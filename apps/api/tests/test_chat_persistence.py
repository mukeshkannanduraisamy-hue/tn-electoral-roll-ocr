"""Chat threads outlive a process, and deleting a thread takes its messages."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import ChatMessageRow, ChatThreadRow, UserRow, session_scope  # noqa: E402


@pytest.fixture(scope="module")
def owner_id():
    """A real user row: foreign keys are enforced (db.py PRAGMA foreign_keys=ON)."""
    uid = uuid.uuid4().hex[:32]
    with session_scope() as s:
        s.add(UserRow(id=uid, username=f"test-{uid[:8]}", password_hash="x"))
    yield uid
    with session_scope() as s:
        row = s.get(UserRow, uid)
        if row is not None:
            s.delete(row)


@pytest.fixture()
def thread_id(owner_id):
    tid = uuid.uuid4().hex[:32]
    with session_scope() as s:
        s.add(ChatThreadRow(id=tid, user_id=owner_id, title="Fixture thread"))
    yield tid
    with session_scope() as s:
        row = s.get(ChatThreadRow, tid)
        if row is not None:
            s.delete(row)


def test_messages_round_trip_their_json_columns(thread_id):
    with session_scope() as s:
        s.add(
            ChatMessageRow(
                id=uuid.uuid4().hex[:32],
                thread_id=thread_id,
                role="assistant",
                content="412 electors.",
                tool_trace=[{"tool": "search_voters", "rows": 412}],
                citations=[{"id": "v1", "epic": "ABC1234567"}],
                blocks=[{"kind": "table", "columns": ["name"]}],
            )
        )
    with session_scope() as s:
        row = s.query(ChatMessageRow).filter_by(thread_id=thread_id).one()
        assert row.tool_trace[0]["tool"] == "search_voters"
        assert row.citations[0]["epic"] == "ABC1234567"
        assert row.blocks[0]["kind"] == "table"


def test_deleting_a_thread_removes_its_messages(thread_id):
    with session_scope() as s:
        s.add(
            ChatMessageRow(
                id=uuid.uuid4().hex[:32], thread_id=thread_id, role="user", content="hi"
            )
        )
    with session_scope() as s:
        s.delete(s.get(ChatThreadRow, thread_id))
    with session_scope() as s:
        assert s.query(ChatMessageRow).filter_by(thread_id=thread_id).count() == 0
