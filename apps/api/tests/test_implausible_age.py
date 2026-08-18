"""An age no elector can have is not stored as their age.

Across four rolls, 17 records held an age outside the electoral range: eleven
`0`, three `6`, two `8` and one `2` -- a lost leading digit, so `80` became `8`
and `60` became `6`. Every one is a value a reader would take at face value,
and none can be right: the roll only lists electors of 18 and over.

The stamped path already cleared these, because the DELETED watermark crosses
the age line and the damage was expected there. Nothing did so otherwise, and
two of the rolls carrying these values have no deletions at all.

A missing age is recoverable later from the page image. A wrong one is not,
because nobody knows to look.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.templates.electoral_roll_ta import ElectoralRollTamilTemplate  # noqa: E402

CELL = BBox(x=0.0, y=0.0, w=560.0, h=220.0)


def _line(text: str, x: float, y: float) -> OcrLine:
    return OcrLine(
        id=f"l{abs(hash((text, x, y))) % 10**8}",
        text=text,
        confidence=0.95,
        bbox=BBox(x=x, y=y, w=max(8.0, len(text) * 7.0), h=16.0),
    )


def _card(age_line: str) -> list[OcrLine]:
    return [
        _line("70", 120, 16),
        _line("IEB0895417", 400, 16),
        _line("பெயர் : பச்சியம்மாள்", 20, 45),
        _line("தந்தை பெயர்: வெங்கடாசலபதி", 20, 70),
        _line("வீட்டு எண் : 1", 20, 95),
        _line(age_line, 20, 120),
    ]


def _parse(lines):
    return ElectoralRollTamilTemplate()._parse_cell(lines, CELL, 0, "page-1", {}, [])


@pytest.mark.parametrize("digits", ["0", "6", "8", "2", "17", "121", "999"])
def test_an_age_outside_the_electoral_range_is_not_stored(digits):
    record = _parse(_card(f"வயது : {digits} பாலினம் : ஆண்"))
    assert record.fields["age"].original_value == ""


@pytest.mark.parametrize("digits", ["18", "19", "45", "80", "120"])
def test_a_possible_age_is_kept(digits):
    record = _parse(_card(f"வயது : {digits} பாலினம் : ஆண்"))
    assert record.fields["age"].original_value == digits


def test_dropping_the_age_leaves_the_rest_of_the_card_alone():
    record = _parse(_card("வயது : 8 பாலினம் : ஆண்"))
    assert record.fields["serial"].original_value == "70"
    assert record.fields["epic"].original_value == "IEB0895417"
    assert record.fields["gender"].original_value == "Male"
    assert record.fields["name"].original_value


def test_the_reader_is_told_the_age_was_rejected():
    """A blank with no explanation looks like the roll printed nothing."""
    record = _parse(_card("வயது : 8 பாலினம் : ஆண்"))
    assert any(issue.field == "age" for issue in record.issues)


def test_a_card_with_no_age_line_is_unchanged():
    lines = [ln for ln in _card("வயது : 45 பாலினம் : ஆண்") if "வயது" not in ln.text]
    record = _parse(lines)
    assert record.fields["age"].original_value == ""
