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
