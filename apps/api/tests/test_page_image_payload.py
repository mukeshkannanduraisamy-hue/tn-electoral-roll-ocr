"""Bulk page queries must not drag the rendered page images along with them.

Context: ``PageRow.image_data`` holds a base64 PNG of a whole rendered page.
``Page`` has no field for it, so no caller that goes through ``_page_from_row``
can even see it -- yet a plain ``select(PageRow)`` loads every mapped column, so
the sidebar's page index streamed one base64 image per page and a 100-page file
meant 100 of them. This is the same defect that made listing files hang for
~133 s against the remote pooler and die with "SSL connection has been closed
unexpectedly"; here it surfaced as "Failed to fetch page index".

The bytes have two real readers -- ``GET /pages/{id}/image`` and the presence
check in ``save_page`` -- and both want a single page, so the column is deferred
at the mapper and those two sites ask for it explicitly. These tests pin down
both halves: bulk paths must not select it, single-page paths must still get it.
"""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

import pytest  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.inspection import inspect  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker, undefer  # noqa: E402

from app.db import Base, FileRow, PageRow  # noqa: E402
from app.routers.export import _collect_pages  # noqa: E402
from app.routers.files import list_pages  # noqa: E402
from app.schemas.core import ExportFormat, ExportRequest, Page  # noqa: E402


@pytest.fixture()
def session():
    """A throwaway database.

    Its own engine rather than ``app.db``'s: that one is built at import time
    from the environment and points at the development database.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        yield db
    engine.dispose()


@pytest.fixture()
def seeded(session: Session) -> Session:
    """One file with two pages that both carry stored image bytes."""
    session.add(FileRow(id="f1", name="roll.pdf", page_count=2))
    for number in (1, 2):
        session.add(
            PageRow(
                id=f"p{number}",
                file_id="f1",
                page_number=number,
                status="completed",
                image_path=f"f1_p{number}.png",
                image_data="QUJD" * 64,
            )
        )
    session.commit()
    return session


def statements_of(session: Session) -> list[str]:
    """Record every statement the session emits from here on."""
    emitted: list[str] = []

    @event.listens_for(session.get_bind(), "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        emitted.append(statement)

    return emitted


# --- the bulk paths --------------------------------------------------------


def test_default_page_query_omits_the_page_image():
    """`select(PageRow)` is what every bulk caller runs; keep the blob out."""
    sql = str(select(PageRow))
    assert "image_data" not in sql, (
        "selecting pages would stream a base64 page image per row:\n" + sql
    )


def test_page_index_query_omits_the_page_image(seeded: Session):
    """The sidebar's page index -- the query behind "Failed to fetch page index"."""
    emitted = statements_of(seeded)

    summaries = list_pages("f1", session=seeded)

    assert len(summaries) == 2, "fixture pages should have come back"
    offenders = [s for s in emitted if "image_data" in s]
    assert not offenders, (
        "the page index selected the base64 page image:\n" + "\n".join(offenders)
    )


def test_export_collection_omits_the_page_image(seeded: Session):
    """Export loads whole pages, but `Page` has nowhere to put the image."""
    emitted = statements_of(seeded)

    pages = _collect_pages(
        seeded, ExportRequest(format=ExportFormat.CSV, file_ids=["f1"])
    )

    assert len(pages) == 2, "fixture pages should have come back"
    offenders = [s for s in emitted if "image_data" in s]
    assert not offenders, (
        "export selected the base64 page image:\n" + "\n".join(offenders)
    )


def test_page_index_still_returns_the_metadata_the_sidebar_needs(seeded: Session):
    """Deferring must not push the real payload out of the query."""
    summaries = list_pages("f1", session=seeded)

    first = summaries[0]
    for key in ("id", "page_number", "status", "record_count", "error_count"):
        assert key in first, f"{key} missing from the page index response"
    assert first["page_number"] == 1, "page index should be in document order"


def test_page_schema_has_no_image_field():
    """Why deferring is safe for every `_page_from_row` caller.

    If someone adds `image_data` to `Page`, `_page_from_row` will start reading
    the attribute and each exported page will lazily fetch its own image. That
    is a decision to make deliberately, so fail here rather than there.
    """
    assert "image_data" not in Page.model_fields


# --- the single-page paths -------------------------------------------------


def test_image_data_remains_reachable_when_explicitly_asked_for():
    """Deferred, not dropped: the column still exists."""
    assert "image_data" in inspect(PageRow).columns.keys()


def test_undefer_brings_the_page_image_back_in_one_query(seeded: Session):
    """What `GET /pages/{id}/image` does -- the bytes, without a second trip."""
    emitted = statements_of(seeded)

    row = seeded.get(PageRow, "p1", options=[undefer(PageRow.image_data)])

    assert row is not None and row.image_data == "QUJD" * 64
    assert len(emitted) == 1, (
        "the image endpoint should fetch the bytes in its initial load, got:\n"
        + "\n".join(emitted)
    )


def test_save_page_reuses_stored_bytes_without_loading_them(seeded: Session):
    """`save_page`'s presence check must stay a predicate, not a fetch.

    It only needs to know whether bytes are already stored; asking for the
    attribute would pull a base64 PNG back on every page of every OCR run.
    """
    from app.db import _stored_page_image_present

    emitted = statements_of(seeded)

    assert _stored_page_image_present(seeded, "p1") is True
    assert _stored_page_image_present(seeded, "nonexistent") is False

    offenders = [s for s in emitted if "image_data" in s and "IS NOT NULL" not in s]
    assert not offenders, (
        "the presence check selected the bytes instead of a predicate:\n"
        + "\n".join(offenders)
    )
