"""Settling one section name per part, across all its pages.

Two problems, both only visible with the whole file in hand, which is why this
runs after the page fan-in rather than inside the template.

**The same section reads several ways.** OCR returned four spellings of one
section across TAM-16, differing only in noise:

    1-பன்குளம் (வ.கி) மற்றும் (ஊ), பனகுளம்
    1-பன்குளம் (வ.கி) மற்றும் (ஊ), பனைகுளம்
    1-பன்குளம் (வ.கி) மற்றும் (ஊை), பனைகுளம்
    1-பன்குளம் (வ.கி) மற்றும் (உள), பனகுளம்

Stored as-is, one section becomes four values and any grouping or filtering on
it silently splits. The section *number* is digits and survives OCR, so it is
the identity; the most-seen spelling becomes the name.

**Supplement pages print no section at all.** Pages 23-31 of TAM-16 carry the
constituency and part number, then go straight to `சேர்த்தல் பட்டியல் 1`, leaving
223 electors with no section. A section header applies until another replaces
it, so those pages inherit the last one seen.

Inheritance is recorded rather than hidden: a carried section is a reasonable
reading of the document, not something printed on the page.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.section_reconciliation import reconcile_sections  # noqa: E402

VARIANTS = [
    "1-பன்குளம் (வ.கி) மற்றும் (ஊ), பனகுளம்",
    "1-பன்குளம் (வ.கி) மற்றும் (ஊ), பனைகுளம்",
    "1-பன்குளம் (வ.கி) மற்றும் (ஊை), பனைகுளம்",
    "1-பன்குளம் (வ.கி) மற்றும் (உள), பனகுளம்",
]


def test_one_spelling_wins_for_a_section_number():
    """The most-seen spelling becomes the name for every page of that section."""
    pages = {4: VARIANTS[0], 5: VARIANTS[0], 6: VARIANTS[1], 7: VARIANTS[2]}
    result = reconcile_sections(pages)
    assert set(result.by_page.values()) == {VARIANTS[0]}


def test_a_page_with_no_section_inherits_the_one_before_it():
    pages = {4: VARIANTS[0], 5: VARIANTS[0], 23: "", 24: "", 25: ""}
    result = reconcile_sections(pages)
    assert result.by_page[24] == VARIANTS[0]
    assert result.inherited_pages == frozenset({23, 24, 25})


def test_inheritance_is_reported_so_it_can_be_marked():
    """A carried section was not printed on that page; the record should say so."""
    result = reconcile_sections({4: VARIANTS[0], 9: ""})
    assert 4 not in result.inherited_pages
    assert 9 in result.inherited_pages


def test_pages_before_any_section_stay_empty():
    """Nothing to carry from, so nothing is invented."""
    result = reconcile_sections({1: "", 2: "", 4: VARIANTS[0]})
    assert result.by_page[1] == ""
    assert result.by_page[2] == ""
    assert result.inherited_pages == frozenset()


def test_a_later_section_replaces_the_earlier_one():
    """A part can hold several sections; the nearest preceding one applies."""
    second = "2-கொட்டகை (வ.கி), கொட்டகை"
    pages = {4: VARIANTS[0], 5: "", 6: second, 7: ""}
    result = reconcile_sections(pages)
    assert result.by_page[5] == VARIANTS[0]
    assert result.by_page[7] == second


def test_each_section_number_is_normalised_independently():
    """A variant of section 2 must not be pulled towards section 1's spelling."""
    second_a = "2-கொட்டகை (வ.கி), கொட்டகை"
    second_b = "2-கொட்டகை (வ.கி), கெட்டகை"
    pages = {4: VARIANTS[0], 5: VARIANTS[0], 6: second_a, 7: second_a, 8: second_b}
    result = reconcile_sections(pages)
    assert result.by_page[4] == VARIANTS[0]
    assert result.by_page[8] == second_a


