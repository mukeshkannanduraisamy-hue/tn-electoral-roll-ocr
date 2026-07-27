"""SQLite persistence.

Storage strategy
----------------
Pages and records are deeply nested, and mapping every level to its own
table would make reads slow and writes fiddly for no benefit at this scale.
Instead each row keeps its payload as JSON *plus* the handful of columns we
actually query on:

* ``records.error_count`` -- drives the review queue without deserialising
  30 records per page to count issues.
* ``records.search_text`` -- flattened field values, so search is a single
  indexed LIKE rather than a full scan through JSON.
* ``records.mean_confidence`` -- for the confidence-threshold filter.

Those denormalised columns are recomputed on every write in
``_record_to_row``, so they cannot drift from the JSON they summarise.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

logger = logging.getLogger(__name__)

from .config import settings
from .schemas.core import (
    FieldValue,
    FileStatus,
    Issue,
    IssueSeverity,
    Job,
    JobStatus,
    Page,
    Record,
    SourceFile,
)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class FileRow(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    pages_done: Mapped[int] = mapped_column(Integer, default=0)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    stored_path: Mapped[str] = mapped_column(String(1024), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class PageRow(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("files.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    template_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ocr_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Everything not queried directly: lines, layout, issues, header, footer.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class RecordRow(Base):
    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    page_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(String(32), index=True)
    page_number: Mapped[int] = mapped_column(Integer, default=0, index=True)
    index: Mapped[int] = mapped_column(Integer, default=0)
    template_id: Mapped[str] = mapped_column(String(64), default="generic")
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # --- denormalised for querying; recomputed on every write --------------
    error_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    search_text: Mapped[str] = mapped_column(Text, default="")

    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    completed_pages: Mapped[int] = mapped_column(Integer, default=0)
    failed_pages: Mapped[int] = mapped_column(Integer, default=0)
    current_item: Mapped[str | None] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


# ---------------------------------------------------------------------------
# Engine / session
# ---------------------------------------------------------------------------


def _database_url() -> str:
    if settings.database_url:
        return settings.database_url
    settings.ensure_dirs()
    return f"sqlite:///{(settings.data_dir / 'ocr.sqlite').as_posix()}"


engine = create_engine(
    _database_url(),
    echo=False,
    future=True,
    # SQLite + FastAPI: requests are served from a threadpool, so the
    # connection must not be pinned to its creating thread.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _record):
    """WAL keeps readers unblocked while a worker writes results."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def reconcile_interrupted_work() -> dict[str, int]:
    """Clear state owned by a process that no longer exists.

    OCR runs in an in-process worker pool, so a job only lives as long as the
    server does. If the process dies mid-job -- a deploy, a crash, a
    free-tier idle spin-down -- the rows it was updating keep their in-flight
    status forever: files stay "processing" and jobs stay "running", and the
    UI shows work that will never finish.

    Nothing can resume those runs, so on startup we mark the jobs failed and
    return their files to "pending" where they can simply be queued again.
    Runs at boot, before any request is served.
    """
    stats = {"jobs_failed": 0, "files_reset": 0}

    with session_scope() as session:
        orphan_jobs = (
            session.execute(
                select(JobRow).where(
                    JobRow.status.in_([JobStatus.RUNNING.value, JobStatus.QUEUED.value])
                )
            )
            .scalars()
            .all()
        )
        for job in orphan_jobs:
            job.status = JobStatus.FAILED.value
            job.error = "Interrupted by a server restart; re-run the extraction."
            job.finished_at = _utcnow()
            stats["jobs_failed"] += 1

        orphan_files = (
            session.execute(
                select(FileRow).where(FileRow.status == FileStatus.PROCESSING.value)
            )
            .scalars()
            .all()
        )
        for file_row in orphan_files:
            # Anything already extracted is kept; the file just becomes
            # queueable again.
            done = session.execute(
                select(func.count())
                .select_from(PageRow)
                .where(PageRow.file_id == file_row.id)
            ).scalar_one()
            file_row.pages_done = done
            file_row.status = (
                FileStatus.COMPLETED.value
                if done and done >= file_row.page_count
                else FileStatus.PENDING.value
            )
            stats["files_reset"] += 1

    if stats["jobs_failed"] or stats["files_reset"]:
        logger.warning(
            "Startup reconciliation: %d interrupted job(s) failed, %d file(s) reset",
            stats["jobs_failed"],
            stats["files_reset"],
        )
    return stats


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _issue_counts(record: Record) -> tuple[int, int]:
    errors = warnings = 0
    for issue in [*record.issues, *(i for f in record.fields.values() for i in f.issues)]:
        severity = issue.severity if isinstance(issue.severity, str) else issue.severity.value
        if severity == IssueSeverity.ERROR.value:
            errors += 1
        elif severity == IssueSeverity.WARNING.value:
            warnings += 1
    return errors, warnings


