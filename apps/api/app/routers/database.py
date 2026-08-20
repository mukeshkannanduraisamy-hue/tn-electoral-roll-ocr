"""Read-only database introspection and query console.

Every endpoint is protected by ``require_user``.  The query endpoint
only permits SELECT and PRAGMA statements so the production data
cannot be modified through the viewer.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import settings
from ..db import UserRow, engine, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


from ..services.sqlite_views import ensure_sqlite_views

# Ensure SQLite views exist on startup
try:
    ensure_sqlite_views(engine)
except Exception as e:
    logger.warning("Could not auto-ensure sqlite views: %s", e)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class TableInfo(BaseModel):
    name: str
    row_count: int
    column_count: int
    type: str = "table"  # "table" | "view"


class ColumnInfo(BaseModel):
    name: str
    type: str
    pk: bool
    nullable: bool
    dflt_value: str | None


class IndexInfo(BaseModel):
    name: str
    unique: bool
    columns: list[str]


class RowsResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class QueryRequest(BaseModel):
    sql: str


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    duration_ms: float


class DbStats(BaseModel):
    sqlite_version: str
    file_size_bytes: int
    file_size_display: str
    table_count: int
    view_count: int
    index_count: int
    page_count: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_TABLE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_table_name(name: str) -> str:
    if not _SAFE_TABLE_RE.match(name):
        raise HTTPException(400, f"Invalid table/view name: {name}")
    inspector = inspect(engine)
    all_names = set(inspector.get_table_names()) | set(inspector.get_view_names())
    if name not in all_names:
        raise HTTPException(404, f"Table or View not found: {name}")
    return name


def _is_read_only(sql: str) -> bool:
    """Return True only if the SQL is a safe read-only statement."""
    stripped = sql.strip().rstrip(";").strip()
    # Remove leading comments
    stripped = re.sub(r"^(/\*.*?\*/|--[^\n]*\n)+", "", stripped, flags=re.DOTALL).strip()
    upper = stripped.upper()
    return upper.startswith("SELECT") or upper.startswith("PRAGMA") or upper.startswith("EXPLAIN")


def _format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DbStats)
def get_db_stats(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> DbStats:
    """Database-level statistics."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    views = inspector.get_view_names()

    index_count = 0
    for t in tables:
        index_count += len(inspector.get_indexes(t))

    # SQLite version
    version_row = session.execute(text("SELECT sqlite_version()")).fetchone()
    sqlite_version = version_row[0] if version_row else "unknown"

    # Page info
    page_count_row = session.execute(text("PRAGMA page_count")).fetchone()
    page_size_row = session.execute(text("PRAGMA page_size")).fetchone()
    page_count = page_count_row[0] if page_count_row else 0
    page_size = page_size_row[0] if page_size_row else 0

    # File size
    db_path = settings.data_dir / "ocr.sqlite"
    file_size = os.path.getsize(db_path) if db_path.exists() else 0

    return DbStats(
        sqlite_version=sqlite_version,
        file_size_bytes=file_size,
        file_size_display=_format_size(file_size),
        table_count=len(tables),
        view_count=len(views),
        index_count=index_count,
        page_count=page_count,
        page_size=page_size,
    )


