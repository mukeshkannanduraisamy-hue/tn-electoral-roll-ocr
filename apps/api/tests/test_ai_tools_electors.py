"""Elector lookup tools.

The fixture population lives in its own part so counts are exact regardless of
what else is in the development database — the same approach as
`test_infographic.py`.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import electors  # noqa: F401,E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"
PEOPLE = [
    ("Muthu Vel", "TNAI0000001", 72, "Male", "12"),
    ("Kamala Devi", "TNAI0000002", 53, "Female", "12"),
    ("Divya R", "TNAI0000003", 25, "Female", "44"),
]


@pytest.fixture(scope="module")
def sample_part():
    with session_scope() as s:
        for name, epic, age, gender, house in PEOPLE:
            s.add(
                VoterRow(
                    id=uuid.uuid4().hex[:32],
                    epic=epic,
                    name=name,
                    age=age,
                    gender=gender,
                    house_number=house,
                    part_number=PART,
                    constituency="Test Constituency",
                    search_text=f"{name} {epic} {house} {PART}".lower(),
                )
            )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_search_filters_to_the_part(sample_part):
    result = _run("search_voters", {"part_number": sample_part})
    assert result["total"] == 3
    assert {r["epic"] for r in result["rows"]} == {e for _, e, _, _, _ in PEOPLE}


def test_search_rows_carry_the_fields_a_citation_needs(sample_part):
    row = _run("search_voters", {"part_number": sample_part})["rows"][0]
    for key in ("id", "epic", "name", "part_number"):
        assert key in row


def test_search_honours_the_limit(sample_part):
    assert len(_run("search_voters", {"part_number": sample_part, "limit": 2})["rows"]) == 2


def test_search_by_gender_and_age(sample_part):
    result = _run(
        "search_voters", {"part_number": sample_part, "gender": "Female", "max_age": 30}
    )
    assert [r["name"] for r in result["rows"]] == ["Divya R"]


def test_get_voter_by_epic_returns_provenance(sample_part):
    result = _run("get_voter", {"epic": "TNAI0000001"})
    assert result["voter"]["name"] == "Muthu Vel"
    assert "provenance" in result
    assert "ocr_fields" in result


def test_get_voter_refuses_an_unknown_epic():
    with pytest.raises(registry.ToolError, match="No elector"):
        _run("get_voter", {"epic": "NOSUCHEPIC1"})


def test_get_voter_requires_an_identifier():
    with pytest.raises(registry.ToolError, match="voter_id or epic"):
        _run("get_voter", {})


def test_household_groups_by_house_number(sample_part):
    result = _run("household_of", {"epic": "TNAI0000001"})
    assert result["household"]["house_number"] == "12"
    assert result["household"]["size"] == 2
