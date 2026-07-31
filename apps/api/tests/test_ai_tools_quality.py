"""Data-quality tools.

These answer the question the workspace cannot currently ask: not "how many
electors are there" but "which of these records should I not believe".
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import quality  # noqa: F401,E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def sample_part():
    """One good record, one with an impossible age, one missing its gender."""
    with session_scope() as s:
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000001", name="Good Record",
                age=45, gender="Male", house_number="12", part_number=PART, search_text="good",
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000002", name="Impossible Age",
                age=3, gender="Female", house_number="14", part_number=PART, search_text="impossible",
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000003", name="No Gender",
                age=30, gender="", part_number=PART, search_text="nogender",
            )
        )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_implausible_age_flags_only_the_child(sample_part):
    rows = _run("find_anomalies", {"kind": "implausible_age", "part_number": sample_part})["rows"]
    assert [r["epic"] for r in rows] == ["TNAQ0000002"]
    assert rows[0]["reason"]


def test_missing_field_flags_the_blank_gender(sample_part):
    rows = _run("find_anomalies", {"kind": "missing_field", "part_number": sample_part})["rows"]
    assert [r["epic"] for r in rows] == ["TNAQ0000003"]


def test_anomaly_rows_are_citable(sample_part):
    rows = _run("find_anomalies", {"kind": "implausible_age", "part_number": sample_part})["rows"]
    assert "id" in rows[0] and "epic" in rows[0]


def test_unknown_anomaly_kind_is_refused():
    with pytest.raises(registry.ToolError, match="Invalid arguments"):
        _run("find_anomalies", {"kind": "bad_vibes"})


def test_ocr_quality_for_a_part_reports_a_population(sample_part):
    result = _run("ocr_quality", {"scope": "part", "id": sample_part})
    assert result["population"] == 3
    assert "mean_confidence" in result


def test_low_confidence_records_respects_its_limit():
    result = _run("low_confidence_records", {"limit": 5})
    assert len(result["rows"]) <= 5