def record_to_row(record: Record, file_id: str, page_number: int) -> dict:
    """Serialise a Record, recomputing every denormalised column."""
    errors, warnings = _issue_counts(record)
    # Use explicit None checks — f.value is a property that returns edited_value
    # or original_value; an empty string is valid and must not be excluded.
    values = [f.value for f in record.fields.values() if f.value is not None]
    confidences = [f.confidence for f in record.fields.values() if f.original_value]

    return {
        "id": record.id,
        "page_id": record.page_id,
        "file_id": file_id,
        "page_number": page_number,
        "index": record.index,
        "template_id": record.template_id,
        "reviewed": record.reviewed,
        "error_count": errors,
        "warning_count": warnings,
        "mean_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
        "min_confidence": min(confidences) if confidences else 0.0,
        "edited": any(f.is_edited for f in record.fields.values()),
        # Lower-cased so search can use a case-insensitive LIKE cheaply.
        "search_text": " ".join(values).lower(),
        "fields": {k: json.loads(v.model_dump_json()) for k, v in record.fields.items()},
        "issues": [json.loads(i.model_dump_json()) for i in record.issues],
        "bbox": json.loads(record.bbox.model_dump_json()) if record.bbox else None,
    }


def row_to_record(row: RecordRow) -> Record:
    return Record(
        id=row.id,
        page_id=row.page_id,
        index=row.index,
        template_id=row.template_id,
        fields={k: FieldValue(**v) for k, v in (row.fields or {}).items()},
        bbox=row.bbox,
        issues=[Issue(**i) for i in (row.issues or [])],
        reviewed=row.reviewed,
    )


def save_page(session: Session, page: Page, file_id: str) -> None:
    """Upsert a page and replace its records."""
    if session.get(FileRow, file_id) is None:
        logger.warning("Parent file %s was deleted mid-job; skipping save_page", file_id)
        return

    payload = json.loads(page.model_dump_json())
    # Records live in their own table; don't duplicate them in the blob.
    payload.pop("records", None)

    # A physical page must map to exactly one row. Anything else claiming the
    # same (file_id, page_number) is a stale row from an earlier run, and
    # leaving it behind means the page's records are counted twice in the
    # table, the review queue and every export. Enforce the invariant here so
    # a caller that mishandles page identity cannot corrupt the data set.
    stale = (
        session.execute(
            select(PageRow).where(
                PageRow.file_id == file_id,
                PageRow.page_number == page.page_number,
                PageRow.id != page.id,
            )
        )
        .scalars()
        .all()
    )
    for stale_row in stale:
        logger.warning(
            "Removing stale duplicate page %s for %s p%s",
            stale_row.id, file_id, page.page_number,
        )
        session.query(RecordRow).filter(RecordRow.page_id == stale_row.id).delete(
            synchronize_session=False
        )
        session.delete(stale_row)

    row = session.get(PageRow, page.id)
    if row is None:
        row = PageRow(id=page.id)
        session.add(row)

    row.file_id = file_id
    row.page_number = page.page_number
    row.status = page.status if isinstance(page.status, str) else page.status.value
    row.image_path = page.image_path
    row.width = page.width
    row.height = page.height
    row.template_id = page.template_id
    row.template_confidence = page.template_confidence
    row.ocr_ms = page.ocr_ms
    row.error = page.error
    row.payload = payload

    # Replace records wholesale -- re-OCR must not leave stale rows behind.
    session.query(RecordRow).filter(RecordRow.page_id == page.id).delete(
        synchronize_session=False
    )
    for record in page.records:
        session.add(RecordRow(**record_to_row(record, file_id, page.page_number)))


def load_page(session: Session, page_id: str) -> Page | None:
    row = session.get(PageRow, page_id)
    if row is None:
        return None
    return _page_from_row(session, row)


def _page_from_row(session: Session, row: PageRow) -> Page:
    payload = dict(row.payload or {})
    payload.update(
        {
            "id": row.id,
            "file_id": row.file_id,
            "page_number": row.page_number,
            "status": row.status,
            "image_path": row.image_path,
            "width": row.width,
            "height": row.height,
            "template_id": row.template_id,
            "template_confidence": row.template_confidence,
            "ocr_ms": row.ocr_ms,
            "error": row.error,
        }
    )
    page = Page(**payload)
    records = (
        session.execute(
            select(RecordRow)
            .where(RecordRow.page_id == row.id)
            .order_by(RecordRow.index)
        )
        .scalars()
        .all()
    )
    page.records = [row_to_record(r) for r in records]
    return page


def load_pages_for_file(session: Session, file_id: str) -> list[Page]:
    rows = (
        session.execute(
            select(PageRow)
            .where(PageRow.file_id == file_id)
            .order_by(PageRow.page_number)
        )
        .scalars()
        .all()
    )
    return [_page_from_row(session, r) for r in rows]


def file_to_schema(row: FileRow) -> SourceFile:
    return SourceFile(
        id=row.id,
        name=row.name,
        size_bytes=row.size_bytes,
        page_count=row.page_count,
        status=row.status,
        pages_done=row.pages_done,
        template_id=row.template_id,
        languages=row.languages or [],
        created_at=row.created_at,
        error=row.error,
    )


def job_to_schema(row: JobRow) -> Job:
    return Job(
        id=row.id,
        file_ids=row.file_ids or [],
        status=row.status,
        total_pages=row.total_pages,
        completed_pages=row.completed_pages,
        failed_pages=row.failed_pages,
        current_item=row.current_item,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error=row.error,
    )
