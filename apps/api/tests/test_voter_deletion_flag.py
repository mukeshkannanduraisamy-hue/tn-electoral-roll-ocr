"""Promotion carries a record's deletion verdict through to the voter table.

The extractor already reads the DELETED stamp and its reason code, but until
the voters table had somewhere to keep them the status was computed and then
dropped — a struck-off elector looked identical to an active one once promoted.
This pins the wiring so that regression cannot come back silently.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import (  # noqa: E402
    FileRow,
    PageRow,
    RecordRow,
    UserRow,
    VoterRow,
    session_scope,
)
from app.routers.voters import promote_records  # noqa: E402
from app.schemas.voters import PromotionRequest  # noqa: E402


def _field(key: str, value: str) -> dict:
    return {"key": key, "original_value": value, "confidence": 1.0}


def _record_fields(epic: str, name: str, is_deleted: str, reason: str = "") -> dict:
    fields = {
        "epic": _field("epic", epic),
        "name": _field("name", name),
        "relation_type": _field("relation_type", "Father"),
        "relation_name": _field("relation_name", "Test Father"),
        "house_number": _field("house_number", "1-1"),
        "age": _field("age", "40"),
        "gender": _field("gender", "Male"),
        "is_deleted": _field("is_deleted", is_deleted),
    }
    if reason:
        fields["deletion_reason"] = _field("deletion_reason", reason)
    return fields


@pytest.fixture()
def seeded():
    """A file/page and two records — one struck off, one active — plus a user."""
    fid = uuid.uuid4().hex[:12]
    pid = uuid.uuid4().hex[:12]
    uid = uuid.uuid4().hex[:12]
    epic_del = f"DEL{uuid.uuid4().hex[:7].upper()}"
    epic_active = f"ACT{uuid.uuid4().hex[:7].upper()}"

    with session_scope() as s:
        s.add(UserRow(id=uid, username=f"t-{uid[:6]}", password_hash="x"))
        s.add(FileRow(id=fid, name="deletion-test.pdf"))
        s.add(PageRow(id=pid, file_id=fid, page_number=1, page_type="voter_list_page"))
        s.add(RecordRow(
            id=uuid.uuid4().hex[:12], page_id=pid, file_id=fid, page_number=1, index=0,
            error_count=0, fields=_record_fields(epic_del, "Struck Off", "Yes", "E"),
        ))
        s.add(RecordRow(
            id=uuid.uuid4().hex[:12], page_id=pid, file_id=fid, page_number=1, index=1,
            error_count=0, fields=_record_fields(epic_active, "Still Here", "No"),
        ))

    yield {"file_id": fid, "user_id": uid, "epic_del": epic_del, "epic_active": epic_active}

    with session_scope() as s:
        for v in s.query(VoterRow).filter(VoterRow.epic.in_([epic_del, epic_active])).all():
            s.delete(v)
        f = s.get(FileRow, fid)
        if f is not None:
            s.delete(f)  # cascades to page + records
        u = s.get(UserRow, uid)
        if u is not None:
            s.delete(u)


def test_a_struck_off_record_promotes_as_deleted(seeded):
    with session_scope() as s:
        user = s.get(UserRow, seeded["user_id"])
        s.expunge(user)
        promote_records(
            PromotionRequest(file_id=seeded["file_id"], only_clean=True),
            session=s,
            user=user,
        )

    with session_scope() as s:
        deleted = s.query(VoterRow).filter_by(epic=seeded["epic_del"]).one()
        active = s.query(VoterRow).filter_by(epic=seeded["epic_active"]).one()
        assert deleted.is_deleted is True
        assert deleted.deletion_reason == "E"
        assert active.is_deleted is False
        assert active.deletion_reason == ""
