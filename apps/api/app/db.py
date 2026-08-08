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
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

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
    inspect,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

if TYPE_CHECKING:
    from alembic.config import Config

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
    page_type: Mapped[str] = mapped_column(String(64), default="voter_list_page", index=True)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)
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
# Authentication
# ---------------------------------------------------------------------------


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    """bcrypt hash. The plaintext password is never stored or logged."""
    display_name: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    """Set after repeated failures, so a stolen username cannot be brute-forced."""


class SessionRow(Base):
    """Server-side sessions.

    A signed stateless cookie would avoid this table, but it cannot be
    revoked: logging out, or disabling a compromised account, would leave
    every issued token valid until it expired. Sessions live in the database
    so "log out" actually means something.
    """

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user_agent: Mapped[str] = mapped_column(String(256), default="")


# ---------------------------------------------------------------------------
# Curated voter records
# ---------------------------------------------------------------------------


class VoterRow(Base):
    """The database of record, distinct from raw OCR output.

    OCR records are *evidence*: they may contain duplicate EPIC numbers
    because the recogniser misread a digit, and rejecting those would lose
    the 29 good records that share the page. This table is the curated set
    a human has accepted, so here EPIC genuinely is unique and the database
    enforces it.

    Provenance columns point back at the OCR record a row was promoted from,
    so any value can be traced to the page image it came from.
    """

    __tablename__ = "voters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # The uniqueness guarantee the whole table exists to provide.
    epic: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    serial: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="", index=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="")
    relation_name: Mapped[str] = mapped_column(String(255), default="")
    house_number: Mapped[str] = mapped_column(String(64), default="")
    age: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    gender: Mapped[str] = mapped_column(String(16), default="", index=True)

    # Page furniture, denormalised so a voter row stands alone in an export.
    part_number: Mapped[str] = mapped_column(String(32), default="", index=True)
    constituency: Mapped[str] = mapped_column(String(255), default="")
    section_name: Mapped[str] = mapped_column(String(512), default="")

    # --- provenance ------------------------------------------------------
    source_record_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_page_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_file_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_file_name: Mapped[str] = mapped_column(String(512), default="")
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    polling_station_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_supplement: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # A Special Intensive Revision roll marks removed electors with a DELETED
    # stamp and a reason code (S-shifted, E-expired, R-repeated, M-missing,
    # Q-disqualified). The extractor reads both; without these columns that
    # status was computed and then dropped on the way to storage, so the app
    # could not tell a struck-off elector from an active one.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deletion_reason: Mapped[str] = mapped_column(String(64), default="")

    notes: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Lower-cased concatenation of the searchable fields, so search is one
    # indexed LIKE instead of an OR across six columns.
    search_text: Mapped[str] = mapped_column(Text, default="", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    created_by: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(128), default="")


# ---------------------------------------------------------------------------
# Polling Stations, Photos, OCR Blocks, Audit Logs, Summaries
# ---------------------------------------------------------------------------


