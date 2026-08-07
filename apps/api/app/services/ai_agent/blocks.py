"""Tool result → what the panel renders.

Deliberately not the model's job. Asking a language model to emit a table is
asking it to retype data it was just given, and a retyped table is a table with
a typo in it. The model writes the prose; the rows come straight from the tool.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

#: Column order for elector tables. Anything not listed is dropped, so a tool
#: that starts returning a new field does not silently widen the table.
_VOTER_COLUMNS = (
    "name", "epic", "age", "gender", "relation_name",
    "house_number", "part_number", "verified",
)

_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def _scrub_rationale(text: str) -> str:
    """Strip every figure out of the model's one-line reason for a query.

    `rationale` (`RunSqlArgs.rationale`) is free prose the model wrote, not a
    tool result -- unlike the `sql` string rendered beside it, where showing
    the operator the exact query *is* the point and it stays verbatim. A
    caption like "Counting the 4,120 electors in part 289" puts an
    unguarded, possibly fabricated figure next to an answer the operator has
    otherwise been told is fully verified.

    Not routed through `guards.strip_unverified_numbers`: that check drops a
    *sentence* whole when it quotes a figure no tool produced, calibrated for
    the model's prose answer. A rationale is a caption, not the answer -- and
    even a figure that happens to be real is still unverified *at this call
    site* (nothing here checks it against `tool_results`), so every digit run
    goes, not just the ones that would fail the sentence-level guard.
    """
    scrubbed = _DIGITS.sub("#", text or "")
    return re.sub(r"\s{2,}", " ", scrubbed).strip()


def _table(rows: List[Dict[str, Any]], columns: List[str], **extra: Any) -> Dict[str, Any]:
    return {
        "kind": "table",
        "columns": columns,
        "rows": [{c: row.get(c) for c in columns} for row in rows],
        **extra,
    }


def blocks_for(tool_name: str, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The render blocks one tool result produces. Never more than two."""
    if tool_name == "aggregate":
        chart = result.get("infographic")
        return [{"kind": "chart", "infographic": chart}] if chart else []

    if tool_name == "get_voter":
        return [
            {
                "kind": "voter_card",
                "voter": result.get("voter") or {},
                "provenance": result.get("provenance") or {},
                "ocr_fields": result.get("ocr_fields") or [],
            }
        ]

    if tool_name == "run_readonly_sql":
        rows = result.get("rows") or []
        columns = result.get("columns") or []
        made: List[Dict[str, Any]] = [
            {
                "kind": "sql",
                "sql": result.get("sql", ""),
                "rationale": _scrub_rationale(result.get("rationale", "")),
                "returned": result.get("returned", len(rows)),
            }
        ]
        if rows:
            made.append(_table(rows, list(columns)))
        return made

    rows = result.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        first = rows[0]
        # An elector row is identified the same way `guards.collect_citations`
        # identifies one: both `id` and `epic` present. Checking `epic` alone
        # would also catch rows like `find_anomalies(kind="duplicate_epic")`,
        # which carry an `epic` string but are OCR-record summaries, not
        # electors — forcing them through `_VOTER_COLUMNS` would silently drop
        # their `occurrences` and `record_ids` fields.
        if "id" in first and "epic" in first:
            columns = [c for c in _VOTER_COLUMNS if c in first]
            if "reason" in first:
                columns = columns + ["reason"]
        else:
            columns = list(first.keys())[:8]
        return [
            _table(
                rows,
                columns,
                total=result.get("total"),
                truncated=bool(result.get("truncated")),
            )
        ]

    for key in ("files", "pages", "jobs"):
        listed = result.get(key)
        if isinstance(listed, list) and listed and isinstance(listed[0], dict):
            return [_table(listed, list(listed[0].keys())[:8])]

    return []
