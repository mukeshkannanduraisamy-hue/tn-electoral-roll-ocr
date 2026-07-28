"""Password hashing, session lifecycle and lockout.

No HTTP, no database fixtures beyond the real engine -- these are the pure
security primitives, and they should be fast enough to run on every save.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.auth import (  # noqa: E402
    MAX_PASSWORD_BYTES,
    create_session,
    hash_password,
    is_locked,
    password_problems,
    register_failure,
    register_success,
    verify_password,
)
from app.config import settings  # noqa: E402
from app.db import SessionRow, UserRow, init_db, session_scope  # noqa: E402


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def test_hash_is_not_the_password():
    h = hash_password("correct horse battery staple")
    assert "correct" not in h
    assert h.startswith("$2b$")


def test_verify_round_trip():
    h = hash_password("Str0ng!Passphrase")
    assert verify_password("Str0ng!Passphrase", h) is True
    assert verify_password("str0ng!passphrase", h) is False
    assert verify_password("", h) is False


def test_same_password_hashes_differently():
    """Distinct salts, so identical passwords are not identical hashes."""
    assert hash_password("Repeated!123") != hash_password("Repeated!123")


def test_overlong_password_is_rejected_not_truncated():
    """bcrypt ignores bytes past 72; silently truncating would make two long
    passwords sharing a prefix equivalent."""
    with pytest.raises(ValueError):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_multibyte_password_counted_in_bytes():
    # Tamil characters are 3 bytes each in UTF-8.
    assert password_problems("கடவுச்சொல்" * 10)


def test_malformed_hash_fails_closed():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


@pytest.mark.parametrize("weak", ["short", "password", "admin", "12345678"])
def test_weak_passwords_flagged(weak):
    assert password_problems(weak)


def test_reasonable_password_accepted():
    assert password_problems("Tamil!Roll2026x") == []


# ---------------------------------------------------------------------------
# Lockout
# ---------------------------------------------------------------------------


def _user() -> UserRow:
    return UserRow(id="u1", username="tester", password_hash="x", failed_attempts=0)


def test_lockout_after_repeated_failures():
    user = _user()
    assert not is_locked(user)
    for _ in range(settings.auth_max_failed_attempts):
        register_failure(user)
    assert is_locked(user), "account should lock after the configured failures"


def test_lockout_clears_on_success():
    user = _user()
    for _ in range(settings.auth_max_failed_attempts):
        register_failure(user)
    assert is_locked(user)

    register_success(user)
    assert not is_locked(user)
    assert user.failed_attempts == 0
    assert user.last_login_at is not None


def test_expired_lock_no_longer_blocks():
    user = _user()
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert not is_locked(user)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_session_token_is_long_and_unique():
    init_db()
    tokens = set()
    with session_scope() as session:
        user = UserRow(
            id=uuid.uuid4().hex[:12],
            username=f"sess-{uuid.uuid4().hex[:6]}",
            password_hash=hash_password("Tamil!Roll2026x"),
        )
        session.add(user)
        session.flush()
        for _ in range(5):
            row = create_session(session, user)
            tokens.add(row.token)
            assert len(row.token) >= 32, "token must not be guessable"

        assert len(tokens) == 5, "tokens must be unique"

        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expires > datetime.now(timezone.utc)

        # Clean up so the dev database is not littered with test rows.
        for token in tokens:
            session.delete(session.get(SessionRow, token))
        session.delete(session.get(UserRow, user.id))