class PollingStationRow(Base):
    """One row per part, read off that part's cover sheet.

    Follows the same split as `records`: columns for what gets filtered and
    sorted on, and a JSON `payload` for the rest. A station is identified by
    its part within a constituency, so (ac_number, part_number) is the
    natural key -- `file_id` only says which upload it arrived on.
    """

    __tablename__ = "polling_stations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(32), ForeignKey("files.id", ondelete="CASCADE"), index=True)
    part_number: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    name_tam: Mapped[str] = mapped_column(String(255), default="")
    building_name: Mapped[str] = mapped_column(String(512), default="")
    section_details: Mapped[str] = mapped_column(Text, default="")
    total_electors: Mapped[int] = mapped_column(Integer, default=0)
    male_electors: Mapped[int] = mapped_column(Integer, default=0)
    female_electors: Mapped[int] = mapped_column(Integer, default=0)
    third_gender_electors: Mapped[int] = mapped_column(Integer, default=0)

    # --- constituency ----------------------------------------------------
    ac_number: Mapped[str] = mapped_column(String(16), default="", index=True)
    ac_name: Mapped[str] = mapped_column(String(255), default="")
    pc_number: Mapped[str] = mapped_column(String(16), default="")
    pc_name: Mapped[str] = mapped_column(String(255), default="")

    # --- station ---------------------------------------------------------
    station_number: Mapped[str] = mapped_column(String(16), default="")
    station_type: Mapped[str] = mapped_column(String(32), default="")
    address: Mapped[str] = mapped_column(Text, default="")

    # --- where it is (the useful filters) --------------------------------
    district: Mapped[str] = mapped_column(String(128), default="", index=True)
    taluk: Mapped[str] = mapped_column(String(128), default="", index=True)
    pincode: Mapped[str] = mapped_column(String(16), default="", index=True)

    # --- elector range ---------------------------------------------------
    serial_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    serial_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source_page_id: Mapped[str] = mapped_column(String(32), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    """Full `PollingStationInfo`, including the fields not broken out above."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class PhotoRow(Base):
    """An image cropped out of a page.

    Either station imagery from the map sheet, or a voter's photograph.
    `record_id` links a voter crop to the OCR record it came from, which is
    how it later reaches the voter promoted from that record -- the crop
    exists before any voter does.
    """

    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    page_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    record_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    voter_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    polling_station_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    photo_type: Mapped[str] = mapped_column(String(64), default="voter_crop", index=True)  # voter_crop | station_front | nazri_naksha | google_map | cad_map | thumbnail
    file_path: Mapped[str] = mapped_column(String(1024), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class OCRBlockRow(Base):
    __tablename__ = "ocr_blocks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    page_id: Mapped[str] = mapped_column(String(32), ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    record_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    field_name: Mapped[str] = mapped_column(String(64), default="")
    bbox_x0: Mapped[int] = mapped_column(Integer, default=0)  # 0-1000 LayoutLMv3 scale
    bbox_y0: Mapped[int] = mapped_column(Integer, default=0)
    bbox_x1: Mapped[int] = mapped_column(Integer, default=0)
    bbox_y1: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    corrected_text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class AuditLogRow(Base):
    """Who changed what, when.

    One row per changed *field*, not per request: "name corrected, age left
    alone" is the question people actually ask of an electoral roll, and a
    request-level log cannot answer it. Creation and deletion are single
    rows, since enumerating every field of a new record says nothing.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    voter_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    file_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    page_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), default="updated", index=True)
    """created | updated | deleted | promoted"""
    field_name: Mapped[str] = mapped_column(String(128), default="")
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str] = mapped_column(String(128), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class AppSettingRow(Base):
    """Operator-editable settings that outlive a process.

    Exists so credentials entered in the UI are held by the server rather than
    the browser: an API key in `localStorage` is readable by any script on the
    page and travels with every request. Values here are returned to the client
    masked, never in full.

    Not a place for anything the code depends on at import time -- that belongs
    in `config.py` and the environment.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    """Stored as written. Treated as secret by the API layer, never logged."""
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(128), default="")


class SummaryRow(Base):
    """The statutory summary sheet, plus what extraction actually produced.

    The count columns hold the *net* figures -- the roll's own bottom line
    after supplements -- because that is the number everything else is
    compared against. `reconciled` is the headline: it says whether the
    records extracted from this file match the total the file itself prints.
    """

    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_id: Mapped[str] = mapped_column(String(32), ForeignKey("files.id", ondelete="CASCADE"), index=True)
    total_voters: Mapped[int] = mapped_column(Integer, default=0)
    male_count: Mapped[int] = mapped_column(Integer, default=0)
    female_count: Mapped[int] = mapped_column(Integer, default=0)
    third_gender_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_age: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- how the net total was arrived at --------------------------------
    base_total: Mapped[int] = mapped_column(Integer, default=0)
    additions_total: Mapped[int] = mapped_column(Integer, default=0)
    deletions_total: Mapped[int] = mapped_column(Integer, default=0)
    corrections: Mapped[int] = mapped_column(Integer, default=0)

    # --- extraction against the printed figure ---------------------------
    extracted_records: Mapped[int] = mapped_column(Integer, default=0)
    printed_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reconciliation_source: Mapped[str] = mapped_column(String(16), default="")
    """Which sheet `printed_total` came from: `summary` or `cover`."""

    source_page_id: Mapped[str] = mapped_column(String(32), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    """Full `RollSummary`, including the per-gender supplement breakdowns."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


# ---------------------------------------------------------------------------
# Assistant conversations
# ---------------------------------------------------------------------------


class ChatThreadRow(Base):
    """One conversation with the assistant.

    Threads are per-user. The assistant reads the database on the operator's
    behalf, so a thread must never be visible to another account.
    """

    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, index=True
    )

    messages: Mapped[list["ChatMessageRow"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", passive_deletes=True
    )


class ChatMessageRow(Base):
    """One turn.

    `tool_trace`, `citations` and `blocks` are stored so reopening a thread
    replays exactly what the operator saw, including which tools ran. An answer
    whose workings cannot be reread is an answer that cannot be audited.
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="user")
    """user | assistant"""
    content: Mapped[str] = mapped_column(Text, default="")
    tool_trace: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    budget_exhausted: Mapped[bool] = mapped_column(Boolean, default=False)
    """The turn that produced this reply ran out of rounds, calls or wall
    clock (`done.budget_exhausted` from the agent loop). The model is only
    nudged to say so in prose and may not, so this is the one guaranteed
    signal a reader has that the answer may be incomplete."""
    provider_notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    """A provider failure surfaced mid-stream (rate limit, truncation) that
    was deliberately kept out of the answer prose (`done.provider_notice`)."""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    thread: Mapped["ChatThreadRow"] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# Engine / session
# ---------------------------------------------------------------------------


def database_url() -> str:
    """The URL both the app and alembic connect through.

    Public because `migrations/env.py` reads it: pointing alembic at its own
    copy in `alembic.ini` is how a migration ends up applied to a different
    database than the one the app is using.
    """
    import os
    url = settings.database_url or os.getenv("DATABASE_URL") or os.getenv("OCR_DATABASE_URL") or ""
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url
    settings.ensure_dirs()
    return f"sqlite:///{(settings.data_dir / 'ocr.sqlite').as_posix()}"


_is_sqlite = database_url().startswith("sqlite")
_connect_args = {"check_same_thread": False, "timeout": 60} if _is_sqlite else {}

engine = create_engine(
    database_url(),
    echo=False,
    future=True,
    connect_args=_connect_args,
)


if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _record):
        """WAL keeps readers unblocked while a worker writes results."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


MIGRATIONS_ROOT = Path(__file__).resolve().parents[1]
"""apps/api -- holds alembic.ini and the migrations package."""


def _alembic_config() -> "Config":
    from alembic.config import Config

    config = Config(str(MIGRATIONS_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_ROOT / "migrations"))
    # The app has already configured logging; let env.py know not to replace
    # the handlers by re-reading the ini file.
    config.attributes["standalone"] = False
    return config


@contextmanager
def alembic_session() -> Iterator["Config"]:
    """An alembic config bound to the application's own connection.

    Sharing the connection rather than letting alembic open its own matters
    on SQLite: a second writer against the same file is how a migration ends
    up blocked behind the connection that triggered it.
    """
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        yield config


def _run_alembic(action: str, revision: str = "head") -> None:
    """Run one of the revision-taking commands (upgrade, downgrade, stamp)."""
    from alembic import command

    with alembic_session() as config:
        getattr(command, action)(config, revision)


def current_revision() -> str | None:
    """The revision this database is stamped at, or None if it is not.

    Deliberately reads the *row*, not the table. Several alembic commands
    (`current` among them) create an empty `alembic_version` table as a side
    effect of connecting, so a table-presence check reports a database as
    version-controlled when nothing has been stamped -- and the upgrade path
    then replays the baseline against a schema that already exists.
    """
    if "alembic_version" not in _table_names():
        return None
    with engine.begin() as connection:
        row = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
    return row[0] if row else None


def is_under_alembic() -> bool:
    return current_revision() is not None


def _table_names() -> set[str]:
    return set(inspect(engine).get_table_names())


def init_db() -> None:
    """Bring the database to the current schema.

    Three cases, and the middle one is the awkward one:

    * **Already under alembic** -- upgrade to head, the ordinary path.
    * **Predates alembic** -- the schema exists but there is no version
      table, so alembic cannot tell what has been applied. Reconcile the
      schema additively, then stamp it as current. This runs once, ever.
    * **Empty** -- upgrade from scratch; the baseline migration creates
      everything.
    """
    settings.ensure_dirs()

    if current_revision() is not None:
        _run_alembic("upgrade")
        return

    if _table_names() & {"files", "pages", "records"}:
        _adopt_pre_alembic_database()
        return

    _run_alembic("upgrade")
    logger.info("Created a new database at the current schema")


def _adopt_pre_alembic_database() -> None:
    """Bring a database created by `create_all` under alembic's control.

    Only additive repairs are attempted -- missing tables, indexes and
    columns. Anything alembic could not have done here either (rewriting a
    column's type, backfilling a value) is deliberately left alone and
    reported by `schema_drift`, because silently rebuilding a table holding
    real electoral data is not a thing to do at import time.
    """
    logger.info("Database predates alembic; reconciling and stamping as current")
    Base.metadata.create_all(engine)  # checkfirst: adds missing tables/indexes
    _add_missing_columns()
    _run_alembic("stamp")

    drift = schema_drift()
    if drift:
        logger.warning(
            "Schema still differs from the models after adoption: %s. "
            "These need a migration; see `python manage.py db revision`.",
            "; ".join(f"{t}: {', '.join(c)}" for t, c in sorted(drift.items())),
        )


def schema_drift() -> dict[str, list[str]]:
    """Model columns the database does not have, by table.

    A diagnostic, not a repair. Once alembic owns the schema a missing
    column means a migration was not written, and the useful response is to
    say so rather than to quietly add it and let the two histories diverge.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    drift: dict[str, list[str]] = {}
    for name, table in Base.metadata.tables.items():
        if name not in existing_tables:
            drift[name] = ["<table missing>"]
            continue
        have = {column["name"] for column in inspector.get_columns(name)}
        missing = sorted({column.name for column in table.columns} - have)
        if missing:
            drift[name] = missing
    return drift


def _column_default_literal(column) -> str | None:
    """A SQL literal for `column`'s Python-side default, if one can be had."""
    default = getattr(column.default, "arg", None)
    if default is None:
        return None
    if callable(default):
        try:
            # Zero-arg factories (`list`, `dict`) are the common case; the
            # ORM also passes a context to some, which we cannot supply.
            default = default()
        except TypeError:
            return None
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, (int, float)):
        return str(default)
    if isinstance(default, str):
        return "'" + default.replace("'", "''") + "'"
    if isinstance(default, (dict, list)):
        return "'" + json.dumps(default).replace("'", "''") + "'"
    return None


