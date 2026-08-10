"""The constituency and section every elector on a page belongs to.

A roll page names three things in its header, and every voter on that page
inherits all three:

    சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர் : 58-பென்னாகரம்     constituency
    பாகம் எண் : 16                                              part number
    பிரிவு எண் மற்றும் பெயர் 1-பனைகுளம் (வ.கி) மற்றும் (ஊ), பனைகுளம்   section

Two things went wrong before these tests existed. The constituency was never
extracted at all, despite `VoterRow.constituency` existing to hold it. And the
section name swallowed the entire page: header text is matched against all the
page's lines joined with spaces, so a `[^\n\r]+` pattern ran to the end of the
document and every one of TAM-16's 779 records carried a full page dump.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.templates.electoral_roll_ta import ElectoralRollTamilTemplate  # noqa: E402

CONSTITUENCY = "58-பென்னாகரம்"
SECTION = "1-பனைகுளம் (வ.கி) மற்றும் (ஊ), பனைகுளம்"


def _line(text: str, y: float, x: float = 20.0) -> OcrLine:
    return OcrLine(
        id=f"l{abs(hash((text, y, x))) % 10**8}",
        text=text,
        confidence=0.95,
        bbox=BBox(x=x, y=y, w=max(8.0, len(text) * 6.0), h=15.0),
    )


def _page_lines() -> list[OcrLine]:
    """A header, then the body text that used to be swallowed by the section."""
    return [
        _line(f"சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர் : {CONSTITUENCY}", 10),
        _line("பாகம் எண் : 16", 10, x=900),
        _line(f"பிரிவு எண் மற்றும் பெயர்  {SECTION}", 28),
        _line("1", 70, x=120),
        _line("IEB0555193", 70, x=400),
        _line("பெயர் : இலட்சுமி", 95),
        _line("வீட்டு எண் : 1", 120),
        _line("வயது : 41 பாலினம் : பெண்", 145),
    ]


def _meta():
    return ElectoralRollTamilTemplate._extract_header_metadata(_page_lines())


def test_constituency_is_read_from_the_header():
    assert _meta()["constituency"] == CONSTITUENCY


def test_section_name_is_read_from_the_header():
    assert _meta()["section_name"] == SECTION


def test_section_name_stops_at_the_end_of_its_own_line():
    """It used to run to the end of the page, carrying every elector with it."""
    section = _meta()["section_name"]
    assert "IEB0555193" not in section
    assert "பெயர் : இலட்சுமி" not in section
    assert len(section) < 120, f"section swallowed {len(section)} chars: {section[:80]}"


def test_part_number_still_works():
    assert _meta()["part_number"] == "16"


def test_the_part_number_does_not_leak_into_the_section():
    """Both sit on the header, and the part number is printed to the right."""
    assert "பாகம்" not in _meta()["section_name"]


def test_a_page_without_a_header_reports_nothing_rather_than_guessing():
    body = [_line("பெயர் : இலட்சுமி", 95), _line("வயது : 41 பாலினம் : பெண்", 120)]
    meta = ElectoralRollTamilTemplate._extract_header_metadata(body)
    assert not meta.get("constituency")
    assert not meta.get("section_name")


def test_every_record_on_the_page_carries_both_fields():
    """The point of the exercise: each voter inherits its page's header."""
    from app.schemas.core import LayoutInfo

    template = ElectoralRollTamilTemplate()
    records = template.parse(
        _page_lines(),
        LayoutInfo(cells=[BBox(x=0, y=60, w=1100, h=200)], rows=1, cols=1),
        "page-1",
        (1100, 400),
    )
    assert records, "expected the body row to parse into a record"
    for record in records:
        assert record.fields["constituency"].original_value == CONSTITUENCY
        assert record.fields["section_name"].original_value == SECTION
        assert record.fields["part_number"].original_value == "16"
