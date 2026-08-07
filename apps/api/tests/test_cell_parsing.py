"""Cell-level parsing of the electoral-roll template.

Exercises `_parse_cell` with the OCR line lists actually observed on the
sample corpus -- no PaddleOCR involved, so these run in milliseconds.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.schemas.core import BBox, GridSource, LayoutInfo, OcrLine  # noqa: E402
from app.templates.electoral_roll_ta import TEMPLATE  # noqa: E402

CELL = BBox(x=0, y=0, w=380, h=150)


def line(text: str, y: float, conf: float = 0.97) -> OcrLine:
    return OcrLine(
        id=uuid.uuid4().hex[:8],
        text=text,
        confidence=conf,
        bbox=BBox(x=5, y=y, w=200, h=12),
        polygon=[],
    )


def parse_cell(texts: list[str]):
    """Run the template over a single cell's worth of lines."""
    lines = [line(t, 10 + i * 18) for i, t in enumerate(texts)]
    layout = LayoutInfo(source=GridSource.DETECTED, confidence=1.0, cells=[CELL],
                        rows=1, cols=1)
    records = TEMPLATE.parse(lines, layout, "page1", (1187, 1680))
    return records[0] if records else None


BASE_KEYS = {"serial", "epic", "name", "relation_type", "relation_name", "house_number", "age", "gender"}


def values(record) -> dict[str, str]:
    if record is None:
        return {}
    return {k: f.value for k, f in record.fields.items() if k in BASE_KEYS}


# ---------------------------------------------------------------------------
# The ordinary case
# ---------------------------------------------------------------------------


def test_full_cell_extracts_every_field():
    rec = parse_cell([
        "181",
        "ZHT0308742",
        "பெயர் : சுசீலா -",
        "கணவர் பெயர்: சண்முகம் -",
        "வீட்டு எண் : 5-177",
        "Photo is",
        "வயது : 34 பாலினம் : பெண்",
        "available",
    ])
    assert values(rec) == {
        "serial": "181",
        "epic": "ZHT0308742",
        "name": "சுசீலா",
        "relation_type": "Husband",
        "relation_name": "சண்முகம்",
        "house_number": "5-177",
        "age": "34",
        "gender": "Female",
    }


def test_house_number_separators_survive():
    """Regression: an unanchored cleanup regex used to strip inner hyphens."""
    for raw, expected in [
        ("வீட்டு எண் : 5-179-1", "5-179-1"),
        ("வீட்டு எண் : 4/420-2", "4/420-2"),
        ("வீட்டு எண் : 4-423-2", "4-423-2"),
    ]:
        rec = parse_cell(["181", "ZHT0308742", raw])
        assert values(rec)["house_number"] == expected


# ---------------------------------------------------------------------------
# Value wrapped onto the following line (records 666 / 668 / 670)
# ---------------------------------------------------------------------------


def test_relation_value_wrapped_to_next_line_is_recovered():
    rec = parse_cell([
        "666",
        "ZHT1672393",
        "பெயர் : பொன்னுசாமி நாயுடு",
        "தந்தையின் பெயர்:",
        "கடமடைமுனியப்பன் -",
        "வீட்டு எண் : 4-417",
        "வயது : 76 பாலினம் : ஆண்",
    ])
    got = values(rec)
    assert got["relation_name"] == "கடமடைமுனியப்பன்"
    assert got["relation_type"] == "Father"
    assert got["name"] == "பொன்னுசாமி நாயுடு"


def test_wrapped_value_does_not_steal_a_following_labelled_line():
    """The next line must only be adopted when it carries no label itself."""
    rec = parse_cell([
        "670",
        "ZHT1672401",
        "பெயர் : கிருஷ்ணன்",
        "தந்தையின் பெயர்:",
        "வீட்டு எண் : 4-418",
        "வயது : 58 பாலினம் : ஆண்",
    ])
    got = values(rec)
    assert got["house_number"] == "4-418"
    assert got["relation_name"] == ""


def test_wrapped_value_does_not_consume_an_identifier():
    """An EPIC-shaped line is page furniture, never a relation's name."""
    rec = parse_cell([
        "671",
        "பெயர் : நாகம்மாள்",
        "கணவர் பெயர்:",
        "ZHT1672419",
    ])
    got = values(rec)
    assert got["relation_name"] == "", "identifier must not be adopted as a name"
    assert got["name"] == "நாகம்மாள்"


# ---------------------------------------------------------------------------
# Empty and partial cells
# ---------------------------------------------------------------------------


def test_empty_cell_produces_no_record():
    layout = LayoutInfo(source=GridSource.DETECTED, confidence=1.0, cells=[CELL],
                        rows=1, cols=1)
    assert TEMPLATE.parse([], layout, "page1", (1187, 1680)) == []


def test_photo_placeholder_only_produces_no_record():
    """A cell holding just the photo placeholder is not a voter."""
    assert parse_cell(["Photo is", "available"]) is None
