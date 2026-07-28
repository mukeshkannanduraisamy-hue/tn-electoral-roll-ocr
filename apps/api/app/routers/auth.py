"""Login, logout and session introspection."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    current_user_optional,
    hash_password,
    is_locked,
    password_problems,
    register_failure,
    register_success,
    require_user,
    set_session_cookie,
    verify_password,
)
from ..config import settings
from ..db import SessionRow, UserRow, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    last_login_at: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def _user_out(user: UserRow) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> UserOut:
    user = session.execute(
        select(UserRow).where(UserRow.username == payload.username)
    ).scalar_one_or_none()

    # One message for every failure mode. Distinguishing "no such user" from
    # "wrong password" tells an attacker which usernames exist.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
    )

    if user is None:
        # Spend roughly the same time as a real check so the response time
        # does not reveal whether the account exists.
        verify_password(payload.password, "$2b$12$" + "." * 53)
        raise invalid

    if is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many failed attempts. Try again in "
                f"{settings.auth_lockout_minutes} minutes."
            ),
        )

    if not user.is_active:
        raise invalid

    if not verify_password(payload.password, user.password_hash):
        register_failure(user)
        logger.info("Failed login for %r", payload.username)
        raise invalid

    register_success(user)
    row = create_session(session, user, request.headers.get("user-agent", ""))
    set_session_cookie(response, row.token)
    logger.info("User %r signed in", user.username)
    return _user_out(user)


@router.post("/logout", status_code=204, response_class=Response)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> Response:
    """Ends the session server-side, so the cookie cannot be replayed."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session.execute(delete(SessionRow).where(SessionRow.token == token))
    out = Response(status_code=204)
    clear_session_cookie(out)
    return out


@router.get("/me", response_model=UserOut)
def me(user: UserRow = Depends(require_user)) -> UserOut:
    return _user_out(user)


@router.get("/status")
def auth_status(user: UserRow | None = Depends(current_user_optional)) -> dict:
    """Unauthenticated probe, so the UI knows whether to show the login screen."""
    return {
        "auth_enabled": settings.auth_enabled,
        "authenticated": user is not None or not settings.auth_enabled,
        "user": _user_out(user).model_dump() if user else None,
    }


@router.post("/password", status_code=204, response_class=Response)
def change_password(
    payload: PasswordChange,
    request: Request,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")

    problems = password_problems(payload.new_password)
    if problems:
        raise HTTPException(400, "New password " + ", and ".join(problems))

    row = session.get(UserRow, user.id)
    row.password_hash = hash_password(payload.new_password)

    # Changing a password invalidates every other session: if the reason for
    # the change is a suspected compromise, leaving them alive defeats it.
    current = request.cookies.get(SESSION_COOKIE)
    session.execute(
        delete(SessionRow).where(
            SessionRow.user_id == user.id, SessionRow.token != current
        )
    )
    logger.info("Password changed for %r; other sessions revoked", user.username)
    return Response(status_code=204)
