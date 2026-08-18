"""Settling one section name per part, across all its pages.

Both problems this solves are invisible from a single page, which is why it runs
after the page fan-in alongside spelling consensus rather than in the template.

**A section reads several ways.** OCR returned four spellings of one section
across TAM-16, differing only in noise, so one section became four stored values
and any grouping on it split silently. The section *number* is digits and
survives OCR intact, so it is the identity; the most-seen spelling becomes the
name for every page carrying that number.

**Supplement pages print no section.** Pages 23-31 of TAM-16 carry the
constituency and part number and then go straight to their supplement title,
leaving 223 electors with nothing. A printed section header applies until another
replaces it, so a page without one inherits the nearest preceding section.

Inheritance is reported rather than hidden. A carried section is a reading of the
document, not something printed on that page, and the distinction belongs in the
record for anyone auditing it later.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..schemas.core import Issue, IssueCode, IssueSeverity, Page

CARRIED_NOTE = (
    "Section carried from an earlier page; this page does not print one"
)

# Sections are printed numbered -- "1-பனைகுளம் (வ.கி) ...". The digits are the
# only part OCR never garbles, so they identify the section and the words after
# them are treated as one noisy observation of its name.
_SECTION_NUMBER_RE = re.compile(r"^\s*(\d+)")


@dataclass(frozen=True)
class SectionResolution:
    by_page: dict[int, str]
    """Section to store for each page, after normalising and carrying forward."""

    inherited_pages: frozenset[int]
    """Pages whose section was carried from an earlier page, not printed on it."""


def _section_number(section: str) -> str | None:
    match = _SECTION_NUMBER_RE.match(section)
    return match.group(1) if match else None


def _canonical_names(sections: list[str]) -> dict[str, str]:
    """The spelling to keep for each section number.

    Ties are broken by longest-then-alphabetical rather than by whichever page
    happened to be seen first, so reprocessing a file cannot shuffle the value
    stored against an elector.
    """
    seen: dict[str, Counter] = {}
    for section in sections:
        number = _section_number(section)
        if number is None:
            continue
        seen.setdefault(number, Counter())[section] += 1

    canonical: dict[str, str] = {}
    for number, counts in seen.items():
        best = max(counts.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]))
        canonical[number] = best[0]
    return canonical


def reconcile_sections(by_page: Mapping[int, str]) -> SectionResolution:
    """One section per page for a whole file.

    `by_page` maps page number to the section read off that page, empty where
    none was printed. Pages before the first section keep nothing -- there is
    nothing to carry from, and inventing one would be worse than a blank.
    """
    if not by_page:
        return SectionResolution(by_page={}, inherited_pages=frozenset())

    canonical = _canonical_names([s for s in by_page.values() if s.strip()])

    resolved: dict[int, str] = {}
    inherited: set[int] = set()
    running = ""

    for page in sorted(by_page):
        section = by_page[page].strip()
        if section:
            number = _section_number(section)
            running = canonical.get(number, section) if number else section
            resolved[page] = running
        else:
            resolved[page] = running
            if running:
                inherited.add(page)

    return SectionResolution(by_page=resolved, inherited_pages=frozenset(inherited))


@dataclass(frozen=True)
class ApplyReport:
    records_changed: int
    pages_inherited: int


def section_printed_on(page: Page) -> str:
    """The section this page printed, read back off its own records.

    Every record on a page carries that page's header, so the first non-empty
    one speaks for the page.

    A section this pass previously carried in does not count as printed --
    otherwise a second run would mistake its own inference for evidence, and a
    page that never printed a section would look like a source for later ones.
    """
    for record in page.records:
        if any(issue.message == CARRIED_NOTE for issue in record.issues):
            return ""
        field = record.fields.get("section_name")
        if field is not None and field.original_value.strip():
            return field.original_value.strip()
    return ""


def apply_sections(pages: Sequence[Page]) -> ApplyReport:
    """Write the settled section onto every record, in place.

    Safe to run twice: the note explaining an inherited section is replaced
    rather than appended, so reprocessing a file does not accumulate copies.
    """
    resolution = reconcile_sections(
        {page.page_number: section_printed_on(page) for page in pages}
    )

    changed = 0
    for page in pages:
        section = resolution.by_page.get(page.page_number, "")
        if not section:
            continue
        carried = page.page_number in resolution.inherited_pages

        for record in page.records:
            field = record.fields.get("section_name")
            if field is None:
                continue
            if field.original_value != section:
                field.original_value = section
                changed += 1

            record.issues = [
                issue for issue in record.issues if issue.message != CARRIED_NOTE
            ]
            if carried:
                record.issues.append(
                    Issue(
                        code=IssueCode.UNPARSED_TEXT,
                        severity=IssueSeverity.INFO,
                        field="section_name",
                        message=CARRIED_NOTE,
                    )
                )

    return ApplyReport(
        records_changed=changed, pages_inherited=len(resolution.inherited_pages)
    )