def _add_missing_columns() -> None:
    """Add model columns a pre-alembic database does not have yet.

    Called only from `_adopt_pre_alembic_database`, once, on a database that
    was built by `create_all` and so may be missing any column added to a
    model after it was created -- which had already happened four times here
    (`pages.page_type` and three columns on `voters`). Derived from the model
    metadata rather than a hand-kept list, because a list only catches the
    columns someone remembered to add to it.

    Additive only. Existing rows get the column default, or NULL where no
    literal default can be derived, so a column the model declares NOT NULL
    may hold NULL on rows written before it existed. Everything else --
    renames, drops, type changes, backfills -- is alembic's job now.
    """
    with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
            }
            if not existing:
                continue  # table itself is absent; create_all owns it

            for column in table.columns:
                if column.name in existing:
                    continue

                ddl = f"{column.name} {column.type.compile(engine.dialect)}"
                literal = _column_default_literal(column)
                if literal is not None:
                    ddl += f" DEFAULT {literal}"

                conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")
                logger.info("Added column %s.%s", table_name, column.name)


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
    row.page_type = page.page_type
    row.classification_confidence = page.classification_confidence
    row.ocr_ms = page.ocr_ms
    row.error = page.error
    row.payload = payload

    # Replace records wholesale -- re-OCR must not leave stale rows behind.
    session.query(RecordRow).filter(RecordRow.page_id == page.id).delete(
        synchronize_session=False
    )
    session.query(OCRBlockRow).filter(OCRBlockRow.page_id == page.id).delete(
        synchronize_session=False
    )
    session.query(PhotoRow).filter(PhotoRow.page_id == page.id).delete(
        synchronize_session=False
    )
    for photo in page.photos:
        session.add(
            PhotoRow(
                id=uuid.uuid4().hex[:12],
                file_id=file_id,
                page_id=page.id,
                record_id=photo.record_id,
                photo_type=photo.photo_type,
                file_path=photo.file_path,
                width=photo.width,
                height=photo.height,
            )
        )

    for record in page.records:
        session.add(RecordRow(**record_to_row(record, file_id, page.page_number)))
        for block in _ocr_blocks_for(record, page):
            session.add(block)


