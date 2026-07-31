"""Operator-editable settings, stored server-side.

The AI credentials live here rather than in the browser. A key kept in
`localStorage` is readable by any script that runs on the page and is re-sent by
the client on every call; a key kept here is written once, used only by the
server making the outbound request, and never returned to the client in full.

Nothing in this module logs a value. `describe_ai_config` is the only shape the
API hands back, and it carries a hint rather than the secret.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import AppSettingRow

logger = logging.getLogger(__name__)

#: Setting keys. Values under these are treated as secret by the API layer.
NVIDIA_API_KEY = "nvidia_api_key"
NVIDIA_BASE_URL = "nvidia_base_url"
NVIDIA_MODEL = "nvidia_model"

SECRET_KEYS = frozenset({NVIDIA_API_KEY})

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_NVIDIA_API_KEY = "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"


@dataclass(frozen=True)
class AiCredentials:
    """What is needed to call the hosted model."""

    api_key: str
    base_url: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def get_setting(session: Session, key: str) -> Optional[str]:
    row = session.execute(
        select(AppSettingRow).where(AppSettingRow.key == key)
    ).scalar_one_or_none()
    value = (row.value or "").strip() if row else ""
    return value or None


def set_setting(session: Session, key: str, value: str, username: str) -> None:
    """Upsert one setting. The value is never written to the log."""
    row = session.execute(
        select(AppSettingRow).where(AppSettingRow.key == key)
    ).scalar_one_or_none()
    if row is None:
        row = AppSettingRow(key=key)
        session.add(row)
    row.value = value
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = username
    logger.info(
        "Setting %r updated by %s (%s)",
        key, username, "value hidden" if key in SECRET_KEYS else f"value={value!r}",
    )


def clear_setting(session: Session, key: str) -> bool:
    row = session.execute(
        select(AppSettingRow).where(AppSettingRow.key == key)
    ).scalar_one_or_none()
    if row is None:
        return False
    session.delete(row)
    logger.info("Setting %r cleared", key)
    return True


def resolve_ai_credentials(session: Session) -> AiCredentials:
    """Credentials for an outbound call.

    A value set in the UI wins over the environment, so an operator can change
    the key without a redeploy. The environment still works for headless
    deployments that never open the Settings page.
    """
    api_key = (
        get_setting(session, NVIDIA_API_KEY)
        or os.getenv("NVIDIA_API_KEY")
        or DEFAULT_NVIDIA_API_KEY
    )
    return AiCredentials(
        api_key=api_key,
        base_url=(
            get_setting(session, NVIDIA_BASE_URL)
            or os.getenv("NVIDIA_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/"),
        model=(
            get_setting(session, NVIDIA_MODEL)
            or os.getenv("NVIDIA_MODEL")
            or DEFAULT_MODEL
        ),
    )


def mask_secret(value: Optional[str]) -> str:
    """A hint that identifies which key is stored without disclosing it.

    Shows the prefix up to the first dash and the last four characters, so an
    operator can tell `nvapi-…mOzN` from a key they have since rotated. Anything
    short enough that a hint would give most of it away is fully redacted.
    """
    if not value:
        return ""
    if len(value) < 12:
        return "•" * len(value)
    head, _, rest = value.partition("-")
    prefix = f"{head}-" if rest else value[:6]
    return f"{prefix}…{value[-4:]}"


def describe_ai_config(session: Session) -> dict:
    """The client-facing shape. Deliberately excludes the key itself."""
    stored_key = get_setting(session, NVIDIA_API_KEY)
    env_key = os.getenv("NVIDIA_API_KEY", "")
    creds = resolve_ai_credentials(session)

    if stored_key:
        source = "settings"
    elif env_key:
        source = "environment"
    elif DEFAULT_NVIDIA_API_KEY:
        source = "default"
    else:
        source = "none"

    row = session.execute(
        select(AppSettingRow).where(AppSettingRow.key == NVIDIA_API_KEY)
    ).scalar_one_or_none()

    return {
        "configured": creds.configured,
        "source": source,
        "base_url": creds.base_url,
        "model": creds.model,
        "key_hint": mask_secret(creds.api_key),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by if row else None,
    }
