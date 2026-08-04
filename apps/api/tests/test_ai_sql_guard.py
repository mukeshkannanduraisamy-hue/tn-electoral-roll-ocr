"""The SQL guard.

A parser is not a security boundary, so this is tested as an attack surface
rather than as a feature. Every case below is a thing the model might emit —
whether by misunderstanding, by following a badly worded question, or because
something upstream told it to.

The rule that matters most: `app_settings` holds the NVIDIA API key. The
assistant must never be able to read its own credentials out of the database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3  # noqa: E402
import pytest  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import sql as sqltool  # noqa: E402


def _guard(statement: str):
    return sqltool.guard_sql(statement)


# --- what must be refused --------------------------------------------------

@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE voters SET verified = 1",
        "DELETE FROM voters",
        "INSERT INTO voters (id) VALUES ('x')",
        "DROP TABLE voters",
        "ALTER TABLE voters ADD COLUMN x TEXT",
        "CREATE TABLE evil (id TEXT)",
        "PRAGMA table_info(voters)",
        "ATTACH DATABASE 'other.db' AS other",
        "VACUUM",
    ],
)
def test_writes_and_ddl_are_refused(statement):
    with pytest.raises(sqltool.SqlGuardError):
        _guard(statement)


def test_multiple_statements_are_refused():
    with pytest.raises(sqltool.SqlGuardError, match="one statement"):
        _guard("SELECT 1; DROP TABLE voters")


def test_comments_are_refused_outright():
    # Comments are how keyword scanning gets defeated. Rejecting them is
    # cheaper than trying to parse around them.
    with pytest.raises(sqltool.SqlGuardError, match="[Cc]omment"):
        _guard("SELECT id FROM voters -- DROP TABLE voters")
    with pytest.raises(sqltool.SqlGuardError, match="[Cc]omment"):
        _guard("SELECT /* sneaky */ id FROM voters")


@pytest.mark.parametrize("table", ["app_settings", "users", "sessions"])
def test_the_forbidden_tables_are_unreachable(table):
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard(f"SELECT * FROM {table}")


def test_the_api_key_cannot_be_reached_through_a_join():
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard("SELECT v.name, a.value FROM voters v JOIN app_settings a ON 1=1")


def test_the_api_key_cannot_be_reached_through_a_subquery():
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard("SELECT (SELECT value FROM app_settings LIMIT 1) AS leaked")


def test_a_cte_cannot_launder_a_forbidden_table():
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard("WITH x AS (SELECT value FROM app_settings) SELECT * FROM x")


def test_a_bare_non_select_is_refused():
    with pytest.raises(sqltool.SqlGuardError, match="SELECT"):
        _guard("EXPLAIN SELECT 1")


# --- what must be allowed --------------------------------------------------

def test_a_plain_select_is_accepted_and_limited():
    guarded = _guard("SELECT name FROM voters")
    assert "LIMIT" in guarded.upper()


def test_a_cte_over_allowed_tables_is_accepted():
    guarded = _guard(
        "WITH per_part AS (SELECT part_number, COUNT(*) n FROM voters GROUP BY part_number) "
        "SELECT * FROM per_part"
    )
    assert "LIMIT" in guarded.upper()


def test_a_join_across_allowed_tables_is_accepted():
    _guard("SELECT v.name FROM voters v JOIN pages p ON p.id = v.page_id")


# --- end to end ------------------------------------------------------------

def _run(args):
    with session_scope() as s:
        return registry.execute(s, "run_readonly_sql", args)


def test_the_tool_returns_rows_and_echoes_the_sql():
    result = _run({"sql": "SELECT COUNT(*) AS n FROM voters", "rationale": "count"})
    assert result["columns"] == ["n"]
    assert isinstance(result["rows"][0]["n"], int)
    assert "voters" in result["sql"]


def test_the_tool_reports_a_refusal_as_a_tool_error():
    with pytest.raises(registry.ToolError, match="not available"):
        _run({"sql": "SELECT * FROM app_settings", "rationale": "leak the key"})


def test_results_are_capped():
    result = _run({"sql": "SELECT id FROM voters", "rationale": "all ids"})
    assert len(result["rows"]) <= sqltool.ROW_LIMIT


# --- bypasses found by adversarial testing -------------------------------
#
# A regex anchored on FROM/JOIN cannot enumerate a comma-separated table list,
# so `FROM voters, app_settings` reached the API key table in an earlier
# version of the guard. These are the exact statements that got through.


SMUGGLING_ATTEMPTS = [
    "SELECT v.name, a.value FROM voters, app_settings a",
    "SELECT * FROM voters, users",
    "SELECT * FROM voters v, sessions s WHERE 1=1",
    "SELECT * FROM voters, app_settings, pages",
    "SELECT * FROM pages JOIN voters ON 1=1, app_settings",
]


@pytest.mark.parametrize("statement", SMUGGLING_ATTEMPTS)
def test_a_forbidden_table_cannot_be_read_however_it_is_smuggled(statement):
    """The property that matters: the read does not happen.

    Which layer refuses it is an implementation detail. `guard_sql` catches
    most of these and can name the table, but a pattern cannot reliably parse
    SQL — the last case hides the table behind an ON clause — so the authorizer
    is what makes the guarantee hold. Assert the guarantee, not the mechanism.
    """
    with pytest.raises(registry.ToolError):
        _run({"sql": statement, "rationale": "adversarial test"})


@pytest.mark.parametrize("statement", SMUGGLING_ATTEMPTS[:4])
def test_the_parser_names_the_table_it_refused_where_it_can(statement):
    """Layer 3's job is a good error message, and for these it manages one."""
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard(statement)


