"""Page classification for electoral roll documents.

Why this exists
---------------
A SIR roll PDF is not a stack of voter grids. A 12-page part file holds a
cover, a signature sheet, a map/photo sheet, six voter grids, a supplement
grid, a summary table and a legend. Only the grids carry voters.

Without this step every page is pushed through the voter template, and the
non-voter pages emit dozens of junk "records" -- on the reference document
that was 139 phantom records out of 331, i.e. more noise than signal.

Classifying on running furniture
--------------------------------
The single biggest trap: **every page from 2 onward repeats the same running
header** (`சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர் : 57-...` plus
`பாகம் எண் : 4`) and the same footer (`... பக்கம் N`). Any rule keyed on
constituency or part vocabulary therefore fires on all twelve pages. The
furniture is stripped first, and every rule below reads only the page body.

Markers are taken from what PaddleOCR actually returns on the reference
corpus, not from what the PDF renders -- the Tamil recogniser drops and
doubles vowel signs, so `சேர்த்தல் பட்டியல்` comes back as
`சேர்த்தல் பட்டி்யல்`. Rules anchor on the stable stem (`சேர்த்தல்`)
rather than the full printed phrase.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from ..schemas.core import LayoutInfo, OcrLine, normalize_box

logger = logging.getLogger(__name__)


class PageType(str, Enum):
    COVER_PAGE = "cover_page"
    MAP_PHOTO_PAGE = "map_photo_page"
    VOTER_LIST_PAGE = "voter_list_page"
    SUPPLEMENT_PAGE = "supplement_page"
    SUMMARY_PAGE = "summary_page"
    LEGEND_PAGE = "legend_page"
    BLANK_OR_SIGNATURE = "blank_or_signature"
    OTHER = "other"


#: Page types that carry voter records and are worth running the grid
#: template over. Everything else should skip parsing entirely.
VOTER_BEARING = frozenset({PageType.VOTER_LIST_PAGE, PageType.SUPPLEMENT_PAGE})


@dataclass
class PageClassificationResult:
    page_type: PageType
    confidence: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

#: Lines repeated on every page. Matched by content rather than by a
#: geometric band, because the supplement banner sits only ~20px below the
#: running header and a band wide enough to catch one would swallow the other.
#
# Matched on stems rather than whole printed phrases: the recogniser mangles
# these lines differently on different pages (`சட்டமன்றத் தொகுதியின்` comes
# back as `சட்டமன்றத் தாகுதியின்` on the legend sheet, `வெளியிடப்பட்ட` loses
# its ெ), and a stem that survives every variant is worth more than an exact
# match that survives most of them.
_FURNITURE = (
    "பாகம் எண்",           # "Part No :"                 -- header, right
    "சட்டமன்றத்",           # "Assembly constituency ..." -- header, left
    "பக்கங்கள்",            # "Total pages N - page M"    -- footer, right
    "யிடப்பட்ட நாள்",       # "Date of publication"       -- footer, centre
)

#: The footer's qualifying-date cell, "வயது 01-01-2026" (age as on ...).
#: Needs a pattern rather than a stem so it cannot swallow a record's own
#: `வயது : 34 பாலினம் : பெண்` line.
_FURNITURE_RE = (
    re.compile(r"வயது\s*[:\-]?\s*\d{1,2}[-/]\d{1,2}[-/]\d{4}"),
)

#: EPIC as the recogniser hands it over: 2-4 letters then 6-9 digits.
#: Deliberately looser than the canonical AAA1234567 so a misread letter
#: still counts as evidence that this is a voter page.
_EPIC_RE = re.compile(r"^[A-Z]{2,4}\d{6,9}$")

_IDENT_TRANSLATE = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1"})


def _epic_like(text: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    return bool(_EPIC_RE.match(cleaned.translate(_IDENT_TRANSLATE)))


def strip_furniture(lines: Sequence[OcrLine]) -> list[OcrLine]:
    """Drop the running header and footer that every page repeats."""
    return [
        ln for ln in lines
        if not any(f in ln.text for f in _FURNITURE)
        and not any(p.search(ln.text) for p in _FURNITURE_RE)
    ]


def normalize_bbox(
    box: Sequence[Sequence[float]] | Sequence[float],
    img_width: int,
    img_height: int,
) -> list[int]:
    """Normalize a bounding box to LayoutLMv3 [x0, y0, x1, y1] on a 0-1000 grid.

    Accepts either a 4-point polygon (PaddleOCR's native form) or a flat
    [xmin, ymin, xmax, ymax]. Guarantees 0 <= x0 < x1 <= 1000 and
    0 <= y0 < y1 <= 1000, so downstream consumers never see a degenerate box.
    """
    if not img_width or not img_height or img_width <= 0 or img_height <= 0:
        return [0, 0, 1000, 1000]

    if isinstance(box, (list, tuple)) and len(box) >= 4 and isinstance(box[0], (list, tuple)):
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
    elif isinstance(box, (list, tuple)) and len(box) == 4:
        xmin, ymin, xmax, ymax = (float(v) for v in box)
    else:
        return [0, 0, 1000, 1000]

    return normalize_box(xmin, ymin, xmax, ymax, img_width, img_height)


# ---------------------------------------------------------------------------
# Marker vocabulary
# ---------------------------------------------------------------------------

# Sheet of station imagery. The captions are printed in English on an
# otherwise Tamil document, which makes them the most reliable markers here.
_MAP_MARKERS = (
    "nazri naksha", "google map", "cad view", "key map",
    "polling station front", "polling station building",
)

# Deletion-reason key, printed in English on the final sheet.
_LEGEND_MARKERS = ("expired", "shifted", "repeated", "disqualified", "missing")

# Title of the statutory summary table: "Summary of elector details".
# `சுருக்கம்` (summary) appears on no other page type.
_SUMMARY_MARKERS = ("சுருக்கம்",)
# Secondary evidence, used only to raise confidence.
_SUMMARY_SUPPORT = ("எண்ணிக்கை", "அடிப்படைப்", "நீக்கல்", "சேர்த்தல்")

# Cover-only vocabulary from part 1 ("Details of revision") and part 2
# ("Details of the part and polling area"). None of these repeat elsewhere.
_COVER_MARKERS = (
    "திருத்தத்தின் விவரங்கள்",    # "Details of revision"
    "திருத்தப்படும் ஆண்டு",       # "Year of revision"
    "தகுதியேற்படுத்தும்",         # "Qualifying date"
    "திருத்தத்தின் வகை",          # "Type of revision"
    "பாகத்தின் விவரங்கள்",        # "Details of the part"
    "வாக்குச் சாவடியின்",         # "Of the polling station"
    "அஞ்சல் அலுவலகம்",            # "Post office"
    "காவல் நிலையம்",              # "Police station"
)

# Supplement banner: "Additions list N (date - date)" / "Deletions list N".
_SUPPLEMENT_MARKERS = ("சேர்த்தல்", "நீக்கல்", "திருத்தப்")

# Field labels inside a voter cell.
_VOTER_LABELS = ("பெயர்", "வயது", "பாலினம்", "வீட்டு")


def _hits(blob: str, markers: Sequence[str]) -> int:
    return sum(1 for m in markers if m in blob)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify_page(
    lines: list[OcrLine],
    layout: LayoutInfo | None = None,
    img_width: int = 1000,
    img_height: int = 1000,
) -> PageClassificationResult:
    """Decide what kind of page this is.

    Rules run most-specific first. Each one reads the page *body* -- the
    running header and footer are stripped up front, since they are identical
    on every page and would otherwise satisfy any constituency-keyed rule.
    """
    body = strip_furniture(lines)

    if not body:
        return PageClassificationResult(
            page_type=PageType.BLANK_OR_SIGNATURE,
            confidence=0.99,
            reason="No text outside the running header and footer",
            metadata={"body_lines": 0},
        )

    blob = " ".join(ln.text for ln in body)
    lowered = blob.lower()
    epic_count = sum(1 for ln in body if _epic_like(ln.text))
    cell_count = len(layout.cells) if layout and layout.cells else 0
    meta = {"body_lines": len(body), "epic_count": epic_count, "cell_count": cell_count}

    # 1. Station imagery -----------------------------------------------------
    map_hits = _hits(lowered, _MAP_MARKERS)
    if map_hits >= 2:
        return PageClassificationResult(
            PageType.MAP_PHOTO_PAGE, 0.98,
            f"Station imagery captions present ({map_hits} of {len(_MAP_MARKERS)})",
            meta,
        )

    # 2. Deletion-reason legend ---------------------------------------------
    # Checked before the summary and cover rules because the legend sheet is
    # otherwise almost empty and would fall through to blank_or_signature.
    legend_hits = _hits(lowered, _LEGEND_MARKERS)
    if legend_hits >= 3 and epic_count == 0:
        return PageClassificationResult(
            PageType.LEGEND_PAGE, 0.96,
            f"Deletion-reason key present ({legend_hits} symbols defined)",
            meta,
        )

    # 3. Statutory summary table --------------------------------------------
    if _hits(blob, _SUMMARY_MARKERS) and epic_count < 3:
        support = _hits(blob, _SUMMARY_SUPPORT)
        return PageClassificationResult(
            PageType.SUMMARY_PAGE, min(0.99, 0.90 + 0.02 * support),
            "Elector-summary table title present with no voter records",
            meta | {"support_markers": support},
        )

    # 4. Cover / part metadata ----------------------------------------------
    cover_hits = _hits(blob, _COVER_MARKERS)
    if cover_hits >= 2 and epic_count < 3:
        return PageClassificationResult(
            PageType.COVER_PAGE, min(0.99, 0.85 + 0.03 * cover_hits),
            f"Revision and part metadata present ({cover_hits} cover markers)",
            meta | {"cover_markers": cover_hits},
        )

    # 5. Supplement grid -----------------------------------------------------
    # Same cell anatomy as a base-roll page, distinguished only by the banner
    # above the grid. Must be tested before the voter rule, which would
    # otherwise claim it.
    if epic_count >= 3 and _supplement_banner(body):
        return PageClassificationResult(
            PageType.SUPPLEMENT_PAGE, 0.95,
            "Voter grid beneath an additions/deletions supplement banner",
            meta,
        )

    # 6. Base-roll voter grid ------------------------------------------------
    label_hits = _hits(blob, _VOTER_LABELS)
    if epic_count >= 5 or cell_count >= 5 or (label_hits >= 3 and len(body) >= 20):
        confidence = 0.99 if epic_count >= 10 else 0.90
        return PageClassificationResult(
            PageType.VOTER_LIST_PAGE, confidence,
            f"Voter grid: {epic_count} EPIC-shaped tokens, {cell_count} cells",
            meta,
        )

    # 7. Signature sheet -----------------------------------------------------
    if len(body) <= 4:
        return PageClassificationResult(
            PageType.BLANK_OR_SIGNATURE, 0.93,
            f"Only {len(body)} line(s) of body text and no voter fields",
            meta,
        )

    return PageClassificationResult(
        PageType.OTHER, 0.50, "No rule matched confidently", meta
    )


def _supplement_banner(body: Sequence[OcrLine]) -> bool:
    """True when an additions/deletions banner sits above the grid.

    Scoped to the topmost band of the body: `சேர்த்தல்` also appears in the
    cover blurb and in the summary table's row labels, where it says nothing
    about the page being a supplement.
    """
    if not body:
        return False
    top = min(ln.bbox.y for ln in body)
    band = top + max(ln.bbox.h for ln in body) * 2.0
    return any(
        any(m in ln.text for m in _SUPPLEMENT_MARKERS)
        for ln in body
        if ln.bbox.y <= band
    )
