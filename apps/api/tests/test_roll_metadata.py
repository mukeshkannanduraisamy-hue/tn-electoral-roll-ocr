"""Cover and summary sheet parsing.

Line positions mirror the reference document (part 4 of AC 57-Palakkodu) at
its rendered size of 1187x1680, because both parsers work off geometry: the
address block's rows are ~24px apart and share one value column, so the
spacing *is* the test.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.core import BBox, OcrLine, Page  # noqa: E402
from app.services.roll_metadata import (  # noqa: E402
    build,
    parse_cover,
    parse_summary,
)


def line(text: str, y: float, x: float, w: float = 200.0, h: float = 16.0) -> OcrLine:
    return OcrLine(
        id=uuid.uuid4().hex[:8],
        text=text,
        confidence=0.95,
        bbox=BBox(x=x, y=y, w=w, h=h),
        polygon=[],
    )


def cover_lines() -> list[OcrLine]:
    """A cover sheet, at the spacing the real one uses."""
    lines = [
        line("வாக்காளர் பட்டியல் 2026 S22 தமிழ்நாடு", 62, 292, 598),
        line("சட்டமன்றத் தொகுதியின் எண். பெயர் மற்றும் ஒதுக்கீட்டுத்தகுதி நிலை : 57 - பாலக்கொடு", 130, 26, 876),
        line("பாகம் எண் : 4", 133, 986, 141),
        line("(பொது)", 165, 24, 87),
        line("சட்டமன்றத் தொகுதி அடங்கியுள்ள நாடாளுமன்றத் தொகுதியின் எண். பெயர் : 10", 206, 25, 1128),
        line("- தர்மபுரி (பொது)", 233, 26, 173),
        # Section 1: revision details, left column.
        line("1. திருத்தத்தின் விவரங்கள்", 271, 26, 277),
        line("திருத்தப்படும் ஆண்டு", 323, 30, 223),
        line("2026", 324, 254, 59),
        line("தகுதியேற்படுத்தும்", 365, 29, 199),
        line("01-01-2026", 369, 268, 98),
        line("திருத்தத்தின் வகை", 441, 30, 201),
        line("சிறப்பு தீவிர திருத்தம்", 440, 268, 221),
        line("பட்டியல்", 503, 31, 85),
        line("23-02-2026", 505, 268, 98),
        # The right-hand prose column: full of dates that belong elsewhere.
        line("19.12.2025 அன்று வெளியிடப்பட்ட, சிறப்பு தீவிர திருத்தம், 2026-இன்", 351, 523, 618),
        # Section 2: the part's area.
        line("2. பாகத்தின் விவரங்கள் மற்றும் வாக்குச்சாவடிக்கான பரப்பளவு", 588, 26, 637),
        line("இந்த பாகத்தில், பாகத்தின் கீழ் வரும் பிரிவின் எண் மற்றும் பெயர்", 634, 27, 655),
        line("1-பஞ்சப்பள்ளி (வ.கி) மற்றும் (ஊ), வார்டு 2", 676, 28, 354),
        line("சொரக்குறிக்கை", 698, 27, 143),
        line("முக்கிய நகரம்/கிராமம்", 684, 509, 194),
        line(": பஞ்சப்பள்ளி", 684, 818, 121),
        line("வார்டு", 708, 508, 60),
        line(":", 713, 818, 12),
        line("அஞ்சல் அலுவலகம்", 732, 509, 172),
        line(": பஞ்சப்பள்ளி", 731, 818, 120),
        line("காவல் நிலையம்", 758, 510, 144),
        line(": பஞ்சப்பள்ளி", 756, 818, 120),
        line("பஞ்சாயத்து", 779, 509, 104),
        line(": பஞ்சபள்ளி", 780, 818, 108),
        line("வட்டம்", 804, 509, 58),
        line(": பாலக்கோடு", 805, 818, 117),
        line("கோட்டம்", 827, 510, 75),
        line(": தரும்புரி", 828, 818, 85),
        line("மாவட்டம்", 851, 508, 82),
        line(": தர்மபுரி", 852, 818, 79),
        line("அஞ்சல் குறியீட்டு எண்", 874, 510, 194),
        line(": 636812", 878, 819, 65),
        # Section 3: the station.
        line("3. வாக்குச் சாவடியின் விவரங்கள்", 1043, 26, 338),
        line("வாக்குச் சாவடியின் எண் மற்றும் பெயர் :", 1087, 28, 400),
        line("வாக்குச் சாவடியின் வகைப்பாடு", 1083, 565, 320),
        line("பொது", 1085, 1020, 71),
        line("4 - ஊராட்சி ஒன்றிய துவக்கப்பள்ளி,", 1127, 28, 340),
        line("சொரக்குறிக்கை- 636812, சொரக்குறிக்கைகிழக்கு", 1151, 28, 464),
        line("துணை வாக்குச் சாவடிகளின் எண்ணிக்கை :", 1151, 587, 279),
        line("0", 1159, 1046, 18),
        line("பார்த்த தார்சு கட்டிடம் தெற்கு பகுதி", 1178, 28, 326),
        line("வாக்குச் சாவடியின் முகவரி :", 1224, 28, 285),
        line("ஊராட்சி ஒன்றிய துவக்கப்பள்ளி,", 1267, 29, 310),
        line("சொரக்குறிக்கை, 636812", 1292, 29, 228),
        # Section 4: the elector table.
        line("4. வாக்காளர்களின் எண்ணிக்கை", 1333, 28, 336),
        line("1", 1502, 89, 16),
        line("180", 1500, 214, 38),
        line("89", 1500, 386, 30),
        line("91", 1501, 599, 27),
        line("0", 1502, 828, 16),
        line("180", 1500, 1037, 37),
    ]
    return lines


def summary_lines() -> list[OcrLine]:
    return [
        line("வாக்காளர் குறித்த விவரங்களின் சுருக்கம்", 60, 26, 400),
        line("A) வாக்காளர்களின் எண்ணிக்கை", 111, 27, 300),
        # I: base roll
        line("அடிப்படைப்", 299, 147, 140),
        line("86", 308, 787, 30), line("85", 308, 884, 30),
        line("0", 308, 991, 16), line("171", 305, 1088, 38),
        # II: additions
        line("சேர்த்தல்", 840, 161, 120),
        line("3", 848, 793, 16), line("6", 849, 889, 16),
        line("0", 850, 993, 16), line("9", 849, 1098, 16),
        # III: deletions
        line("நீக்கல் பட்டியல்", 932, 129, 160),
        line("0", 938, 793, 16), line("0", 938, 889, 16),
        line("0", 939, 991, 16), line("0", 939, 1099, 16),
        # IV: gender reclassification
        line("பாலினப் பிரிவில் மாற்றம் செய்வதால் ஏற்படும் வேறுபாடு", 1022, 118, 500),
        line("0", 1029, 793, 16), line("0", 1029, 890, 16),
        line("0", 1029, 991, 16), line("0", 1029, 1098, 16),
        # Net
        line("திருத்தங்களுக்கு பிறகு பட்டியலிலுள்ள நிகர வாக்காளர்களின்", 1080, 27, 560),
        line("89", 1087, 787, 30), line("91", 1087, 885, 30),
        line("0", 1088, 991, 16), line("180", 1085, 1086, 38),
        # B: corrections
        line("B) திருத்தங்களின் எண்ணிக்கை", 1186, 32, 300),
        line("சிறப்பு தீவிர திருத்தம் 2026", 1327, 220, 300),
        line("2", 1333, 618, 16),
    ]


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------


def test_cover_identity():
    info = parse_cover(cover_lines(), "page1")
    assert info.part_number == "4"
    assert info.ac_number == "57"
    assert info.ac_name == "பாலக்கொடு"
    assert info.pc_number == "10"
    # The reservation status belongs to the seat, not the place.
    assert info.pc_name == "தர்மபுரி"
    assert info.source_page_id == "page1"


def test_cover_revision_block_ignores_the_prose_column():
    """The right-hand blurb repeats dates and years that belong elsewhere."""
    info = parse_cover(cover_lines())
    assert info.revision_year == "2026"
    assert info.qualifying_date == "01-01-2026"
    assert info.publication_date == "23-02-2026"
    assert info.revision_type == "சிறப்பு தீவிர திருத்தம்"


def test_cover_address_block_does_not_shift_by_one_row():
    """Regression: ranking candidates by x alone read the row above.

    Every label shares one value column ~24px below its neighbour, so the
    whole block silently took the previous row's value.
    """
    info = parse_cover(cover_lines())
    assert info.main_town == "பஞ்சப்பள்ளி"
    assert info.post_office == "பஞ்சப்பள்ளி"
    assert info.police_station == "பஞ்சப்பள்ளி"
    assert info.panchayat == "பஞ்சபள்ளி"
    assert info.taluk == "பாலக்கோடு"
    assert info.revenue_division == "தரும்புரி"
    assert info.district == "தர்மபுரி"
    assert info.pincode == "636812"


def test_cover_ward_is_empty_when_the_form_leaves_it_blank():
    """`வார்டு` also appears in the section text, which is not the ward."""
    assert parse_cover(cover_lines()).ward == ""


def test_cover_station_details():
    info = parse_cover(cover_lines())
    assert info.station_number == "4"
    assert info.name.startswith("ஊராட்சி ஒன்றிய துவக்கப்பள்ளி")
    assert "தெற்கு பகுதி" in info.name
    assert info.address == "ஊராட்சி ஒன்றிய துவக்கப்பள்ளி, சொரக்குறிக்கை, 636812"
    assert info.station_type == "பொது"
    assert info.auxiliary_stations == 0
    assert "1-பஞ்சப்பள்ளி" in info.section_details


def test_cover_elector_table():
    info = parse_cover(cover_lines())
    assert (info.serial_start, info.serial_end) == (1, 180)
    assert info.counts.male == 89
    assert info.counts.female == 91
    assert info.counts.third_gender == 0
    assert info.counts.total == 180
    assert info.counts.adds_up


def test_cover_with_no_lines_is_empty_not_an_error():
    info = parse_cover([])
    assert info.part_number == "" and info.counts.total == 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_rows():
    summary = parse_summary(summary_lines(), "page11")
    assert (summary.base.male, summary.base.female, summary.base.total) == (86, 85, 171)
    assert (summary.additions.male, summary.additions.female, summary.additions.total) == (3, 6, 9)
    assert summary.deletions.total == 0
    assert summary.gender_adjustment.total == 0
    assert (summary.net.male, summary.net.female, summary.net.total) == (89, 91, 180)
    assert summary.source_page_id == "page11"


def test_summary_corrections_are_not_read_as_a_count_row():
    """Section B's lone number sits in a different column entirely."""
    assert parse_summary(summary_lines()).corrections == 2


