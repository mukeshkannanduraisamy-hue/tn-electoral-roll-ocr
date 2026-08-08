"""What the template records for a struck-off elector's cell.

Two behaviours are pinned here that the template did not have:

* `is_deleted` is written on every cell, including `"No"`. It used to be written
  only when the answer was `"Yes"`, which left an evaluated live elector and a
  cell nothing had looked at both holding `""` -- the state all 632 records in
  the historical database are in.
* The stamp is a signal in its own right, supplied as geometry from the image
  rather than read out of the OCR text, because OCR never returns it.

Line text is verbatim PaddleOCR output for TAM-16 page 4.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.services.stamp_detector import StampMark  # noqa: E402
from app.templates.electoral_roll_ta import ElectoralRollTamilTemplate  # noqa: E402

CELL = BBox(x=0.0, y=0.0, w=560.0, h=220.0)


def _line(text: str, x: float, y: float, conf: float = 0.95) -> OcrLine:
    return OcrLine(
        id=f"l{abs(hash((text, x, y))) % 10**8}",
        text=text,
        confidence=conf,
        bbox=BBox(x=x, y=y, w=max(8.0, len(text) * 7.0), h=16.0),
    )


def _stamped_card_lines() -> list[OcrLine]:
    """Serial 13: reason code `S`, and an age line the stamp ran through."""
    return [
        _line("S", 20, 16, 0.832),
        _line("13", 120, 16, 0.999),
        _line("IEB1717636", 400, 16, 0.986),
        _line("பெயர் : சண்முகம்", 20, 45),
        _line("தந்தை பெயர்: கூளியீப்பன்", 20, 70),
        _line("வீட்டு எண் : 2-2", 20, 95, 0.917),
        _line("வயது : 5ஆபீலினம் : ஆண்", 20, 120, 0.936),
    ]


def _live_card_lines() -> list[OcrLine]:
    """Serial 17: no reason code, no stamp."""
    return [
        _line("17", 120, 16, 1.0),
        _line("IEB2121796", 400, 16, 0.996),
        _line("பெயர் : பவித்ரா", 20, 45),
        _line("கணவர் பெயர்: செல்வராஜ்", 20, 70),
        _line("வீட்டு எண் : 2/19", 20, 95),
        _line("வயது : 22 பாலினம் : பெண்", 20, 120),
    ]


def _parse(lines, marks):
    template = ElectoralRollTamilTemplate()
    return template._parse_cell(
        lines, CELL, 0, "page-1", {}, stamp_marks=marks
    )


def test_live_cell_records_an_explicit_no():
    record = _parse(_live_card_lines(), [])
    assert record.fields["is_deleted"].original_value == "No"


def test_reason_code_marks_the_cell_deleted():
    record = _parse(_stamped_card_lines(), [])
    assert record.fields["is_deleted"].original_value == "Yes"
    assert "Shifted" in record.fields["deletion_reason"].original_value


def test_stamp_alone_marks_the_cell_deleted():
    """A card whose reason letter OCR dropped is still struck off."""
    lines = [ln for ln in _stamped_card_lines() if ln.text != "S"]
    mark = StampMark(x=30, y=20, w=280, h=180, angle=62.0)
    record = _parse(lines, [mark])
    assert record.fields["is_deleted"].original_value == "Yes"


def test_stamp_does_not_leak_into_the_live_cell_verdict():
    record = _parse(_live_card_lines(), [])
    assert record.fields["deletion_reason"].original_value == ""


def test_unknown_s2_code_is_flagged_without_inventing_a_meaning():
    lines = _stamped_card_lines()
    lines[0] = _line("S2", 20, 16, 0.80)
    record = _parse(lines, [])
    reason = record.fields["deletion_reason"].original_value
    assert record.fields["is_deleted"].original_value == "Yes"
    assert reason.startswith("S2")
    assert "Shifted" not in reason


def test_a_code_on_its_own_is_not_mistaken_for_the_serial():
    """`S2` read as a serial gives 2, silently renumbering the elector."""
    lines = _stamped_card_lines()
    lines[0] = _line("S2", 20, 16, 0.80)
    record = _parse(lines, [])
    assert record.fields["serial"].original_value == "13"


def test_a_lone_letter_code_also_leaves_the_serial_alone():
    record = _parse(_stamped_card_lines(), [])
    assert record.fields["serial"].original_value == "13"


def test_a_house_number_the_stamp_may_have_flattened_is_flagged():
    """`2-2` read as `22` is the silent case: valid-looking, and wrong.

    It cannot be told from a genuine `22` by inspection, so it is not corrected
    -- it is marked for a human to check, which nothing currently does.
    """
    lines = [ln for ln in _stamped_card_lines() if "வீட்டு" not in ln.text]
    lines.append(_line("வீட்டு எண் : 22", 20, 95, 0.917))
    mark = StampMark(x=30, y=20, w=280, h=180, angle=62.0)
    record = _parse(lines, [mark])
    assert any(
        issue.field == "house_number" for issue in record.issues
    ), [i.model_dump() for i in record.issues]


def test_a_house_number_that_kept_its_separator_is_not_flagged():
    mark = StampMark(x=30, y=20, w=280, h=180, angle=62.0)
    record = _parse(_stamped_card_lines(), [mark])
    assert not any(issue.field == "house_number" for issue in record.issues)


def test_an_unstamped_card_house_number_is_never_flagged():
    """No stamp crossed it, so a bare number is just a house number."""
    lines = [ln for ln in _live_card_lines() if "வீட்டு" not in ln.text]
    lines.append(_line("வீட்டு எண் : 22", 20, 95))
    record = _parse(lines, [])
    assert not any(issue.field == "house_number" for issue in record.issues)


def test_ocr_fragment_inside_a_stamp_is_not_taken_for_a_field():
    """Serial 13 yields a stray `C` at 0.945 -- the outline of the `D`.

    High confidence, so nothing downstream would question it.
    """
    lines = _stamped_card_lines()
    fragment = _line("C", 150, 60, 0.945)
    mark = StampMark(x=140, y=50, w=200, h=150, angle=62.0)
    record = _parse(lines + [fragment], [mark])
    for field in record.fields.values():
        assert field.original_value.strip() != "C"