def test_a_tie_keeps_the_longer_spelling():
    """OCR drops glyphs more often than it invents them, so longer is likelier
    to be the complete reading. Documented because it decides stored values."""
    shorter, longer = VARIANTS[0], VARIANTS[1]
    assert len(longer) > len(shorter)
    result = reconcile_sections({4: shorter, 5: longer})
    assert set(result.by_page.values()) == {longer}


def test_pages_are_ordered_by_number_not_by_insertion():
    """Pages may arrive in any order; the document's order is what counts."""
    pages = {25: "", 5: VARIANTS[0], 24: ""}
    result = reconcile_sections(pages)
    assert result.by_page[24] == VARIANTS[0]
    assert result.by_page[25] == VARIANTS[0]


def test_a_tie_is_broken_the_same_way_every_run():
    """Reprocessing a file must not shuffle which spelling is stored."""
    pages = {4: VARIANTS[0], 5: VARIANTS[1]}
    first = reconcile_sections(pages).by_page
    for _ in range(5):
        assert reconcile_sections(pages).by_page == first


def test_a_section_with_no_number_is_left_alone():
    """Nothing to group by, so variants are not merged on a guess."""
    pages = {4: "பனைகுளம்", 5: "பனகுளம்"}
    result = reconcile_sections(pages)
    assert result.by_page[4] == "பனைகுளம்"
    assert result.by_page[5] == "பனகுளம்"


def test_an_empty_file_is_handled():
    result = reconcile_sections({})
    assert result.by_page == {}
    assert result.inherited_pages == frozenset()


# ----------------------------------------------------- applying it to pages

from app.schemas.core import (  # noqa: E402
    BBox, FieldValue, Page, PageStatus, Record,
)
from app.services.section_reconciliation import apply_sections  # noqa: E402


def _page(number: int, section: str, records: int = 2) -> Page:
    return Page(
        id=f"p{number}",
        file_id="f1",
        page_number=number,
        status=PageStatus.COMPLETED,
        width=1000,
        height=1400,
        records=[
            Record(
                id=f"r{number}-{i}",
                page_id=f"p{number}",
                index=i,
                template_id="electoral_roll_ta",
                bbox=BBox(x=0, y=0, w=10, h=10),
                fields={
                    "section_name": FieldValue(
                        key="section_name", original_value=section
                    )
                },
            )
            for i in range(records)
        ],
    )


def _sections_of(page: Page) -> set[str]:
    return {r.fields["section_name"].original_value for r in page.records}


def test_applying_rewrites_every_record_on_a_page():
    pages = [_page(4, VARIANTS[0]), _page(5, VARIANTS[0]), _page(6, VARIANTS[2])]
    apply_sections(pages)
    assert _sections_of(pages[2]) == {VARIANTS[0]}


def test_applying_fills_pages_that_printed_no_section():
    pages = [_page(4, VARIANTS[0]), _page(23, "")]
    apply_sections(pages)
    assert _sections_of(pages[1]) == {VARIANTS[0]}


def test_a_filled_page_says_the_section_was_carried():
    pages = [_page(4, VARIANTS[0]), _page(23, "")]
    apply_sections(pages)
    for record in pages[1].records:
        assert any("carried" in (i.message or "") for i in record.issues)
    for record in pages[0].records:
        assert not any("carried" in (i.message or "") for i in record.issues)


def test_applying_twice_does_not_stack_notes():
    pages = [_page(4, VARIANTS[0]), _page(23, "")]
    apply_sections(pages)
    apply_sections(pages)
    for record in pages[1].records:
        carried = [i for i in record.issues if "carried" in (i.message or "")]
        assert len(carried) == 1


def test_applying_reports_how_much_it_changed():
    pages = [_page(4, VARIANTS[0]), _page(5, VARIANTS[2]), _page(23, "")]
    report = apply_sections(pages)
    assert report.records_changed == 4      # page 5 normalised, page 23 filled
    assert report.pages_inherited == 1
