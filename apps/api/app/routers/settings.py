"""Operator settings, including the AI assistant's credentials.

The API key is write-only over this interface: it can be set, replaced, tested
and cleared, but never read back. `GET` returns a masked hint so an operator can
tell which key is stored without the value being exposed to the browser, to
anything reading the response, or to a screen recording.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..auth import require_user
from ..db import UserRow, get_session
from ..services import app_settings as store

logger = logging.getLogger(__name__)
router = APIRouter()


class AiSettingsUpdate(BaseModel):
    """All fields optional, so the model can be changed without resending the key."""

    api_key: str | None = Field(
        None,
        description="Paste a new key to replace the stored one. Omit to leave it as is.",
    )
    base_url: str | None = None
    model: str | None = None

    @field_validator("api_key")
    @classmethod
    def _reject_the_masked_hint(cls, value: str | None) -> str | None:
        """Guard against a client echoing the hint back as if it were the key.

        The hint contains "…", so saving it would replace a working key with a
        useless placeholder.
        """
        if value and "…" in value:
            raise ValueError(
                "That looks like the masked hint rather than a key. "
                "Paste the full key, or leave the field blank to keep the current one."
            )
        return value

    @field_validator("base_url")
    @classmethod
    def _require_https(cls, value: str | None) -> str | None:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return value


@router.get("/ai")
def get_ai_settings(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict:
    """Current AI configuration. Never includes the key itself."""
    return store.describe_ai_config(session)


@router.put("/ai")
def update_ai_settings(
    payload: AiSettingsUpdate,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    """Save the key, base URL or model.

    A blank string clears that field; omitting it leaves the stored value alone.
    That distinction matters for the key, which the client cannot resend because
    it never received it.
    """
    if payload.api_key is not None:
        key = payload.api_key.strip()
        if key:
            store.set_setting(session, store.NVIDIA_API_KEY, key, user.username)
        else:
            store.clear_setting(session, store.NVIDIA_API_KEY)

    for value, name in (
        (payload.base_url, store.NVIDIA_BASE_URL),
        (payload.model, store.NVIDIA_MODEL),
    ):
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            store.set_setting(session, name, cleaned, user.username)
        else:
            store.clear_setting(session, name)

    session.commit()
    return store.describe_ai_config(session)


@router.delete("/ai/key", status_code=204, response_class=Response)
def clear_ai_key(
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> Response:
    """Forget the stored key. Any key set in the environment takes over again."""
    store.clear_setting(session, store.NVIDIA_API_KEY)
    session.commit()
    logger.info("AI API key cleared by %s", user.username)
    return Response(status_code=204)


@router.post("/ai/test")
def test_ai_settings(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict:
    """Make one tiny live call, so a pasted key can be verified immediately."""
    from ..services.nvidia_ai_service import check_credentials

    creds = store.resolve_ai_credentials(session)
    if not creds.configured:
        raise HTTPException(400, "No API key is configured.")
    return check_credentials(creds)
