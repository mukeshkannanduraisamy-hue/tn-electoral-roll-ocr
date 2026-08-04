"""The guards that make the assistant's answers checkable.

`infographic.py` established the rule: the model does not produce numbers. The
agent widens the aperture — the model may now quote any figure a tool returned —
without widening the licence. Anything else still goes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai_agent import blocks, guards  # noqa: E402

TOOL_RESULTS = [
    {
        "rows": [
            {"id": "v1", "epic": "TNAI0000001", "name": "Muthu Vel", "age": 72},
            {"id": "v2", "epic": "TNAI0000002", "name": "Kamala Devi", "age": 53},
        ],
        "total": 412,
    }
]


def test_numbers_from_tool_results_are_permitted():
    allowed = guards.permitted_numbers(TOOL_RESULTS)
    assert "412" in allowed and "72" in allowed


def test_a_sentence_quoting_a_real_figure_survives():
    text = "There are 412 electors in this part."
    kept, dropped = guards.strip_unverified_numbers(text, guards.permitted_numbers(TOOL_RESULTS))
    assert kept == text
    assert dropped == 0


def test_a_sentence_quoting_an_invented_figure_is_dropped():
    text = "There are 412 electors. Roughly 900 of them are women."
    kept, dropped = guards.strip_unverified_numbers(text, guards.permitted_numbers(TOOL_RESULTS))
    assert "900" not in kept
    assert "412" in kept
    assert dropped == 1


def test_numbers_inside_identifiers_are_permitted():
    # An EPIC contains digits and is not a claim about quantity.
    allowed = guards.permitted_numbers(TOOL_RESULTS)
    text = "Muthu Vel holds EPIC TNAI0000001."
    kept, dropped = guards.strip_unverified_numbers(text, allowed)
    assert dropped == 0


def test_citations_are_collected_from_any_nesting_depth():
    known = guards.collect_citations(TOOL_RESULTS)
    assert set(known) == {"v1", "v2"}
    assert known["v1"]["name"] == "Muthu Vel"


def test_a_known_marker_is_kept_and_reported():
    known = guards.collect_citations(TOOL_RESULTS)
    text, cited = guards.bind_citations("See [[v:v1]] for the household.", known)
    assert "[[v:v1]]" in text
    assert [c["id"] for c in cited] == ["v1"]


def test_an_invented_marker_is_stripped():
    known = guards.collect_citations(TOOL_RESULTS)
    text, cited = guards.bind_citations("See [[v:ghost]] and [[v:v2]].", known)
    assert "ghost" not in text
    assert [c["id"] for c in cited] == ["v2"]


def test_search_results_become_a_table_block():
    made = blocks.blocks_for("search_voters", TOOL_RESULTS[0])
    assert made[0]["kind"] == "table"
    assert "name" in made[0]["columns"]


def test_an_aggregate_becomes_a_chart_block():
    made = blocks.blocks_for("aggregate", {"infographic": {"title": "Electors", "series": []}})
    assert made[0]["kind"] == "chart"
    assert made[0]["infographic"]["title"] == "Electors"


def test_sql_results_become_a_sql_block_and_a_table():
    made = blocks.blocks_for(
        "run_readonly_sql",
        {"sql": "SELECT 1", "columns": ["n"], "rows": [{"n": 1}], "rationale": "why"},
    )
    kinds = [b["kind"] for b in made]
    assert kinds == ["sql", "table"]