def test_summary_arithmetic_holds():
    summary = parse_summary(summary_lines())
    assert summary.net_is_consistent  # 171 + 9 - 0 + 0 == 180


def test_summary_falls_back_to_printed_order_when_labels_are_destroyed():
    """OCR can mangle a row label past recognition; order still identifies it."""
    lines = [ln for ln in summary_lines() if ln.text not in {"அடிப்படைப்", "சேர்த்தல்"}]
    summary = parse_summary(lines)
    assert summary.base.total == 171
    assert summary.additions.total == 9


# ---------------------------------------------------------------------------
# Whole-file assembly and reconciliation
# ---------------------------------------------------------------------------


def make_page(number: int, page_type: str, lines: list[OcrLine], records: int = 0) -> Page:
    from app.schemas.core import Record

    return Page(
        id=f"p{number}",
        file_id="f1",
        page_number=number,
        page_type=page_type,
        lines=lines,
        records=[
            Record(
                id=f"r{number}-{i}",
                page_id=f"p{number}",
                index=i,
                template_id="electoral_roll_ta",
            )
            for i in range(records)
        ],
    )


def test_reconciliation_matches_when_extraction_is_complete():
    pages = [
        make_page(1, "cover_page", cover_lines()),
        make_page(4, "voter_list_page", [], records=150),
        make_page(10, "supplement_page", [], records=30),
        make_page(11, "summary_page", summary_lines()),
    ]
    metadata = build(pages, "f1")
    assert metadata.reconciliation.extracted_records == 180
    assert metadata.reconciliation.printed_total == 180
    assert metadata.reconciliation.source == "summary"
    assert metadata.reconciliation.difference == 0
    assert metadata.reconciliation.matches


def test_reconciliation_reports_a_shortfall():
    pages = [
        make_page(1, "cover_page", cover_lines()),
        make_page(4, "voter_list_page", [], records=150),
        make_page(11, "summary_page", summary_lines()),
    ]
    metadata = build(pages, "f1")
    assert metadata.reconciliation.difference == -30
    assert not metadata.reconciliation.matches


def test_reconciliation_falls_back_to_the_cover_without_a_summary_sheet():
    pages = [
        make_page(1, "cover_page", cover_lines()),
        make_page(4, "voter_list_page", [], records=180),
    ]
    metadata = build(pages, "f1")
    assert metadata.reconciliation.source == "cover"
    assert metadata.reconciliation.printed_total == 180
    assert metadata.reconciliation.matches
    assert metadata.summary is None


def test_reconciliation_without_either_sheet_makes_no_claim():
    pages = [make_page(4, "voter_list_page", [], records=30)]
    metadata = build(pages, "f1")
    assert metadata.reconciliation.printed_total is None
    assert metadata.reconciliation.difference is None
    assert not metadata.reconciliation.matches