def _ocr_blocks_for(record: Record, page: Page) -> Iterator[OCRBlockRow]:
    """One block per located field, with its box on the 0-1000 grid.

    Normalised rather than stored in page pixels so a block stays meaningful
    if the page is later re-rendered at a different DPI -- the raw geometry
    is already in the page payload for anyone who wants pixels.

    Fields the template never found have no box and no block: an absent
    field is absent, and inventing a zero-area block for it would put a
    phantom highlight in the top-left corner of the page overlay.
    """
    for key, field in record.fields.items():
        if field.bbox is None:
            continue
        x0, y0, x1, y1 = field.bbox.to_layoutlm(page.width, page.height)
        yield OCRBlockRow(
            id=uuid.uuid4().hex[:12],
            page_id=page.id,
            record_id=record.id,
            field_name=key,
            bbox_x0=x0,
            bbox_y0=y0,
            bbox_x1=x1,
            bbox_y1=y1,
            raw_text=field.original_value,
            corrected_text=field.edited_value or "",
            confidence=field.confidence,
        )


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
            "page_type": row.page_type,
            "classification_confidence": row.classification_confidence,
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


def record_audit(
    session: Session,
    voter_id: str,
    *,
    action: str,
    user: str,
    field_name: str = "",
    old_value: str | None = None,
    new_value: str | None = None,
    file_id: str | None = None,
    page_id: str | None = None,
) -> AuditLogRow:
    """Append one entry to the audit trail."""
    entry = AuditLogRow(
        id=uuid.uuid4().hex[:12],
        voter_id=voter_id,
        file_id=file_id,
        page_id=page_id,
        action=action,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        user_id=user,
    )
    session.add(entry)
    return entry


