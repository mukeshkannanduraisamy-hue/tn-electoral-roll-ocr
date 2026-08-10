"""Read the cover and summary sheets of an electoral roll part.

These two pages carry no voter records, which is why the pipeline skips
record extraction on them -- but they carry everything *about* the part: the
constituency, the polling station and its address, and the elector
arithmetic. The last of those is the useful bit, because it gives an
independently printed total to check extraction against.

Parsing strategy
----------------
Both sheets are laid out as columns, and the labels are the least reliable
thing on the page -- the Tamil recogniser mangles them differently on every
document. So values are located by **geometry and shape** wherever possible:

* a label/value pair is "the nearest line to the right, on the same
  baseline, beginning with a colon";
* the elector table is "the bottom-most band holding six integers", found by
  clustering numbers on their y coordinate rather than by reading a header;
* dates and years are matched as patterns within a section's band, so a
  destroyed label costs nothing.

Where a label *is* used it is matched on a stem short enough to survive
(`அடிப்படை` rather than `அடிப்படைப் பட்டியல்`).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from ..schemas.core import OcrLine, Page
from ..schemas.roll import (
    ElectorCounts,
    PartMetadata,
    PartReconciliation,
    PollingStationInfo,
    RollSummary,
)
from .page_classifier import PageType

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"\d{1,2}[-./]\d{1,2}[-./]\d{4}")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
#: A count as it ends up after `_digits` has normalised it. Signed, because the
#: gender-reclassification row genuinely is: `+1` to one column and `-1` to the
#: other when an elector is moved between them.
_INT_RE = re.compile(r"^-?\d{1,6}$")
#: "... : 57 - பாலக்கொடு" -> ("57", "பாலக்கொடு"). The name is optional
#: because the cover splits the parliamentary constituency over two lines.
_NUM_NAME_RE = re.compile(r":\s*(\d+)\s*(?:[-–—]\s*(.*))?$")

# Vertical tolerance for "on the same baseline", as a fraction of line
# height. Values sit a few pixels off their labels; a whole line height
# apart is a different row.
_BAND = 1.2


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_colon(text: str) -> str:
    return _clean(text.lstrip(": \t-"))


#: A count with a letter `o` standing in for a zero. The summary's right-hand
#: columns hold nothing but counts, and OCR returns the table's zeroes as `o`
#: often enough to matter: TAM-16's deletions total reads `117 116 o 233`, and
#: because a row needs four numbers the whole line was dropped, leaving
#: deletions at supplement 1's 226 instead of the printed 233.
#:
#: Deliberately narrow. The table numbers its sections `I`, `IlI`, `IV` and
#: labels one `B`, all in the same columns, so mapping letters to digits
#: generally would invent rows. Only `o` is ambiguous with a digit, and only
#: when it sits among digits.
_INT_WITH_O_RE = re.compile(r"^(?=.*[oO])[0-9oO]{1,6}$")

#: Dashes OCR returns for a minus sign, in the order of likelihood.
_MINUS_CHARS = "-−–—"

#: A count that may be negative. The gender-reclassification row is signed by
#: nature -- an elector moving from female to male is `+1` to one column and
#: `-1` to the other -- and on TAM-19 OCR returns that `-1` faithfully at 0.998
#: confidence. Matching only unsigned digits left the row three numbers long,
#: so it failed the four-number filter and was filled from an unrelated band,
#: putting 11 where the sheet prints 0 and breaking its arithmetic.
_SIGNED_INT_RE = re.compile(rf"^[{_MINUS_CHARS}]\d{{1,6}}$")


def _digits(text: str) -> str:
    """`text` as a plain integer, undoing what OCR does to these columns.

    An `o` among digits is a zero: the summary's right-hand columns hold nothing
    but counts. A leading dash is a minus sign. Neither rewrite is applied more
    widely -- the table numbers its sections `I`, `IlI`, `IV` in these same
    columns and its footer carries dates like `06-04-2026`, and both would
    become counts under a looser rule.
    """
    stripped = _clean(text)
    if _INT_WITH_O_RE.match(stripped):
        return stripped.replace("o", "0").replace("O", "0")
    if _SIGNED_INT_RE.match(stripped):
        return "-" + stripped[1:]
    return stripped


def _is_int(text: str) -> bool:
    return bool(_INT_RE.match(_digits(text)))


def _as_int(text: str) -> int | None:
    stripped = _digits(text)
    return int(stripped) if _INT_RE.match(stripped) else None


def _find(lines: Sequence[OcrLine], *stems: str) -> OcrLine | None:
    """First line containing any of `stems`."""
    for line in lines:
        if any(stem in line.text for stem in stems):
            return line
    return None


def _value_right_of(lines: Sequence[OcrLine], label: OcrLine) -> str:
    """The value printed to the right of `label`, on the same baseline.

    Nearest baseline wins, and only then leftmost. Ranking by x alone reads
    the wrong row whenever the band is wide enough to touch its neighbour --
    the address block's rows are ~24px apart and share one value column, so
    every field silently took the row above it and the whole block shifted
    by one. Nearest-baseline is unambiguous: a real value sits within a few
    pixels of its label, a neighbouring row a full row-pitch away.
    """
    tolerance = max(label.bbox.h, 1.0) * _BAND
    candidates = [
        ln for ln in lines
        if ln is not label
        and ln.bbox.x >= label.bbox.x2 - label.bbox.w * 0.25
        and abs(ln.bbox.cy - label.bbox.cy) <= tolerance
    ]
    if not candidates:
        return ""
    best = min(candidates, key=lambda ln: (abs(ln.bbox.cy - label.bbox.cy), ln.bbox.x))
    return _strip_colon(best.text)


def _between(
    lines: Sequence[OcrLine],
    start: OcrLine | None,
    end: OcrLine | None,
    *,
    max_x: float | None = None,
) -> list[OcrLine]:
    """Lines below `start` and above `end`, optionally left of `max_x`."""
    top = start.bbox.y2 if start else float("-inf")
    bottom = end.bbox.y if end else float("inf")
    return [
        ln for ln in lines
        if top <= ln.bbox.cy <= bottom
        and (max_x is None or ln.bbox.x < max_x)
    ]


def _number_bands(
    lines: Sequence[OcrLine], *, min_x: float = 0.0, size: int | None = None
) -> list[tuple[float, list[OcrLine]]]:
    """Group integer-only lines into horizontal bands, top to bottom.

    Returns (band centre y, lines sorted left to right). `size` filters to
    bands holding exactly that many numbers, which is how the elector table
    is told apart from a stray page number.
    """
    numeric = [
        ln for ln in lines
        if _is_int(ln.text) and ln.bbox.x >= min_x
    ]
    bands: list[list[OcrLine]] = []
    for line in sorted(numeric, key=lambda ln: ln.bbox.cy):
        tolerance = max(line.bbox.h, 1.0) * _BAND
        if bands and abs(line.bbox.cy - bands[-1][0].bbox.cy) <= tolerance:
            bands[-1].append(line)
        else:
            bands.append([line])

    result = [
        (sum(ln.bbox.cy for ln in band) / len(band), sorted(band, key=lambda ln: ln.bbox.x))
        for band in bands
    ]
    if size is not None:
        result = [b for b in result if len(b[1]) == size]
    return result


def _counts_from(band: Sequence[OcrLine]) -> ElectorCounts:
    """Read male / female / third-gender / total off the rightmost 4 numbers."""
    values = [_as_int(ln.text) or 0 for ln in band][-4:]
    while len(values) < 4:
        values.insert(0, 0)
    return ElectorCounts(
        male=values[0], female=values[1], third_gender=values[2], total=values[3]
    )


# ---------------------------------------------------------------------------
# Cover sheet
# ---------------------------------------------------------------------------


def parse_cover(lines: list[OcrLine], page_id: str = "") -> PollingStationInfo:
    """Read the part and polling-station details off a cover page."""
    info = PollingStationInfo(source_page_id=page_id)
    if not lines:
        return info

    ordered = sorted(lines, key=lambda ln: (ln.bbox.cy, ln.bbox.x))
    page_width = max(ln.bbox.x2 for ln in ordered)
    mid_x = page_width * 0.42

    # --- identity -----------------------------------------------------------
    part = _find(ordered, "பாகம் எண்")
    if part:
        digits = re.search(r"\d+", part.text.split(":")[-1])
        info.part_number = digits.group() if digits else ""

    assembly = _find(ordered, "சட்டமன்றத்")
    if assembly:
        match = _NUM_NAME_RE.search(_clean(assembly.text))
        if match:
            info.ac_number = match.group(1)
            info.ac_name = _clean(match.group(2) or "")

    parliament = _find(ordered, "நாடாளுமன்ற")
    if parliament:
        match = _NUM_NAME_RE.search(_clean(parliament.text))
        if match:
            info.pc_number = match.group(1)
            info.pc_name = _clean(match.group(2) or "")
        if not info.pc_name:
            # The name wrapped onto the next line: "- தர்மபுரி (பொது)".
            below = [
                ln for ln in ordered
                if ln.bbox.cy > parliament.bbox.cy
                and ln.bbox.x < mid_x
                and ln.bbox.cy - parliament.bbox.cy < parliament.bbox.h * 3
            ]
            if below:
                info.pc_name = _strip_colon(below[0].text)
        # Both names carry a trailing reservation status -- "(பொது)",
        # "(தனி)" -- which belongs to the seat, not to the place.
        info.pc_name = re.sub(r"\s*\(.*?\)\s*$", "", info.pc_name).strip()
        info.ac_name = re.sub(r"\s*\(.*?\)\s*$", "", info.ac_name).strip()

    # --- revision block -----------------------------------------------------
    # Section 1 runs from its own heading to the section 2 heading. Only the
    # left half: the right half holds a prose description of the revision
    # that is full of dates and years belonging to other things.
    revision = _between(
        ordered,
        _find(ordered, "திருத்தத்தின் விவரங்கள்"),
        _find(ordered, "பாகத்தின் விவரங்கள்"),
        max_x=mid_x,
    )
    dates = [m.group() for ln in revision for m in [_DATE_RE.search(ln.text)] if m]
    if dates:
        info.qualifying_date = dates[0]
        info.publication_date = dates[-1] if len(dates) > 1 else ""
    years = [m.group() for ln in revision for m in [_YEAR_RE.search(_clean(ln.text))] if m
             and _clean(ln.text) == m.group()]
    if years:
        info.revision_year = years[0]
    # The revision's name is the longest piece of prose in the block.
    prose = [_clean(ln.text) for ln in revision if not _DATE_RE.search(ln.text)]
    prose = [p for p in prose if len(p) > 8 and not p.isdigit()]
    if prose:
        info.revision_type = max(prose, key=len)

    # --- the part's area ----------------------------------------------------
    for field, *stems in (
        ("main_town", "முக்கிய நகரம்", "நகரம்/கிராமம்"),
        ("post_office", "அஞ்சல் அலுவலகம்"),
        ("police_station", "காவல் நிலைய"),
        ("panchayat", "பஞ்சாயத்து"),
        ("taluk", "வட்டம்"),
        ("revenue_division", "கோட்டம்"),
        ("district", "மாவட்டம்"),
        ("pincode", "அஞ்சல் குறியீட்டு"),
    ):
        label = _find(ordered, *stems)
        if label:
            setattr(info, field, _value_right_of(ordered, label))

    # `வார்டு` also appears inside the section description, so it is matched
    # only in the label column to the right of the section text.
    ward_label = next(
        (ln for ln in ordered if _clean(ln.text) == "வார்டு" and ln.bbox.x > mid_x), None
    )
    if ward_label:
        info.ward = _value_right_of(ordered, ward_label)

    if info.pincode:
        digits = re.search(r"\d{6}", info.pincode)
        info.pincode = digits.group() if digits else ""

    section = _between(
        ordered,
        _find(ordered, "பாகத்தின் கீழ் வரும் பிரிவின்", "வரும் பிரிவின்"),
        _find(ordered, "வாக்குச் சாவடியின் விவரங்கள்"),
        max_x=mid_x,
    )
    info.section_details = " ".join(_clean(ln.text) for ln in section).strip()

    # --- the station --------------------------------------------------------
    name_lines = _between(
        ordered,
        _find(ordered, "சாவடியின் எண் மற்றும் பெயர்"),
        _find(ordered, "சாவடியின் முகவரி"),
        max_x=mid_x,
    )
    info.name = " ".join(_clean(ln.text) for ln in name_lines).strip()
    if info.name:
        match = re.match(r"^(\d+)\s*[-–—]\s*(.*)$", info.name)
        if match:
            info.station_number = match.group(1)
            info.name = _clean(match.group(2))

    address_lines = _between(
        ordered,
        _find(ordered, "சாவடியின் முகவரி"),
        _find(ordered, "வாக்காளர்களின் எண்ணிக்கை"),
        max_x=mid_x,
    )
    info.address = " ".join(_clean(ln.text) for ln in address_lines).strip()

    kind = _find(ordered, "சாவடியின் வகைப்பாடு")
    if kind:
        info.station_type = _value_right_of(ordered, kind)

    auxiliary = _find(ordered, "சாவடிகளின் எண்ணிக்கை")
    if auxiliary:
        info.auxiliary_stations = _as_int(_value_right_of(ordered, auxiliary)) or 0

    # --- elector table ------------------------------------------------------
    # "from serial | to serial | male | female | third gender | total".
    table = _between(ordered, _find(ordered, "வாக்காளர்களின் எண்ணிக்கை"), None)
    six = _number_bands(table, size=6)
    if six:
        band = six[-1][1]
        info.serial_start = _as_int(band[0].text)
        info.serial_end = _as_int(band[1].text)
        info.counts = _counts_from(band)
    else:
        # Serial columns can be missed when the range is a single digit; a
        # bare four-number band is still the elector breakdown.
        four = _number_bands(table, size=4)
        if four:
            info.counts = _counts_from(four[-1][1])

    if info.counts.total and not info.counts.adds_up:
        logger.warning(
            "Cover elector counts do not add up (%d+%d+%d != %d) on page %s",
            info.counts.male, info.counts.female, info.counts.third_gender,
            info.counts.total, page_id or "?",
        )

    return info


# ---------------------------------------------------------------------------
# Summary sheet
# ---------------------------------------------------------------------------

#: Row label stems, in the order the statutory form prints them. Order is
#: the fallback when a label is too mangled to match.
_SUMMARY_ROWS = (
    ("base", ("அடிப்படை",)),
    ("additions", ("சேர்த்தல்",)),
    ("deletions", ("நீக்கல்",)),
    ("gender_adjustment", ("பாலின",)),
    ("net", ("நிகர",)),
)

# Only these two are printed as several supplement rows plus a total. Restricting
# the override keeps a stray "total" reading from clobbering a single-row figure.
_SUBTOTALLED_ROWS = frozenset({"additions", "deletions"})

# "Total", with the spellings OCR returns for it.
_TOTAL_STEMS = ("மொத்தம்", "மொத்தம", "மாத்தம்", "மொததம்")


# Page kinds that can carry the rest of a summary table. The legend sheet is the
# one that does in practice: on TAM-16 the net row shares page 33 with the
# deletion-reason key, and the classifier calls that page a legend.
_SUMMARY_CONTINUATION_TYPES = frozenset({
    PageType.SUMMARY_PAGE.value,
    PageType.LEGEND_PAGE.value,
    PageType.BLANK_OR_SIGNATURE.value,
})


def summary_lines(pages: Sequence[Page]) -> list[OcrLine]:
    """Every line of the summary table, including the pages it runs onto.

    The statutory summary does not always fit one sheet. On TAM-16 the base,
    additions and deletions rows are on page 32 while the `நிகர` net row -- the
    figure the roll certifies, and the only one that closes the arithmetic -- is
    on page 33 beside the legend. Handing the parser the single page classified
    `summary_page` left the net to be filled from an unrelated band.

    Continuation lines are shifted down by the height of the pages before them
    so the rows keep document order across the join, which is what the parser's
    vertical banding depends on. Copies are returned: these lines belong to a
    Page that gets saved.
    """
    ordered = sorted(pages, key=lambda p: p.page_number)
    start = next(
        (
            index
            for index, page in enumerate(ordered)
            if page.page_type == PageType.SUMMARY_PAGE.value
        ),
        None,
    )
    if start is None:
        return []

    collected: list[OcrLine] = list(ordered[start].lines)
    offset = float(ordered[start].height or 0)

    for page in ordered[start + 1:]:
        if page.page_type not in _SUMMARY_CONTINUATION_TYPES:
            break
        if page.records:
            break                       # a sheet with electors is not the table
        for line in page.lines:
            shifted = line.bbox.model_copy(update={"y": line.bbox.y + offset})
            collected.append(line.model_copy(update={"bbox": shifted}))
        offset += float(page.height or 0)

    return collected


def parse_summary(lines: list[OcrLine], page_id: str = "") -> RollSummary:
    """Read the base/additions/deletions/net table off a summary page."""
    summary = RollSummary(source_page_id=page_id)
    if not lines:
        return summary

    ordered = sorted(lines, key=lambda ln: (ln.bbox.cy, ln.bbox.x))
    page_width = max(ln.bbox.x2 for ln in ordered)

    # Section B ("count of corrections") holds a lone number in a different
    # column; keep it out of the four-column table entirely.
    section_b = _find(ordered, "திருத்தங்களின் எண்ணிக்கை")
    table_lines = [
        ln for ln in ordered
        if section_b is None or ln.bbox.cy < section_b.bbox.y
    ]

    # The count columns occupy the right third of the sheet.
    bands = _number_bands(table_lines, min_x=page_width * 0.60, size=4)
    labelled: dict[str, ElectorCounts] = {}
    unclaimed: list[tuple[float, list[OcrLine]]] = []

    # Additions and deletions are printed one row per supplement and then a
    # `மொத்தம்` row that belongs to the category above it. Taking the first row
    # reports supplement 1 as the whole figure, which is what made well-formed
    # rolls look like they failed to reconcile. The category label is carried
    # down the sub-rows so its own total can replace the first reading.
    current_key: str | None = None

    for centre_y, band in bands:
        # Narrow enough that a row does not read its neighbours' labels. At 2.5x
        # the band height the window was wider than the row pitch, so the
        # additions total saw `நீக்கல் பட்டியல்` printed below it and was filed
        # as a deletion.
        tolerance = max(band[0].bbox.h, 1.0) * 1.1
        row_text = " ".join(
            ln.text for ln in table_lines
            if ln.bbox.x < page_width * 0.60
            and abs(ln.bbox.cy - centre_y) <= tolerance
        )

        matched = next(
            (
                key
                for key, stems in _SUMMARY_ROWS
                if any(stem in row_text for stem in stems)
            ),
            None,
        )

        if matched is not None:
            current_key = matched
            labelled.setdefault(matched, _counts_from(band))
        elif (
            current_key in _SUBTOTALLED_ROWS
            and any(stem in row_text for stem in _TOTAL_STEMS)
        ):
            labelled[current_key] = _counts_from(band)
        else:
            unclaimed.append((centre_y, band))

    # Fall back to printed order for any row whose label did not survive OCR.
    for key, _stems in _SUMMARY_ROWS:
        if key in labelled:
            continue
        if unclaimed:
            _y, band = unclaimed.pop(0)
            labelled[key] = _counts_from(band)

    for key, counts in labelled.items():
        setattr(summary, key, counts)

    if section_b is not None:
        below = [ln for ln in ordered if ln.bbox.cy > section_b.bbox.cy]
        corrections = _number_bands(below, size=1)
        if corrections:
            summary.corrections = _as_int(corrections[0][1][0].text) or 0

    if summary.net.total and not summary.net_is_consistent:
        logger.warning(
            "Summary does not reconcile on page %s: %d + %d - %d + %d != %d",
            page_id or "?", summary.base.total, summary.additions.total,
            summary.deletions.total, summary.gender_adjustment.total,
            summary.net.total,
        )

    return summary


# ---------------------------------------------------------------------------
# Whole-file assembly
# ---------------------------------------------------------------------------


def build(pages: Sequence[Page], file_id: str = "") -> PartMetadata:
    """Derive a part's metadata from its already-classified pages.

    Reconciliation prefers the summary sheet's net total over the cover's
    count. They agree on a well-formed roll, but the summary is the figure
    the document itself derives and certifies, and on a part whose
    supplements changed the count it is the one that stayed current.
    """
    metadata = PartMetadata(file_id=file_id)

    cover = next(
        (p for p in pages if p.page_type == PageType.COVER_PAGE.value), None
    )
    summary_page = next(
        (p for p in pages if p.page_type == PageType.SUMMARY_PAGE.value), None
    )

    if cover is not None:
        metadata.station = parse_cover(cover.lines, cover.id)
    if summary_page is not None:
        metadata.summary = parse_summary(summary_lines(pages), summary_page.id)

    printed: int | None = None
    source = ""
    if metadata.summary and metadata.summary.net.total:
        printed, source = metadata.summary.net.total, "summary"
    elif metadata.station and metadata.station.counts.total:
        printed, source = metadata.station.counts.total, "cover"

    metadata.reconciliation = PartReconciliation(
        extracted_records=sum(len(p.records) for p in pages),
        printed_total=printed,
        source=source,
    )

    if printed is not None and not metadata.reconciliation.matches:
        logger.warning(
            "File %s does not reconcile: extracted %d records, %s sheet prints %d",
            file_id or "?", metadata.reconciliation.extracted_records,
            source, printed,
        )

    return metadata
