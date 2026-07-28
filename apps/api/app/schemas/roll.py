"""Part-level metadata: the cover sheet and the statutory summary table.

A roll PDF describes one *part* of one assembly constituency. Everything
that identifies that part -- which polling station serves it, where the
station is, how many electors it holds -- is printed on the cover, and the
arithmetic behind the elector count is printed on the summary sheet.

Those two pages are worth more than their page count suggests: together they
give an independently printed total to check the extracted records against.
See `PartReconciliation`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ElectorCounts(BaseModel):
    """One row of the male / female / third-gender / total breakdown."""

    male: int = 0
    female: int = 0
    third_gender: int = 0
    total: int = 0

    @property
    def adds_up(self) -> bool:
        """Whether the parts sum to the printed total.

        A row that fails this was misread -- the roll's own arithmetic is
        not in question -- so it is the cheapest available check on the
        numbers coming out of OCR.
        """
        return self.male + self.female + self.third_gender == self.total


class PollingStationInfo(BaseModel):
    """Everything the cover sheet says about the part and its station."""

    # --- identity --------------------------------------------------------
    part_number: str = ""
    ac_number: str = ""
    ac_name: str = ""
    pc_number: str = ""
    pc_name: str = ""

    # --- revision --------------------------------------------------------
    revision_year: str = ""
    revision_type: str = ""
    qualifying_date: str = ""
    publication_date: str = ""

    # --- the part's area -------------------------------------------------
    section_details: str = ""
    """Section number and name, e.g. "1-பஞ்சப்பள்ளி (வ.கி) மற்றும் (ஊ), வார்டு 2"."""
    main_town: str = ""
    ward: str = ""
    post_office: str = ""
    police_station: str = ""
    panchayat: str = ""
    taluk: str = ""
    revenue_division: str = ""
    district: str = ""
    pincode: str = ""

    # --- the station -----------------------------------------------------
    station_number: str = ""
    name: str = ""
    """Station name and building, as printed on one run of lines."""
    address: str = ""
    station_type: str = ""
    """ஆண் / பெண் / பொது -- men's, women's or general."""
    auxiliary_stations: int = 0

    # --- electors --------------------------------------------------------
    serial_start: int | None = None
    serial_end: int | None = None
    counts: ElectorCounts = Field(default_factory=ElectorCounts)

    source_page_id: str = ""


class RollSummary(BaseModel):
    """The summary sheet: base roll, supplements, and the net total.

    ``net`` is the figure the roll itself certifies, arrived at as
    base + additions - deletions +/- gender reclassification.
    """

    base: ElectorCounts = Field(default_factory=ElectorCounts)
    additions: ElectorCounts = Field(default_factory=ElectorCounts)
    deletions: ElectorCounts = Field(default_factory=ElectorCounts)
    gender_adjustment: ElectorCounts = Field(default_factory=ElectorCounts)
    net: ElectorCounts = Field(default_factory=ElectorCounts)
    corrections: int = 0

    source_page_id: str = ""

    @property
    def net_is_consistent(self) -> bool:
        """Whether the printed net total follows from the printed components.

        Failing this means one of the five rows was misread, not that the
        roll is wrong.
        """
        derived = (
            self.base.total
            + self.additions.total
            - self.deletions.total
            + self.gender_adjustment.total
        )
        return derived == self.net.total


class PartReconciliation(BaseModel):
    """Extracted record count against the totals the document prints.

    The whole point of reading the cover and summary sheets: the roll states
    how many electors it contains, so extraction can be checked rather than
    trusted. A mismatch localises the problem -- a page that was skipped, a
    grid that was misread -- without anyone opening the PDF.
    """

    extracted_records: int = 0
    printed_total: int | None = None
    """Net total from the summary sheet, falling back to the cover's count."""
    source: str = ""
    """Which sheet `printed_total` came from: `summary`, `cover`, or empty."""

    @property
    def difference(self) -> int | None:
        if self.printed_total is None:
            return None
        return self.extracted_records - self.printed_total

    @property
    def matches(self) -> bool:
        return self.printed_total is not None and self.difference == 0


class PartMetadata(BaseModel):
    """Everything derived from a file's non-voter pages."""

    file_id: str = ""
    station: PollingStationInfo | None = None
    summary: RollSummary | None = None
    reconciliation: PartReconciliation = Field(default_factory=PartReconciliation)
