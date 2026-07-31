"""A read-only SQL escape hatch, for the questions the typed tools do not cover.

Layered on purpose. A regex parser can be fooled, so it is not the only thing
standing between the model and the database:

1.  Reject anything that is not a single SELECT or WITH.
2.  Reject comments outright — they are how keyword scans get defeated.
3.  Require every referenced table to be on an allowlist. Not a denylist: a
    denylist is a list of the attacks someone thought of.
4.  Execute on a connection opened read-only at the OS level, so a bypass of
    1-3 still cannot write.
5.  Cap rows and wall-clock time.

`app_settings` is excluded because it stores the NVIDIA API key. An assistant
able to select its own credentials out of the database is one prompt away from
printing them into a chat transcript.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....config import settings
from ....db import database_url
from ..registry import ToolError, register

logger = logging.getLogger(__name__)

#: Everything the assistant may read. Adding a table here is a deliberate act.
ALLOWED_TABLES = frozenset(
    {
        "voters",
        "records",
        "pages",
        "files",
        "polling_stations",
        "photos",
        "ocr_blocks",
        "jobs",
        "summaries",
        "audit_logs",
    }
)

ROW_LIMIT = 200
TIMEOUT_SECONDS = 5.0

_FORBIDDEN_KEYWORD = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|"
    r"vacuum|reindex|begin|commit|rollback|truncate|grant|revoke)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--|/\*|\*/|#)")
#: Every position a table name can appear in a SELECT we accept.
_TABLE_REF = re.compile(r"\b(?:from|join)\s+[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
#: Names introduced by a CTE are not real tables and must not be allowlisted.
_CTE_NAME = re.compile(r"(?:\bwith\s+|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", re.IGNORECASE)


class SqlGuardError(ToolError):
    """The statement was refused. The reason is shown to the operator."""


def guard_sql(raw: str) -> str:
    """Validate a statement and return the wrapped, row-limited form.

    Raises `SqlGuardError` with a reason the operator can read. The reason is
    deliberately specific: "not available" for a forbidden table tells them the
    assistant tried, and what it tried, which is information they should have.
    """
    statement = (raw or "").strip()
    if not statement:
        raise SqlGuardError("No SQL was provided.")

    if _COMMENT.search(statement):
        raise SqlGuardError("SQL comments are not allowed.")

    statement = statement.rstrip(";").strip()
    if ";" in statement:
        raise SqlGuardError("Only one statement may be run at a time.")

    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        raise SqlGuardError("Only a SELECT (or WITH … SELECT) may be run.")

    forbidden = _FORBIDDEN_KEYWORD.search(statement)
    if forbidden:
        raise SqlGuardError(
            f"{forbidden.group(1).upper()} is not permitted; this tool is read-only."
        )

    cte_names = {name.lower() for name in _CTE_NAME.findall(statement)}
    referenced = {name.lower() for name in _TABLE_REF.findall(statement)}
    for table in sorted(referenced - cte_names):
        if table not in ALLOWED_TABLES:
            raise SqlGuardError(
                f"The table {table!r} is not available to the assistant. "
                f"Readable tables: {', '.join(sorted(ALLOWED_TABLES))}."
            )

    return f"SELECT * FROM (\n{statement}\n) LIMIT {ROW_LIMIT}"


def _readonly_connection() -> sqlite3.Connection:
    """A connection the operating system will not let us write through.

    Belt and braces. If the parser above were ever bypassed, this is what still
    stands between a crafted statement and the database.
    """
    if not database_url().startswith("sqlite"):
        raise SqlGuardError(
            "The SQL tool is available only on SQLite deployments. "
            "Use the typed tools instead."
        )

    path = (settings.data_dir / "ocr.sqlite").as_posix()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row

    deadline = time.monotonic() + TIMEOUT_SECONDS

    def _abort_when_out_of_time() -> int:
        # A non-zero return aborts the query.
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(_abort_when_out_of_time, 10_000)
    return conn


class RunSqlArgs(BaseModel):
    sql: str = Field(..., description="A single SELECT or WITH … SELECT statement")
    rationale: str = Field(
        ..., description="One sentence: what this query is for. Shown to the operator."
    )


@register(
    name="run_readonly_sql",
    description=(
        "Run one read-only SELECT when no other tool can answer the question. "
        f"Readable tables: {', '.join(sorted(ALLOWED_TABLES))}. Results are "
        f"capped at {ROW_LIMIT} rows — if the answer says exactly {ROW_LIMIT} "
        "rows came back, treat that as a possible truncation (check the "
        "`truncated` flag) rather than the true count; use COUNT(*) to get an "
        "exact total. The SQL is shown to the operator. Prefer a typed tool "
        "whenever one fits."
    ),
    args_model=RunSqlArgs,
    label="Running SQL",
)
def run_readonly_sql(_session: Session, args: RunSqlArgs) -> Dict[str, Any]:
    guarded = guard_sql(args.sql)

    conn = _readonly_connection()
    try:
        cursor = conn.execute(guarded)
        fetched = cursor.fetchall()
        columns: List[str] = [d[0] for d in (cursor.description or [])]
    except sqlite3.OperationalError as exc:
        raise SqlGuardError(f"The query could not run: {exc}") from exc
    finally:
        conn.close()

    rows = [dict(zip(columns, tuple(row))) for row in fetched]
    logger.info("Assistant SQL (%s) returned %d rows", args.rationale[:80], len(rows))

    return {
        "sql": args.sql.strip(),
        "rationale": args.rationale,
        "columns": columns,
        "rows": rows,
        "returned": len(rows),
        "truncated": len(rows) >= ROW_LIMIT,
    }
