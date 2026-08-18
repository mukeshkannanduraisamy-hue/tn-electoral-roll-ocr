"""Reading the additions and deletions totals off a summary sheet.

The sheet is the only external check on extraction: the issuing authority prints
the base count, the supplement additions, the deletions and the net total, and
the four must reconcile as base + additions - deletions + gender = net.

Additions and deletions are printed as several rows -- one per supplement, then
a `மொத்தம்` total that belongs to the category above it. Taking the first row of
a category picks up supplement 1 and calls it the whole figure, which on TAM-16
read additions as 213 instead of 223, deletions as 223 (the additions total) and
the net as 226 (the deletions supplement-1 figure). Everything downstream then
reported the roll as failing to reconcile when it does.

Numbers below are TAM-16's, transcribed from its page 32:

    அடிப்படைப் பட்டியல்          279  277  0  556
    சேர்த்தல்  துணைப்பட்டியல் 1   105  108  0  213
              துணைப்பட்டியல் 2     5    5  0   10
              மொத்தம்            110  113  0  223
    நீக்கல்   துணைப்பட்டியல் 1   112  114  0  226
              துணைப்பட்டியல் 2     5    2  0    7
              மொத்தம்            117  116  0  233
    நிகர                        272  274  0  546

    556 + 223 - 233 + 0 = 546
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.services.roll_metadata import parse_summary  # noqa: E402

PAGE_WIDTH = 1000.0
_LABEL_X = 60.0
_NUMBER_XS = (620.0, 700.0, 780.0, 870.0)


def _line(text: str, x: float, y: float) -> OcrLine:
    return OcrLine(
        id=f"l{abs(hash((text, x, y))) % 10**9}",
        text=text,
        confidence=0.95,
        bbox=BBox(x=x, y=y, w=max(30.0, len(text) * 6.0), h=14.0),
    )


def _row(label: str, counts: tuple[int, int, int, int], y: float) -> list[OcrLine]:
    lines = [_line(str(c), x, y) for c, x in zip(counts, _NUMBER_XS)]
    if label:
        lines.append(_line(label, _LABEL_X, y))
    return lines


def _summary_page() -> list[OcrLine]:
    rows: list[OcrLine] = []
    rows += _row("அடிப்படைப் பட்டியல்", (279, 277, 0, 556), 100)
    rows += _row("சேர்த்தல் பட்டியல் துணைப்பட்டியல் 1", (105, 108, 0, 213), 140)
    rows += _row("துணைப்பட்டியல் 2 தொடர் திருத்தக் காலம்", (5, 5, 0, 10), 180)
    rows += _row("மொத்தம்", (110, 113, 0, 223), 220)
    rows += _row("நீக்கல் பட்டியல் துணைப்பட்டியல் 1", (112, 114, 0, 226), 260)
    rows += _row("துணைப்பட்டியல் 2 தொடர் திருத்தக் காலம்", (5, 2, 0, 7), 300)
    rows += _row("மொத்தம்", (117, 116, 0, 233), 340)
    rows += _row("பாலினப் பிரிவில் மாற்றம்", (0, 0, 0, 0), 380)
    rows += _row("திருத்தங்களுக்கு பிறகு நிகர வாக்காளர்கள்", (272, 274, 0, 546), 420)
    # Right-hand column marker the parser uses to size the number bands.
    rows.append(_line("x", PAGE_WIDTH - 20, 20))
    return rows


def test_additions_use_the_category_total_not_supplement_one():
    assert parse_summary(_summary_page()).additions.total == 223


def test_deletions_use_the_category_total_not_supplement_one():
    assert parse_summary(_summary_page()).deletions.total == 233


def test_base_and_net_are_read():
    summary = parse_summary(_summary_page())
    assert summary.base.total == 556
    assert summary.net.total == 546


def test_the_sheet_reconciles_once_the_totals_are_right():
    """base + additions - deletions + gender == net, which is the whole point."""
    assert parse_summary(_summary_page()).net_is_consistent


def test_gender_reclassification_is_not_mistaken_for_a_category_total():
    assert parse_summary(_summary_page()).gender_adjustment.total == 0


def test_a_sheet_without_subtotal_rows_still_parses():
    """Not every roll prints supplements; a single row per category must work."""
    rows: list[OcrLine] = []
    rows += _row("அடிப்படைப் பட்டியல்", (100, 100, 0, 200), 100)
    rows += _row("சேர்த்தல் பட்டியல்", (5, 5, 0, 10), 140)
    rows += _row("நீக்கல் பட்டியல்", (2, 1, 0, 3), 180)
    rows += _row("பாலினப் பிரிவில் மாற்றம்", (0, 0, 0, 0), 220)
    rows += _row("நிகர வாக்காளர்கள்", (103, 104, 0, 207), 260)
    rows.append(_line("x", PAGE_WIDTH - 20, 20))
    summary = parse_summary(rows)
    assert summary.additions.total == 10
    assert summary.deletions.total == 3
    assert summary.net_is_consistent


def test_no_lines_is_handled():
    assert parse_summary([]).net.total == 0


def test_a_zero_read_as_the_letter_o_still_forms_a_row():
    """TAM-16's deletions total is `117 116 o 233` -- the third-gender zero
    came back as a letter at 0.792 confidence.

    A row needs four numbers, so the whole line was dropped and deletions read
    226 (supplement 1) instead of 233. In this column, which holds nothing but
    counts, an `o` among digits is a zero.
    """
    rows: list[OcrLine] = []
    rows += _row("அடிப்படைப் பட்டியல்", (279, 277, 0, 556), 100)
    rows += _row("சேர்த்தல் பட்டியல்", (110, 113, 0, 223), 140)
    # the deletions total, exactly as OCR returns it
    rows += [
        _line("நீக்கல் பட்டியல் மொத்தம்", _LABEL_X, 180),
        _line("117", _NUMBER_XS[0], 180),
        _line("116", _NUMBER_XS[1], 180),
        _line("o", _NUMBER_XS[2], 180),
        _line("233", _NUMBER_XS[3], 180),
    ]
    rows += _row("பாலினப் பிரிவில் மாற்றம்", (0, 0, 0, 0), 220)
    rows += _row("நிகர வாக்காளர்கள்", (272, 274, 0, 546), 260)
    rows.append(_line("x", PAGE_WIDTH - 20, 20))

    summary = parse_summary(rows)
    assert summary.deletions.total == 233
    assert summary.deletions.third_gender == 0
    assert summary.net_is_consistent


def _sheet_with_gender_row(gender_tokens: tuple[str, str, str, str]) -> list[OcrLine]:
    rows: list[OcrLine] = []
    rows += _row("அடிப்படைப் பட்டியல்", (403, 374, 0, 777), 100)
    rows += _row("சேர்த்தல் பட்டியல்", (7, 22, 0, 29), 140)
    rows += _row("நீக்கல் பட்டியல்", (29, 23, 0, 52), 180)
    rows += [
        _line("பாலினப் பிரிவில் மாற்றம் செய்வதால் ஏற்படும் வேறுபாடு", _LABEL_X, 220),
        *(_line(t, x, 220) for t, x in zip(gender_tokens, _NUMBER_XS)),
    ]
    rows += _row("நிகர வாக்காளர்கள்", (382, 372, 0, 754), 260)
    rows.append(_line("x", PAGE_WIDTH - 20, 20))
    return rows


def test_a_gender_reclassification_row_may_be_negative():
    """TAM-19 prints `1 -1 0 0`: one elector moved from female to male.

    OCR returns the minus faithfully at 0.998, but `-1` did not match the
    integer pattern, so the row had only three numbers, failed the four-number
    filter and was filled from an unrelated band -- landing gender at 11 and
    breaking the sheet's arithmetic.
    """
    summary = parse_summary(_sheet_with_gender_row(("1", "-1", "0", "0")))
    assert summary.gender_adjustment.male == 1
    assert summary.gender_adjustment.female == -1
    assert summary.gender_adjustment.total == 0


def test_the_sheet_reconciles_with_a_reclassification():
    """777 + 29 - 52 + 0 = 754."""
    summary = parse_summary(_sheet_with_gender_row(("1", "-1", "0", "0")))
    assert summary.net_is_consistent


def test_the_other_rows_are_unharmed_by_the_negative_row():
    summary = parse_summary(_sheet_with_gender_row(("1", "-1", "0", "0")))
    assert summary.base.total == 777
    assert summary.additions.total == 29
    assert summary.deletions.total == 52
    assert summary.net.total == 754


@pytest.mark.parametrize("minus", ["-", "−", "–", "—"])
def test_the_dashes_ocr_uses_for_a_minus_are_all_read(minus):
    """Hyphen, true minus, en dash and em dash all come back from OCR."""
    summary = parse_summary(_sheet_with_gender_row(("1", f"{minus}1", "0", "0")))
    assert summary.gender_adjustment.female == -1


def test_a_negative_row_still_has_to_add_up():
    assert parse_summary(
        _sheet_with_gender_row(("1", "-1", "0", "0"))
    ).gender_adjustment.adds_up


def test_a_date_is_not_read_as_a_negative_number():
    """Footers carry `06-04-2026`; it must not become a count."""
    rows = _sheet_with_gender_row(("1", "-1", "0", "0"))
    rows.append(_line("06-04-2026", _NUMBER_XS[0], 320))
    summary = parse_summary(rows)
    assert summary.net.total == 754


def test_roman_numerals_are_not_mistaken_for_numbers():
    """The table numbers its sections `I`, `IlI`, `IV` in the same columns.

    Mapping letters to digits wholesale would turn `IlI` into 111 and invent a
    row, so only an `o` sitting among digits is treated as a zero.
    """
    rows: list[OcrLine] = []
    rows += _row("அடிப்படைப் பட்டியல்", (279, 277, 0, 556), 100)
    rows += [_line(t, _NUMBER_XS[i], 140) for i, t in enumerate(("IlI", "IV", "B", "I"))]
    rows += _row("சேர்த்தல் பட்டியல்", (5, 5, 0, 10), 180)
    rows += _row("நீக்கல் பட்டியல்", (2, 1, 0, 3), 220)
    rows += _row("பாலினப் பிரிவில் மாற்றம்", (0, 0, 0, 0), 260)
    rows += _row("நிகர வாக்காளர்கள்", (282, 281, 0, 563), 300)
    rows.append(_line("x", PAGE_WIDTH - 20, 20))

    summary = parse_summary(rows)
    assert summary.base.total == 556
    assert summary.additions.total == 10
    assert summary.deletions.total == 3
    assert summary.net_is_consistent
