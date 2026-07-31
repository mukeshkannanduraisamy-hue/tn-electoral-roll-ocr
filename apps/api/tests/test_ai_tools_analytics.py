"""The aggregate tool is a thin, validating wrapper over infographic.py.

It must not become a second implementation of the metric vocabulary: the
guarantee that a chart's numbers came from SQL lives in one module, and that is
where it stays.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import analytics  # noqa: F401,E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def sample_part():
    with session_scope() as s:
        for i, (gender, age) in enumerate(
            [("Male", 40), ("Male", 60), ("Female", 30)]
        ):
            s.add(
                VoterRow(
                    id=uuid.uuid4().hex[:32],
                    epic=f"TNAG{i:07d}",
                    name=f"Person {i}",
                    age=age,
                    gender=gender,
                    part_number=PART,
                    search_text=f"person {i} {PART}".lower(),
                )
            )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)


def _run(args):
    with session_scope() as s:
        return registry.execute(s, "aggregate", args)


def test_counts_come_from_sql(sample_part):
    result = _run({"metric": "voter_count", "filters": {"part_number": sample_part}})
    assert result["infographic"]["total"] == 3


def test_breakdown_returns_a_series(sample_part):
    chart = _run(
        {
            "metric": "voter_count",
            "dimension": "gender",
            "filters": {"part_number": sample_part},
        }
    )["infographic"]
    assert {p["label"]: p["value"] for p in chart["series"]} == {"Male": 2, "Female": 1}


def test_an_unknown_metric_is_refused_with_the_vocabulary(sample_part):
    with pytest.raises(registry.ToolError) as exc:
        _run({"metric": "vibes"})
    assert "voter_count" in str(exc.value)


def test_the_tool_description_lists_the_metric_keys():
    assert "voter_count" in registry.REGISTRY["aggregate"].description
