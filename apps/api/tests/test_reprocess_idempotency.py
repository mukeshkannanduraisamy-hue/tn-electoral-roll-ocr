"""Re-processing a file must replace its records, never duplicate them.

The bug this guards: the job runner minted a fresh `page_id` on every run, so
running extraction twice produced two page rows for the same physical page.
A 30-voter page silently became 60 records, and every export double-counted
them. Page identity has to come from (file_id, page_number).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import (  # noqa: E402
    FileRow,
    PageRow,
    RecordRow,
    init_db,
    save_page,
    session_scope,
)
from app.schemas.core import FieldValue, Page, PageStatus, Record  # noqa: E402
from app.services.job_queue import existing_page_ids  # noqa: E402


def make_page(page_id: str, file_id: str, page_number: int, n_records: int) -> Page:
    records = [
        Record(
            id=uuid.uuid4().hex[:12],
            page_id=page_id,
            index=i,
            template_id="electoral_roll_ta",
            fields={
                "serial": FieldValue(
                    key="serial", original_value=str(100 + i), confidence=0.99
                )
            },
        )
        for i in range(n_records)
    ]
    return Page(
        id=page_id,
        file_id=file_id,
        page_number=page_number,
        status=PageStatus.COMPLETED,
        template_id="electoral_roll_ta",
        records=records,
    )


@pytest.fixture()
def temp_file_id():
    """A throwaway FileRow, removed afterwards so the dev DB stays clean."""
    init_db()
    file_id = "test" + uuid.uuid4().hex[:8]
    with session_scope() as session:
        session.add(
            FileRow(id=file_id, name="reprocess-test.pdf", page_count=1,
                    stored_path="", size_bytes=0)
        )
    yield file_id
    with session_scope() as session:
        session.query(RecordRow).filter(RecordRow.file_id == file_id).delete(
            synchronize_session=False
        )
        session.query(PageRow).filter(PageRow.file_id == file_id).delete(
            synchronize_session=False
        )
        session.query(FileRow).filter(FileRow.id == file_id).delete(
            synchronize_session=False
        )


def count_records(file_id: str) -> int:
    with session_scope() as session:
        return session.execute(
            select(func.count()).select_from(RecordRow).where(
                RecordRow.file_id == file_id
            )
        ).scalar_one()


def count_pages(file_id: str) -> int:
    with session_scope() as session:
        return session.execute(
            select(func.count()).select_from(PageRow).where(PageRow.file_id == file_id)
        ).scalar_one()


def test_reprocessing_with_same_page_id_replaces_records(temp_file_id):
    page_id = uuid.uuid4().hex[:12]

    with session_scope() as session:
        save_page(session, make_page(page_id, temp_file_id, 1, 30), temp_file_id)
    assert count_records(temp_file_id) == 30

    with session_scope() as session:
        save_page(session, make_page(page_id, temp_file_id, 1, 30), temp_file_id)

    assert count_records(temp_file_id) == 30, "re-processing must replace, not append"
    assert count_pages(temp_file_id) == 1


def test_fresh_page_id_still_does_not_duplicate(temp_file_id):
    """Defence in depth: even a caller that mishandles page identity is safe.

    `save_page` enforces one row per (file_id, page_number), so a second save
    with a *different* id supersedes the first instead of stacking on top of
    it. This is what stops a bug like the positional-argument mix-up in
    `reocr_page` from silently doubling every record on the page.
    """
    with session_scope() as session:
        save_page(session, make_page(uuid.uuid4().hex[:12], temp_file_id, 1, 30),
                  temp_file_id)
    with session_scope() as session:
        save_page(session, make_page(uuid.uuid4().hex[:12], temp_file_id, 1, 30),
                  temp_file_id)

    assert count_records(temp_file_id) == 30
    assert count_pages(temp_file_id) == 1


def test_distinct_pages_of_same_file_coexist(temp_file_id):
    """The dedup guard must key on page_number, not wipe the whole file."""
    with session_scope() as session:
        save_page(session, make_page(uuid.uuid4().hex[:12], temp_file_id, 1, 30),
                  temp_file_id)
        save_page(session, make_page(uuid.uuid4().hex[:12], temp_file_id, 2, 30),
                  temp_file_id)

    assert count_pages(temp_file_id) == 2
    assert count_records(temp_file_id) == 60


def test_existing_page_ids_returns_prior_identity(temp_file_id):
    """The job runner uses this to reuse a page's id across runs."""
    page_id = uuid.uuid4().hex[:12]
    with session_scope() as session:
        save_page(session, make_page(page_id, temp_file_id, 1, 5), temp_file_id)

    with session_scope() as session:
        mapping = existing_page_ids(session, temp_file_id)

    assert mapping == {1: page_id}


def test_existing_page_ids_empty_for_unprocessed_file(temp_file_id):
    with session_scope() as session:
        assert existing_page_ids(session, temp_file_id) == {}