@router.get("/tables", response_model=list[TableInfo])
def list_tables(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> list[TableInfo]:
    """List all tables and views with row counts."""
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    views = sorted(inspector.get_view_names())
    result: list[TableInfo] = []

    for name in tables:
        col_count = len(inspector.get_columns(name))
        row = session.execute(text(f'SELECT COUNT(*) FROM "{name}"')).fetchone()
        row_count = row[0] if row else 0
        result.append(TableInfo(name=name, row_count=row_count, column_count=col_count, type="table"))

    for name in views:
        try:
            col_count = len(inspector.get_columns(name))
            row = session.execute(text(f'SELECT COUNT(*) FROM "{name}"')).fetchone()
            row_count = row[0] if row else 0
        except Exception:
            col_count = 0
            row_count = 0
        result.append(TableInfo(name=name, row_count=row_count, column_count=col_count, type="view"))

    return result


@router.get("/tables/{table_name}/columns", response_model=list[ColumnInfo])
def get_columns(
    table_name: str,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> list[ColumnInfo]:
    """Column definitions for a table."""
    name = _validate_table_name(table_name)
    inspector = inspect(engine)
    columns = inspector.get_columns(name)
    pk_cols = inspector.get_pk_constraint(name).get("constrained_columns", [])
    return [
        ColumnInfo(
            name=c["name"],
            type=str(c["type"]),
            pk=c["name"] in pk_cols,
            nullable=c.get("nullable", True),
            dflt_value=str(c["default"]) if c.get("default") is not None else None,
        )
        for c in columns
    ]


@router.get("/tables/{table_name}/indexes", response_model=list[IndexInfo])
def get_indexes(
    table_name: str,
    _user: UserRow = Depends(require_user),
) -> list[IndexInfo]:
    """List indexes on a table."""
    name = _validate_table_name(table_name)
    inspector = inspect(engine)
    indexes = inspector.get_indexes(name)
    return [
        IndexInfo(
            name=idx["name"],
            unique=idx.get("unique", False),
            columns=idx.get("column_names", []),
        )
        for idx in indexes
    ]


@router.get("/tables/{table_name}/rows", response_model=RowsResponse)
def get_rows(
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort: str | None = Query(None),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    search: str | None = Query(None),
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> RowsResponse:
    """Paginated rows from a table."""
    name = _validate_table_name(table_name)
    inspector = inspect(engine)
    col_names = [c["name"] for c in inspector.get_columns(name)]

    # Build query
    where_clause = ""
    if search:
        # Search across all text-compatible columns
        conditions = []
        for col in col_names:
            conditions.append(f'CAST("{col}" AS TEXT) LIKE :search')
        if conditions:
            where_clause = "WHERE " + " OR ".join(conditions)

    # Count
    count_sql = f'SELECT COUNT(*) FROM "{name}" {where_clause}'
    params: dict[str, Any] = {}
    if search:
        params["search"] = f"%{search}%"
    total_row = session.execute(text(count_sql), params).fetchone()
    total = total_row[0] if total_row else 0

    # Sort
    order_clause = ""
    if sort and sort in col_names:
        direction = "DESC" if order == "desc" else "ASC"
        order_clause = f'ORDER BY "{sort}" {direction}'
    elif col_names:
        # Default: sort by first column
        order_clause = f'ORDER BY "{col_names[0]}" ASC'

    offset = (page - 1) * page_size
    data_sql = f'SELECT * FROM "{name}" {where_clause} {order_clause} LIMIT :limit OFFSET :offset'
    params["limit"] = page_size
    params["offset"] = offset

    rows_raw = session.execute(text(data_sql), params).fetchall()

    rows = []
    for r in rows_raw:
        row_dict: dict[str, Any] = {}
        for i, col in enumerate(col_names):
            val = r[i]
            # Truncate very long string values for display
            if isinstance(val, str) and len(val) > 500:
                row_dict[col] = val[:500] + "…"
            else:
                row_dict[col] = val
        rows.append(row_dict)

    return RowsResponse(
        columns=col_names,
        rows=rows,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/query", response_model=QueryResponse)
def execute_query(
    body: QueryRequest,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> QueryResponse:
    """Execute a read-only SQL query."""
    sql = body.sql.strip()
    if not sql:
        raise HTTPException(400, "Empty query")

    if not _is_read_only(sql):
        raise HTTPException(
            403,
            "Only SELECT, PRAGMA, and EXPLAIN statements are allowed. "
            "This is a read-only console.",
        )

    start = time.perf_counter()
    try:
        result = session.execute(text(sql))
        elapsed = (time.perf_counter() - start) * 1000

        # For PRAGMA statements that don't return column names nicely
        if result.returns_rows:
            keys = list(result.keys())
            rows_raw = result.fetchall()
            rows = [dict(zip(keys, row)) for row in rows_raw]
            return QueryResponse(
                columns=keys,
                rows=rows,
                row_count=len(rows),
                duration_ms=round(elapsed, 2),
            )
        else:
            return QueryResponse(
                columns=[],
                rows=[],
                row_count=0,
                duration_ms=round(elapsed, 2),
            )
    except Exception as exc:
        raise HTTPException(400, f"Query error: {exc}") from exc


@router.post("/tables/{name}/truncate")
def truncate_single_table(
    name: str,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    """Truncate / delete all rows from a specific database table."""
    name = _validate_table_name(name)
    if name.lower() in ("sqlite_master", "sqlite_sequence", "sqlite_stat1", "users"):
        raise HTTPException(400, f"Cannot truncate system/user table: {name}")
    try:
        session.execute(text(f"DELETE FROM {name};"))
        session.commit()
        logger.info("User %r truncated table %s", user.username, name)
        return {"status": "ok", "message": f"Table {name} truncated successfully."}
    except Exception as e:
        session.rollback()
        raise HTTPException(500, f"Failed to truncate table {name}: {e}") from e


@router.post("/truncate-all")
def truncate_all_database_tables(
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    """Truncate all data tables in the database."""
    tables = [
        "audit_logs", "ocr_blocks", "photos", "records", "summaries",
        "polling_stations", "pages", "files", "voters", "jobs"
    ]
    try:
        for t in tables:
            try:
                session.execute(text(f"DELETE FROM {t};"))
            except Exception:
                pass
        session.commit()
        logger.info("User %r truncated entire database", user.username)
        return {"status": "ok", "message": "All database tables truncated successfully."}
    except Exception as e:
        session.rollback()
        raise HTTPException(500, f"Database truncation failed: {e}") from e