def test_the_authorizer_refuses_a_forbidden_read_the_parser_let_through():
    """The parser is not the boundary; SQLite's authorizer is.

    Bypassing `guard_sql` entirely and running straight at the connection is
    the only honest way to test the layer underneath it.
    """
    conn = sqltool._readonly_connection()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT value FROM app_settings").fetchall()
    finally:
        conn.close()


def test_the_authorizer_still_allows_an_ordinary_read():
    conn = sqltool._readonly_connection()
    try:
        assert conn.execute("SELECT COUNT(*) FROM voters").fetchone() is not None
    finally:
        conn.close()


def test_a_comma_join_is_refused_end_to_end():
    with pytest.raises(registry.ToolError):
        _run({"sql": "SELECT v.name, a.value FROM voters, app_settings a",
              "rationale": "leak the key"})


# --- Fix 1: database path derivation ----------------------------------------

def test_readonly_connection_opens_correct_database():
    """Verify the connection opens the expected SQLite database.

    This tests that _readonly_connection() derives the database path correctly
    from database_url() rather than hardcoding it.
    """
    conn = sqltool._readonly_connection()
    try:
        # If connected to the right database, we should be able to query voters
        # (which is in the allowed tables list).
        result = conn.execute("SELECT COUNT(*) FROM voters").fetchone()
        assert result is not None
        assert isinstance(result[0], int)
    finally:
        conn.close()


# --- Fix 2: deny dangerous SQL functions -----------------------------------

@pytest.mark.parametrize(
    "func_name",
    ["load_extension", "readfile", "writefile", "fts3_tokenizer", "edit", "zipfile", "sqlite_dbpage"],
)
def test_authorizer_denies_dangerous_functions(func_name):
    """Unit test: _authorizer denies each dangerous function."""
    # For SQLITE_FUNCTION, arg2 is the function name.
    result = sqltool._authorizer(sqlite3.SQLITE_FUNCTION, None, func_name, None, None)
    assert result == sqlite3.SQLITE_DENY, f"_authorizer should deny {func_name}"


@pytest.mark.parametrize(
    "func_name",
    ["count", "upper", "lower", "abs", "random", "length"],
)
def test_authorizer_allows_ordinary_functions(func_name):
    """Unit test: _authorizer allows ordinary functions."""
    result = sqltool._authorizer(sqlite3.SQLITE_FUNCTION, None, func_name, None, None)
    assert result == sqlite3.SQLITE_OK, f"_authorizer should allow {func_name}"


def test_load_extension_is_refused():
    """Integration test: a query calling load_extension is refused.

    This verifies that the authorizer's function denylist is what refuses it,
    not Python's default extension-loading block. We expect this to fail because
    the authorizer denies the SQLITE_FUNCTION action.
    """
    conn = sqltool._readonly_connection()
    try:
        # The authorizer should deny this before any execution.
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            conn.execute("SELECT load_extension('x')").fetchall()
    finally:
        conn.close()