def save_part_metadata(session: Session, file_id: str, metadata) -> None:
    """Upsert the polling station and summary derived from a file's sheets.

    Replaces rather than accumulates: re-running extraction on a file must
    leave exactly one station and one summary for it, or the counts double
    every time the file is reprocessed.

    `metadata` is a `schemas.roll.PartMetadata`; it is not annotated here
    because importing it would make `db` depend on a service-layer schema
    that already imports `db`'s neighbours.
    """
    if session.get(FileRow, file_id) is None:
        logger.warning("File %s was deleted; skipping part metadata", file_id)
        return

    session.query(PollingStationRow).filter(
        PollingStationRow.file_id == file_id
    ).delete(synchronize_session=False)
    session.query(SummaryRow).filter(SummaryRow.file_id == file_id).delete(
        synchronize_session=False
    )

    station = metadata.station
    if station is not None:
        counts = station.counts
        station_id = uuid.uuid4().hex[:12]
        # Station imagery is cropped off the map sheet before any station
        # row exists, so the link is made here, once the station has an id.
        session.query(PhotoRow).filter(
            PhotoRow.file_id == file_id,
            PhotoRow.photo_type != "voter_crop",
        ).update({"polling_station_id": station_id}, synchronize_session=False)
        session.add(
            PollingStationRow(
                id=station_id,
                file_id=file_id,
                part_number=station.part_number,
                name=station.name,
                name_tam=station.name,
                building_name=station.name,
                section_details=station.section_details,
                total_electors=counts.total,
                male_electors=counts.male,
                female_electors=counts.female,
                third_gender_electors=counts.third_gender,
                ac_number=station.ac_number,
                ac_name=station.ac_name,
                pc_number=station.pc_number,
                pc_name=station.pc_name,
                station_number=station.station_number,
                station_type=station.station_type,
                address=station.address,
                district=station.district,
                taluk=station.taluk,
                pincode=station.pincode,
                serial_start=station.serial_start,
                serial_end=station.serial_end,
                source_page_id=station.source_page_id,
                payload=json.loads(station.model_dump_json()),
            )
        )

    summary = metadata.summary
    reconciliation = metadata.reconciliation
    if summary is not None or reconciliation.printed_total is not None:
        net = summary.net if summary else None
        session.add(
            SummaryRow(
                id=uuid.uuid4().hex[:12],
                file_id=file_id,
                total_voters=net.total if net else 0,
                male_count=net.male if net else 0,
                female_count=net.female if net else 0,
                third_gender_count=net.third_gender if net else 0,
                base_total=summary.base.total if summary else 0,
                additions_total=summary.additions.total if summary else 0,
                deletions_total=summary.deletions.total if summary else 0,
                corrections=summary.corrections if summary else 0,
                extracted_records=reconciliation.extracted_records,
                printed_total=reconciliation.printed_total,
                reconciled=reconciliation.matches,
                reconciliation_source=reconciliation.source,
                source_page_id=summary.source_page_id if summary else "",
                payload=json.loads(summary.model_dump_json()) if summary else {},
            )
        )


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


if _is_sqlite:
    @event.listens_for(engine, "begin")
    def _code_begin_immediate(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")
