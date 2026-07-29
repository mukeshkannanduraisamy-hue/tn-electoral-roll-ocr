"""Document template protocol.

A template knows how to turn the OCR output of one page into structured
records, and how to tell whether a given record is trustworthy. Everything
document-specific lives behind this interface so the rest of the pipeline
stays generic.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schemas.core import ColumnDef, LayoutInfo, OcrLine, Record


@runtime_checkable
class DocumentTemplate(Protocol):
    """Contract every template implements."""

    id: str
    name: str
    description: str
    languages: list[str]

    def columns(self) -> list[ColumnDef]:
        """Column definitions for the table view / exports."""
        ...

    def detect(self, lines: list[OcrLine], page_size: tuple[int, int]) -> float:
        """Confidence in [0,1] that this template fits the page."""
        ...

    def expected_grid(self) -> tuple[int, int] | None:
        """(rows, cols) if this template expects a fixed grid, else None."""
        ...

    def consensus_fields(self) -> list[str]:
        """Field keys eligible for cross-corpus spelling consensus.

        Optional -- return [] (or omit) to opt out. Only free-text proper
        nouns belong here; never identifiers or numbers.
        """
        ...

    def parse(
        self,
        lines: list[OcrLine],
        layout: LayoutInfo,
        page_id: str,
        page_size: tuple[int, int],
    ) -> list[Record]:
        """Turn OCR lines into records."""
        ...

    def validate(self, records: list[Record]) -> None:
        """Attach validation issues to records, in place."""
        ...
