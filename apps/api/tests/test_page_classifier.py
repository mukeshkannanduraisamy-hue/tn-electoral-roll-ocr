"""Page classification over the SIR roll page types.

The line texts below are what PaddleOCR actually returned for the reference
document (part 4 of AC 57-Palakkodu), not what the PDF renders -- the Tamil
recogniser doubles and drops vowel signs, and rules that match the printed
spelling do not survive contact with it.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.services.page_classifier import (  # noqa: E402
    VOTER_BEARING,
    PageType,
    classify_page,
    normalize_bbox,
    strip_furniture,
)

# The header and footer repeated on every page from 2 onward. Any rule keyed
# on constituency or part vocabulary matches these, on all twelve pages.
HEADER = [
    "சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர் : 57-பாலக்கொடு",
    "பாகம் எண் : 4",
]
FOOTER = [
    "வயது 01-01-2026",
    "பட்டியல் வெளியிடப்பட்ட நாள் :- 23-02-2026",
    "மொத்தப் பக்கங்கள் 12 - பக்கம் 4",
]


def line(text: str, y: float, x: float = 30.0) -> OcrLine:
    return OcrLine(
        id=uuid.uuid4().hex[:8],
        text=text,
        confidence=0.95,
        bbox=BBox(x=x, y=y, w=300, h=16),
        polygon=[],
    )


def page(body: list[str], *, furniture: bool = True, start_y: float = 60.0):
    """Build a page: running header, body lines, running footer."""
    lines = []
    if furniture:
        lines += [line(HEADER[0], 4), line(HEADER[1], 6, x=1026)]
    lines += [line(t, start_y + i * 20) for i, t in enumerate(body)]
    if furniture:
        lines += [line(t, 1639 + i) for i, t in enumerate(FOOTER)]
    return lines


def voter_cell_lines(serial: int, epic: str, y: float) -> list[str]:
    return [
        f"{serial}",
        epic,
        "பெயர் : சுசீலா",
        "கணவர் பெயர்: சண்முகம்",
        "வீட்டு எண் : 5-177",
        "வயது : 34 பாலினம் : பெண்",
    ]


def voter_body(count: int = 12) -> list[str]:
    body: list[str] = []
    for i in range(count):
        body += voter_cell_lines(i + 1, f"ZHT0{300000 + i}", 0)
    return body


# ---------------------------------------------------------------------------
# Running furniture
# ---------------------------------------------------------------------------


def test_running_header_and_footer_are_stripped():
    lines = page(["வாக்காளர் பதிவு அலுவலரின்", "கயாப்பம்"])
    body = strip_furniture(lines)
    assert [ln.text for ln in body] == [
        "வாக்காளர் பதிவு அலுவலரின்",
        "கயாப்பம்",
    ]


def test_running_header_alone_does_not_make_a_cover_page():
    """Regression: the header names the constituency and the part on *every*
    page, so a cover rule reading it classified all twelve as cover_page."""
    for body in (voter_body(12), ["E- Expired, S- Shifted, R-Repeated"]):
        result = classify_page(page(body))
        assert result.page_type is not PageType.COVER_PAGE


# ---------------------------------------------------------------------------
# One case per page type
# ---------------------------------------------------------------------------


def test_cover_page():
    result = classify_page(page([
        "வாக்காளர் பட்டியல் 2026 S22 தமிழ்நாடு",
        "1. திருத்தத்தின் விவரங்கள்",
        "திருத்தப்படும் ஆண்டு",
        "தகுதியேற்படுத்தும்",
        "திருத்தத்தின் வகை",
        "2. பாகத்தின் விவரங்கள் மற்றும் வாக்குச்சாவடிக்கான பரப்பளவு",
    ]))
    assert result.page_type is PageType.COVER_PAGE


def test_map_photo_page():
    result = classify_page(page([
        "Nazri Naksha", "Google Map View",
        "Polling Station Building Front View", "Cad View", "Key MAP View",
    ]))
    assert result.page_type is PageType.MAP_PHOTO_PAGE


def test_voter_list_page():
    result = classify_page(page(voter_body(12)))
    assert result.page_type is PageType.VOTER_LIST_PAGE
    assert result.metadata["epic_count"] >= 10


def test_supplement_page_is_distinguished_from_the_base_roll():
    """Same cell anatomy as a voter grid; only the banner above it differs."""
    lines = page(["சேர்த்தல் பட்டி்யல் 1 (19-12-202510-02-2026 )"] + voter_body(9),
                 start_y=25)
    result = classify_page(lines)
    assert result.page_type is PageType.SUPPLEMENT_PAGE


def test_additions_wording_in_prose_is_not_a_supplement():
    """`சேர்த்தல்` also appears in the cover blurb and the summary table."""
    result = classify_page(page([
        "வாக்காளர் குறித்த விவரங்களின் சுருக்கம்",
        "A) வாக்காளர்களின் எண்ணிக்கை",
        "சேர்த்தல் பட்டியல்",
        "நீக்கல் பட்டியல்",
    ]))
    assert result.page_type is PageType.SUMMARY_PAGE


def test_summary_page():
    result = classify_page(page([
        "வாக்காளர் குறித்த விவரங்களின் சுருக்கம்",
        "A) வாக்காளர்களின் எண்ணிக்கை",
        "அடிப்படைப் பட்டியல்", "86", "85", "0", "171",
    ]))
    assert result.page_type is PageType.SUMMARY_PAGE


def test_legend_page():
    result = classify_page(page([
        "E- Expired, S- Shifted, R-Repeated, M - Missing, Q- Disqualified",
    ]))
    assert result.page_type is PageType.LEGEND_PAGE


def test_signature_page():
    result = classify_page(page(["வாக்காளர் பதிவு அலுவலரின்", "கயாப்பம்"]))
    assert result.page_type is PageType.BLANK_OR_SIGNATURE


def test_page_with_no_text_at_all():
    assert classify_page([]).page_type is PageType.BLANK_OR_SIGNATURE


# ---------------------------------------------------------------------------
# What the pipeline gates on
# ---------------------------------------------------------------------------


def test_only_grid_pages_are_voter_bearing():
    assert VOTER_BEARING == {PageType.VOTER_LIST_PAGE, PageType.SUPPLEMENT_PAGE}


# ---------------------------------------------------------------------------
# LayoutLMv3 box normalisation
# ---------------------------------------------------------------------------


def test_normalize_bbox_scales_polygon_to_0_1000():
    poly = [(0, 0), (500, 0), (500, 400), (0, 400)]
    assert normalize_bbox(poly, 1000, 800) == [0, 0, 500, 500]


def test_normalize_bbox_clamps_and_never_degenerates():
    # Out of bounds, and zero-height: both must still yield a valid box.
    assert normalize_bbox([-50, -50, 5000, 5000], 1000, 1000) == [0, 0, 1000, 1000]
    x0, y0, x1, y1 = normalize_bbox([10, 10, 10, 10], 1000, 1000)
    assert x0 < x1 and y0 < y1


def test_normalize_bbox_survives_a_zero_sized_page():
    assert normalize_bbox([0, 0, 10, 10], 0, 0) == [0, 0, 1000, 1000]
