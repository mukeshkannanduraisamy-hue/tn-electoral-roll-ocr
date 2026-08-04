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


# --- Regression tests added after review found two defects that only real
# data (not the fixtures above) exposed: a sign mismatch in permitted_numbers
# and a column-dropping bug in blocks_for for duplicate_epic rows. ---


def test_a_negative_magnitude_is_permitted_signed_and_unsigned():
    # `difference` fields (polling_station's, count_mismatch's) are
    # legitimately negative. `_DIGITS` extracts the *unsigned* run out of
    # prose, so a correct sentence written either way -- "-20" or "20 fewer"
    # -- must survive. Regression for a bug where only the signed string was
    # permitted and the natural unsigned phrasing was wrongly dropped.
    allowed = guards.permitted_numbers([{"difference": -20}])
    kept_unsigned, dropped_unsigned = guards.strip_unverified_numbers(
        "The count is 20 fewer than declared.", allowed
    )
    assert dropped_unsigned == 0
    kept_signed, dropped_signed = guards.strip_unverified_numbers(
        "The count is -20 relative to declared.", allowed
    )
    assert dropped_signed == 0
    # An unrelated invented figure is still caught.
    _, dropped_invented = guards.strip_unverified_numbers(
        "There are 900 more electors than declared.", allowed
    )
    assert dropped_invented == 1


def test_sign_direction_is_a_documented_limitation_not_desired_behaviour():
    # Pinned as a KNOWN GAP, not a feature: strip_unverified_numbers checks
    # that a magnitude came from a tool, not that a claim's direction is
    # true. A tool result of difference=-20 means "20 fewer than declared";
    # a sentence that flips this into "20 more" still passes, because both
    # sentences quote the same permitted magnitude, 20. See the guards.py
    # module docstring and permitted_numbers docstring for why a numeric
    # guard structurally cannot check sign-as-a-claim.
    allowed = guards.permitted_numbers([{"difference": -20}])
    _, dropped = guards.strip_unverified_numbers(
        "The roll has 20 more electors than declared.", allowed
    )
    assert dropped == 0  # documented limitation, not desired behaviour


def test_a_confidence_fraction_is_permitted_as_a_percentage():
    # quality.py stores mean/min confidence as 0-1 floats, but a spoken
    # answer naturally renders that as a percentage. Regression for a bug
    # where the whole sentence was dropped because only the raw fraction
    # ("0.897"), not its x100 rendering, was permitted.
    allowed = guards.permitted_numbers([{"mean_confidence": 0.897}])
    text = "Mean confidence is 89.7%."
    kept, dropped = guards.strip_unverified_numbers(text, allowed)
    assert kept == text
    assert dropped == 0
    # An invented percentage is still caught.
    _, dropped_invented = guards.strip_unverified_numbers(
        "Mean confidence is 99%.", allowed
    )
    assert dropped_invented == 1


def test_duplicate_epic_rows_keep_their_evidence_columns():
    # find_anomalies(kind="duplicate_epic") rows carry an `epic` key but are
    # OCR-record summaries, not electors -- they have no `id`. Regression
    # for a bug where blocks_for keyed elector-row detection off "epic"
    # alone, forcing these rows through the elector column allowlist and
    # silently dropping `occurrences`/`record_ids`, the fields that explain
    # the anomaly.
    result = {
        "rows": [
            {
                "epic": "IEB0142620",
                "occurrences": 2,
                "record_ids": ["a1", "a2"],
                "reason": "EPIC IEB0142620 was extracted onto 2 OCR records.",
            }
        ],
        "returned": 1,
    }
    made = blocks.blocks_for("find_anomalies", result)
    assert made[0]["columns"] == ["epic", "occurrences", "record_ids", "reason"]
    assert made[0]["rows"][0]["occurrences"] == 2
    assert made[0]["rows"][0]["record_ids"] == ["a1", "a2"]


def test_deeply_nested_results_do_not_crash():
    # A pathologically deep structure must stop being walked, not raise
    # RecursionError. Real tool results are only a few levels deep, so
    # this is purely a defensive bound.
    deep: dict = {"id": "v1", "epic": "X1"}
    for _ in range(2000):
        deep = {"child": deep}
    guards.permitted_numbers([deep])  # must not raise
    guards.collect_citations([deep])  # must not raise
