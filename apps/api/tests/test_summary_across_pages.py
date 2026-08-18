"""Reading a summary table that runs onto the next sheet.

The statutory summary does not always fit one page. On TAM-16 the base,
additions and deletions rows sit on page 32 while the `நிகர` net row -- the
figure the roll certifies and the only one that closes the arithmetic -- sits on
page 33, together with the deletion-reason legend.

Page 33 is therefore classified `legend_page`, and the parser was only ever
handed the single page classified `summary_page`. The net was filled from an
unrelated band instead, so every roll in the corpus reported a net that did not
follow from its own components.

Continuation pages are merged with their line positions shifted down by the
height of the pages before them, so the rows keep document order across the
join and the vertical banding still works.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.core import BBox, OcrLine, Page, PageStatus  # noqa: E402
from app.services.page_classifier import PageType  # noqa: E402
from app.services.roll_metadata import build, summary_lines  # noqa: E402

PAGE_W, PAGE_H = 1000.0, 1400.0
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
    out = [_line(str(c), x, y) for c, x in zip(counts, _NUMBER_XS)]
    if label:
        out.append(_line(label, _LABEL_X, y))
    return out


def _page(number: int, page_type: PageType, lines: list[OcrLine]) -> Page:
    return Page(
        id=f"p{number}",
        file_id="f1",
        page_number=number,
        status=PageStatus.COMPLETED,
        width=int(PAGE_W),
        height=int(PAGE_H),
        page_type=page_type.value,
        classification_confidence=0.96,
        lines=lines,
        records=[],
    )


def _summary_page() -> Page:
    """Base, additions and deletions -- everything but the net."""
    lines: list[OcrLine] = []
    lines += _row("அடிப்படைப் பட்டியல்", (279, 277, 0, 556), 300)
    lines += _row("சேர்த்தல் பட்டியல் துணைப்பட்டியல் 1", (105, 108, 0, 213), 500)
    lines += _row("துணைப்பட்டியல் 2", (5, 5, 0, 10), 600)
    lines += _row("மொத்தம்", (110, 113, 0, 223), 700)
    lines += _row("நீக்கல் பட்டியல் துணைப்பட்டியல் 1", (112, 114, 0, 226), 800)
    lines += _row("துணைப்பட்டியல் 2", (5, 2, 0, 7), 900)
    lines += _row("மொத்தம்", (117, 116, 0, 233), 1000)
    lines += _row("பாலினப் பிரிவில் மாற்றம்", (0, 0, 0, 0), 1100)
    lines.append(_line("x", PAGE_W - 20, 40))
    return _page(32, PageType.SUMMARY_PAGE, lines)


def _legend_page_carrying_the_net() -> Page:
    lines: list[OcrLine] = []
    lines += _row("திருத்தங்களுக்கு பிறகு நிகர வாக்காளர்கள்", (272, 274, 0, 546), 200)
    lines.append(_line("திருத்தங்களின் எண்ணிக்கை", _LABEL_X, 400))
    lines.append(_line("5", _NUMBER_XS[0], 500))
    lines.append(_line("E- Expired, S- Shifted, R-Repeated", _LABEL_X, 700))
    lines.append(_line("x", PAGE_W - 20, 40))
    return _page(33, PageType.LEGEND_PAGE, lines)


def _voter_page(number: int) -> Page:
    return _page(number, PageType.VOTER_LIST_PAGE,
                 [_line("பெயர் : இலட்சுமி", _LABEL_X, 300)])


def test_the_net_row_on_the_following_page_is_read():
    meta = build([_summary_page(), _legend_page_carrying_the_net()], "f1")
    assert meta.summary is not None
    assert meta.summary.net.total == 546


def test_the_sheet_reconciles_once_both_pages_are_read():
    """556 + 223 - 233 + 0 = 546, which is the whole point of the table."""
    meta = build([_summary_page(), _legend_page_carrying_the_net()], "f1")
    assert meta.summary.net_is_consistent


def test_the_earlier_rows_survive_the_merge():
    summary = build([_summary_page(), _legend_page_carrying_the_net()], "f1").summary
    assert summary.base.total == 556
    assert summary.additions.total == 223
    assert summary.deletions.total == 233


def test_a_voter_page_after_the_summary_is_not_merged_in():
    """Only sheets continuing the table qualify; voter pages carry electors."""
    lines = summary_lines([_summary_page(), _voter_page(33)])
    assert not any("பெயர்" in ln.text for ln in lines)


def test_continuation_lines_are_shifted_below_the_first_page():
    """Without an offset the net row would sort among page 32's rows."""
    pages = [_summary_page(), _legend_page_carrying_the_net()]
    lines = summary_lines(pages)
    net = next(ln for ln in lines if "நிகர" in ln.text)
    last_on_first_page = max(
        ln.bbox.cy for ln in _summary_page().lines if ln.bbox.cy < PAGE_H
    )
    assert net.bbox.cy > last_on_first_page


def test_the_original_pages_are_not_mutated():
    """Lines belong to the Page and get saved; offsetting must copy."""
    pages = [_summary_page(), _legend_page_carrying_the_net()]
    before = [ln.bbox.y for ln in pages[1].lines]
    summary_lines(pages)
    assert [ln.bbox.y for ln in pages[1].lines] == before


def test_a_single_page_summary_still_parses():
    lines: list[OcrLine] = []
    lines += _row("அடிப்படைப் பட்டியல்", (100, 100, 0, 200), 300)
    lines += _row("சேர்த்தல் பட்டியல்", (5, 5, 0, 10), 400)
    lines += _row("நீக்கல் பட்டியல்", (2, 1, 0, 3), 500)
    lines += _row("பாலினப் பிரிவில் மாற்றம்", (0, 0, 0, 0), 600)
    lines += _row("நிகர வாக்காளர்கள்", (103, 104, 0, 207), 700)
    lines.append(_line("x", PAGE_W - 20, 40))
    meta = build([_page(20, PageType.SUMMARY_PAGE, lines)], "f1")
    assert meta.summary.net.total == 207
    assert meta.summary.net_is_consistent


def test_no_summary_page_yields_no_summary():
    assert build([_voter_page(1)], "f1").summary is None
