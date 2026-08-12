"""Which number on a supplement card is the elector's serial.

A base-list card carries one numbered box. A card on an additions supplement
carries two: the elector's serial in the roll on the left, and the supplement's
own number on the right -- a constant `1` down the whole page, not a per-card
count.

Both boxes sit on the same printed row, and the parser took whichever line came
first out of OCR. Lines are ordered by `(round(cy / 8), cx)`, so a one or two
pixel difference in reported height puts the right-hand box in an earlier band
than the left and flips the answer. Across four rolls that produced 81 serial
jumps, alternating like `574 -> 1 -> 576 -> 1 -> 578`: half the electors on every
supplement page were stored under the supplement number instead of their own.

The serial is the leftmost box, whatever order OCR reports the two in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.templates.electoral_roll_ta import ElectoralRollTamilTemplate  # noqa: E402

CELL = BBox(x=0.0, y=0.0, w=560.0, h=220.0)


def _line(text: str, x: float, y: float, conf: float = 0.99) -> OcrLine:
    return OcrLine(
        id=f"l{abs(hash((text, x, y))) % 10**8}",
        text=text,
        confidence=conf,
        bbox=BBox(x=x, y=y, w=max(8.0, len(text) * 7.0), h=16.0),
    )


def _at(centre_y: float) -> float:
    """`y` for a line whose centre lands on `centre_y` (helper height is 16)."""
    return centre_y - 8.0


def _supplement_card(serial_cy: float, supplement_cy: float) -> list[OcrLine]:
    """Serial 560 and supplement number 1, printed on one row.

    Centres are given directly because the bug lives in where they round to:
    lines sort by `(round(cy / 8), cx)`, so two boxes a pixel apart can land in
    different bands and swap order. Taken from TAM-16 page 23, where `575` sits
    at cy 1020.5 (band 128) and its `1` at cy 1019.5 (band 127).
    """
    return [
        _line("560", 60, _at(serial_cy)),
        _line("1", 210, _at(supplement_cy)),
        _line("IEB2202604", 400, _at(serial_cy)),
        _line("பெயர் : தமிழரசு ம", 20, 45),
        _line("தந்தை பெயர்: மனோகரன்", 20, 70),
        _line("வீட்டு எண் : 5/84", 20, 95),
        _line("வயது : 19 பாலினம் : ஆண்", 20, 120),
    ]


def _parse(lines):
    """Parse a cell the way `parse` hands it over.

    The ordering is the whole point: `parse` sorts a cell's lines by
    `(round(cy / 8), cx)` before `_parse_cell` sees them, so a test that passes
    its own list order never exercises the band rounding that swaps the boxes.
    """
    ordered = sorted(lines, key=lambda ln: (round(ln.bbox.cy / 8), ln.bbox.cx))
    template = ElectoralRollTamilTemplate()
    return template._parse_cell(ordered, CELL, 0, "page-1", {}, [])


@pytest.mark.parametrize(
    "serial_cy,supplement_cy",
    [
        (68.5, 68.5),   # same band, which already worked
        (68.5, 67.5),   # straddles a band edge: supplement sorts first
        (67.5, 68.5),   # straddles the other way
        (72.4, 71.6),   # a different edge
    ],
)
def test_the_serial_is_the_left_box_however_ocr_orders_them(serial_cy, supplement_cy):
    record = _parse(_supplement_card(serial_cy, supplement_cy))
    assert record.fields["serial"].original_value == "560"


def test_the_supplement_number_is_not_stored_as_the_serial():
    """`1` repeated down a page is the supplement, not 30 electors numbered 1."""
    record = _parse(_supplement_card(68.5, 67.5))
    assert record.fields["serial"].original_value != "1"


def test_the_epic_is_unaffected():
    record = _parse(_supplement_card(68.5, 67.5))
    assert record.fields["epic"].original_value == "IEB2202604"


def test_a_serial_box_carrying_a_printed_marker_is_still_read():
    """TAM-16 page 24 prints `#2  604` in the serial box.

    The `#2` is on the page, not an OCR slip. The box then matched no serial
    pattern at all, so only the supplement's `1` was left to be taken as the
    serial -- the residue after the left-box rule fixed the rest.
    """
    lines = [
        _line("#2 604", 65, _at(68.5)),
        _line("1", 206, _at(67.5)),
        _line("IEB1479708", 312, _at(67.5)),
        _line("பெயர் : தவமணி திம்மராயன்", 36, 45),
        _line("வயது : 45 பாலினம் : பெண்", 20, 120),
    ]
    record = _parse(lines)
    assert record.fields["serial"].original_value == "604"


def test_a_printed_marker_is_not_read_as_a_deletion_code():
    """`#2` marks something about the entry; it does not strike anyone off."""
    lines = [
        _line("#2 604", 65, _at(68.5)),
        _line("1", 206, _at(67.5)),
        _line("IEB1479708", 312, _at(67.5)),
        _line("வயது : 45 பாலினம் : பெண்", 20, 120),
    ]
    assert _parse(lines).fields["is_deleted"].original_value == "No"


def test_a_base_list_card_with_one_box_still_works():
    lines = [
        _line("13", 120, 16),
        _line("IEB1717636", 400, 16),
        _line("பெயர் : சண்முகம்", 20, 45),
        _line("வயது : 59 பாலினம் : ஆண்", 20, 120),
    ]
    assert _parse(lines).fields["serial"].original_value == "13"


def test_a_reason_code_still_beats_the_box_it_sits_in():
    """A struck-off supplement card carries a code as well as two numbers."""
    lines = [
        _line("S", 20, 16, 0.83),
        _line("576", 60, 16),
        _line("3", 210, 15),
        _line("KCY2607174", 400, 16),
        _line("பெயர் : கோவிந்தராஜி", 20, 45),
        _line("வயது : 57 பாலினம் : ஆண்", 20, 120),
    ]
    record = _parse(lines)
    assert record.fields["serial"].original_value == "576"
    assert record.fields["is_deleted"].original_value == "Yes"
