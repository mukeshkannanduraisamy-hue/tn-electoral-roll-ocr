"""A read-only SQL escape hatch, for the questions the typed tools do not cover.

Layered on purpose. A regex parser can be fooled, so it is not the only thing
standing between the model and the database:

1.  Reject anything that is not a single SELECT or WITH.
2.  Reject comments outright — they are how keyword scans get defeated.
3.  Require every referenced table to be on an allowlist. Not a denylist: a
    denylist is a list of the attacks someone thought of.
4.  Install SQLite's own authorizer, which vetoes any read of a table outside
    the allowlist. This is the real boundary. Layer 3 reads *text*, and text
    can always be arranged to hide a table from a regex — `FROM voters,
    app_settings` slipped past an earlier version of this file precisely that
    way, because a pattern anchored on FROM/JOIN cannot enumerate a
    comma-separated list. The authorizer fires on the compiled query plan
    instead, so it sees every table SQLite actually resolved, whatever the
    source text looked like.
5.  Execute on a connection opened read-only at the OS level, so a bypass of
    1-4 still cannot write.
6.  Cap rows and wall-clock time.

Layer 3 is kept even though layer 4 subsumes it: it refuses a bad statement
before the database is opened, and it can say *which* table was refused and
what the alternatives are, which a bare authorizer denial cannot.

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
#:
#: `(?:\s|\()*` (not `\s+`) between the keyword and an optional quote/bracket:
#: SQLite's tokenizer needs neither whitespace nor a bare identifier there --
#: `FROM[app_settings]`, `FROM"app_settings"`, `` FROM`x` `` and even a bare
#: name wrapped in redundant parens, `FROM(app_settings)` / `FROM (( x ))`, all
#: parse and execute. Requiring `\s+` and no parens let that whole class slip
#: past this check while still running. The trailing `\b` on the keyword
#: itself stops "FROMx" (one fused identifier, not actually a FROM clause at
#: all) from being misread as a match. Whitespace is deliberately NOT allowed
#: between a quote/bracket and the identifier: for a quoted or bracketed name
#: that space is part of the literal identifier, so `FROM[ app_settings ]`
#: does not resolve to the real table anyway -- SQLite raises "no such table"
#: for it -- and is safely left uncaptured here.
_TABLE_REF = re.compile(
    r"\b(?:from|join)\b(?:\s|\()*[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE
)
#: A subquery hiding behind redundant parens -- `FROM ((SELECT ...))` -- makes
#: the pattern above capture the leading keyword of the subquery itself
#: ("select"/"with") as if it were a table name. Neither is ever a legal bare
#: table name, so dropping them from the referenced set is free of risk.
_NOT_A_TABLE = frozenset({"select", "with"})
#: Names introduced by a CTE are not real tables and must not be allowlisted.
_CTE_NAME = re.compile(r"(?:\bwith\s+|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", re.IGNORECASE)

#: Tables that exist but must never be reachable, named explicitly so a CTE
#: cannot alias-shadow them (see `guard_sql`'s reserved-name check below).
_FORBIDDEN_TABLES = frozenset({"app_settings", "users", "sessions"})

#: SQLite functions that must not be callable. load_extension is obvious; the
#: others read/write the filesystem or manipulate the database at dangerous
#: levels: readfile and writefile do I/O; fts3_tokenizer, edit, and sqlite_dbpage
#: expose internal APIs; zipfile performs archive manipulation. This is a
#: targeted denylist layered inside _PERMITTED_ACTIONS, which is already
#: restrictive.
_DENIED_FUNCTIONS = frozenset(
    {"load_extension", "readfile", "writefile", "fts3_tokenizer", "edit", "zipfile", "sqlite_dbpage"}
)

#: Where a FROM clause stops. Needed to find comma-separated table lists, which
#: `_TABLE_REF` cannot see: it anchors on the FROM/JOIN keyword, so in
#: `FROM voters, app_settings` it captures `voters` and stops. That gap was a
#: live bypass to the API key table before the authorizer was added.
_CLAUSE_END = re.compile(
    r"\b(where|group|order|limit|having|union|intersect|except|on|using|window)\b",
    re.IGNORECASE,
)
_FROM_OR_JOIN = re.compile(r"\b(?:from|join)\b", re.IGNORECASE)
#: Leading identifier of one comma-separated entry, past any parens or quoting.
_LEADING_NAME = re.compile(r"^[\s(]*[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)")


def _comma_separated_tables(statement: str) -> set:
    """Table names in a comma-separated FROM list, which `_TABLE_REF` misses."""
    found = set()
    for keyword in _FROM_OR_JOIN.finditer(statement):
        tail = statement[keyword.end():]
        stop = _CLAUSE_END.search(tail)
        clause = tail[: stop.start()] if stop else tail

        segments: List[str] = []
        current: List[str] = []
        depth = 0
        for char in clause:
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            if char == "," and depth == 0:
                segments.append("".join(current))
                current = []
            else:
                current.append(char)
        segments.append("".join(current))

        for segment in segments:
            name = _LEADING_NAME.match(segment)
            if name:
                found.add(name.group(1).lower())
    return found


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
    shadowed = cte_names & (ALLOWED_TABLES | _FORBIDDEN_TABLES)
    if shadowed:
        # A CTE named exactly like a real table is excluded, by name, from the
        # allowlist check below -- for *every* occurrence of that name in the
        # statement, not just the CTE's own reference to itself. That would
        # normally still be safe (SQL scoping means a CTE's name shadows the
        # real table for the rest of the statement, so it cannot actually
        # launder a read of the real one), but it depends on engine behaviour
        # this guard has no business relying on. Simplest fix: never allow it.
        raise SqlGuardError(
            f"A WITH name may not reuse a real table name ({', '.join(sorted(shadowed))!r}); "
            "pick a different alias."
        )

    referenced = (
        {name.lower() for name in _TABLE_REF.findall(statement)}
        | _comma_separated_tables(statement)
    ) - _NOT_A_TABLE
    for table in sorted(referenced - cte_names):
        if table not in ALLOWED_TABLES:
            raise SqlGuardError(
                f"The table {table!r} is not available to the assistant. "
                f"Readable tables: {', '.join(sorted(ALLOWED_TABLES))}."
            )

    return f"SELECT * FROM (\n{statement}\n) LIMIT {ROW_LIMIT}"


#: Actions the assistant's connection may perform at all. Everything else —
#: attaching a database, reading a pragma, opening a transaction, creating a
#: temp table — is denied outright, so the authorizer is an allowlist in the
#: same spirit as ALLOWED_TABLES.
_PERMITTED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
)


def _authorizer(action: int, arg1, arg2, _db, _trigger) -> int:
    """SQLite's own veto, consulted while the statement is compiled.

    This is what makes the table allowlist real. `guard_sql` reads the query as
    text and can be out-argued by it; this sees the resolved query plan. Every
    table SQLite intends to read arrives here by name, whether it was written
    after FROM, after a comma, inside a subquery, behind an alias, or reached
    through a view.
    """
    if action not in _PERMITTED_ACTIONS:
        return sqlite3.SQLITE_DENY

    if action == sqlite3.SQLITE_READ:
        # arg1 is the table; arg2 the column. A subquery's synthesised name
        # arrives with arg1 empty, which is not a real table and is fine.
        table = (arg1 or "").lower()
        if table and table not in ALLOWED_TABLES:
            logger.warning(
                "SQLite authorizer denied a read of %r (column %r)", arg1, arg2
            )
            return sqlite3.SQLITE_DENY

    if action == sqlite3.SQLITE_FUNCTION:
        # arg2 is the function name. Deny dangerous functions case-insensitively.
        func_name = (arg2 or "").lower()
        if func_name in _DENIED_FUNCTIONS:
            logger.warning("SQLite authorizer denied function call to %r", arg2)
            return sqlite3.SQLITE_DENY

    return sqlite3.SQLITE_OK


def _readonly_connection() -> sqlite3.Connection:
    """A connection the operating system will not let us write through.

    Belt and braces. If the parser above were ever bypassed, this is what still
    stands between a crafted statement and the database.
    """
    url = database_url()
    if not url.startswith("sqlite"):
        raise SqlGuardError(
            "The SQL tool is available only on SQLite deployments. "
            "Use the typed tools instead."
        )

    # Extract the path from the URL. The standard form is sqlite:///path,
    # where /// is the prefix for an absolute path. Strip any query string.
    if url.startswith("sqlite:///"):
        # Remove the sqlite:// prefix, leaving /path (or drive:path on Windows).
        path_with_query = url[10:]  # len("sqlite:///") == 10, but one slash stays
    else:
        raise SqlGuardError(
            f"Could not parse the database URL: expected sqlite:/// prefix, got {url!r}"
        )

    # Strip query string if present.
    path_str = path_with_query.split("?")[0]
    if not path_str:
        raise SqlGuardError(
            f"Could not parse the database URL: no path after sqlite:/// prefix in {url!r}"
        )

    conn = sqlite3.connect(f"file:{path_str}?mode=ro", uri=True, timeout=TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.set_authorizer(_authorizer)

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
    except sqlite3.DatabaseError as exc:
        # An authorizer veto arrives here too. Report it as a refusal rather
        # than a malfunction: the statement was understood and declined, and
        # the operator should see which table the assistant reached for.
        if "not authorized" in str(exc) or "prohibited" in str(exc):
            logger.warning("Authorizer refused an assistant query: %s", exc)
            raise SqlGuardError(
                f"The query was refused: {exc}. Readable tables: "
                f"{', '.join(sorted(ALLOWED_TABLES))}."
            ) from exc
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
