"""Authentication: password hashing, sessions, and route protection.

Design choices worth stating, because they are the ones that make this real
security rather than the appearance of it:

* **bcrypt**, not a homemade hash. Work factor 12, and the 72-byte input
  limit is handled explicitly rather than silently truncating.
* **Server-side sessions.** A signed stateless cookie cannot be revoked, so
  "log out" would be a lie and a disabled account would keep working until
  its token expired. Sessions are rows; deleting one ends it immediately.
* **No default password.** The first-run admin password comes from the
  environment, or a strong one is generated and printed once. Shipping a
  known default on an app holding voter PII would be indefensible.
* **Lockout after repeated failures**, so a known username cannot be
  brute-forced, with the counter cleared on success.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionRow, UserRow, get_session, session_scope

logger = logging.getLogger(__name__)

SESSION_COOKIE = "ocr_session"

# bcrypt hashes at most 72 bytes and silently ignores the rest, which would
# make two long passwords sharing a prefix equivalent. Reject instead.
MAX_PASSWORD_BYTES = 72


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            f"({len(encoded)} given)"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:MAX_PASSWORD_BYTES],
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Malformed hash in the database -- treat as a failed login rather
        # than a 500, but make it visible.
        logger.warning("Malformed password hash encountered during login")
        return False


def password_problems(password: str) -> list[str]:
    """Validation messages for a proposed password, empty when acceptable."""
    problems: list[str] = []
    if len(password) < settings.auth_min_password_length:
        problems.append(
            f"must be at least {settings.auth_min_password_length} characters"
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        problems.append(f"must be at most {MAX_PASSWORD_BYTES} bytes")
    if password.lower() in {"password", "admin", "12345678", "changeme"}:
        problems.append("is too common")
    return problems


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(session: Session, user: UserRow, user_agent: str = "") -> SessionRow:
    row = SessionRow(
        token=secrets.token_urlsafe(48),
        user_id=user.id,
        expires_at=_utcnow() + timedelta(hours=settings.auth_session_hours),
        user_agent=user_agent[:256],
    )
    session.add(row)
    return row


def set_session_cookie(response: Response, token: str) -> None:
    is_secure = settings.auth_cookie_secure
    samesite_val = "none" if is_secure else "lax"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.auth_session_hours * 3600,
        httponly=True,  # unreadable from JavaScript, so XSS cannot steal it
        samesite=samesite_val,
        secure=is_secure,  # HTTPS-only in production, False on local HTTP
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    is_secure = settings.auth_cookie_secure
    samesite_val = "none" if is_secure else "lax"
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        samesite=samesite_val,
        secure=is_secure,
    )


def purge_expired_sessions(session: Session) -> int:
    result = session.execute(
        delete(SessionRow).where(SessionRow.expires_at < _utcnow())
    )
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _lookup_user(session: Session, token: str | None) -> UserRow | None:
    if not token:
        return None
    row = session.get(SessionRow, token)
    if row is None:
        return None
    # `expires_at` is stored naive-UTC by SQLite; compare like for like.
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _utcnow():
        session.delete(row)
        return None

    user = session.get(UserRow, row.user_id)
    if user is None or not user.is_active:
        return None

    # Sliding session expiration: auto-extend on active usage, but only if
    # updated more than 1 hour ago to avoid write contention on every read request.
    target_expiry = _utcnow() + timedelta(hours=settings.auth_session_hours)
    if (target_expiry - expires).total_seconds() > 3600:
        row.expires_at = target_expiry
    return user



def current_user_optional(
    ocr_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
) -> UserRow | None:
    """The signed-in user, or None. For endpoints that work either way."""
    return _lookup_user(session, ocr_session)


def require_user(
    ocr_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: Session = Depends(get_session),
) -> UserRow:
    """Gate for every route that touches voter data.

    Returns 401 so the client can redirect to the login screen; a 403 would
    imply the credentials were understood but insufficient.
    """
    if not settings.auth_enabled:
        return _anonymous_user()

    user = _lookup_user(session, ocr_session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


def _anonymous_user() -> UserRow:
    """Stand-in used only when auth is deliberately disabled for local dev."""
    return UserRow(
        id="anonymous",
        username="anonymous",
        password_hash="",
        display_name="Anonymous (auth disabled)",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Lockout
# ---------------------------------------------------------------------------


def is_locked(user: UserRow) -> bool:
    if user.locked_until is None:
        return False
    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > _utcnow()


def register_failure(user: UserRow) -> None:
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= settings.auth_max_failed_attempts:
        user.locked_until = _utcnow() + timedelta(
            minutes=settings.auth_lockout_minutes
        )
        logger.warning(
            "Account %s locked for %d minutes after %d failed attempts",
            user.username,
            settings.auth_lockout_minutes,
            user.failed_attempts,
        )


def register_success(user: UserRow) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = _utcnow()


# ---------------------------------------------------------------------------
# First-run bootstrap
# ---------------------------------------------------------------------------


def ensure_admin_user() -> None:
    """Create the initial admin account if no users exist.

    The password comes from `OCR_ADMIN_PASSWORD`. If that is unset, a strong
    one is generated and logged **once** -- deliberately never a fixed
    default, which would be a published credential on a database of voter
    PII.
    """
    if not settings.auth_enabled:
        logger.warning(
            "OCR_AUTH_ENABLED=false -- the API is UNAUTHENTICATED. "
            "Acceptable for local development only."
        )
        return

    with session_scope() as session:
        if session.execute(select(UserRow.id).limit(1)).first() is not None:
            purge_expired_sessions(session)
            return

        username = settings.admin_username
        password = settings.admin_password
        generated = False
        if not password:
            password = secrets.token_urlsafe(16)
            generated = True

        problems = password_problems(password)
        if problems and not generated:
            raise RuntimeError(
                f"OCR_ADMIN_PASSWORD is unusable: it {', and '.join(problems)}."
            )

        session.add(
            UserRow(
                id=uuid.uuid4().hex[:12],
                username=username,
                password_hash=hash_password(password),
                display_name="Administrator",
            )
        )

        if generated:
            # Printed once, at first boot only. There is no way to recover it
            # afterwards -- the hash is one-way -- so it is loud on purpose.
            logger.warning(
                "\n"
                "==============================================================\n"
                "  Created the initial admin account.\n"
                f"    username: {username}\n"
                f"    password: {password}\n"
                "  Store this now: it is not recoverable and will not be\n"
                "  shown again. Set OCR_ADMIN_PASSWORD to choose your own.\n"
                "=============================================================="
            )
        else:
            logger.info("Created the initial admin account %r from OCR_ADMIN_PASSWORD", username)
