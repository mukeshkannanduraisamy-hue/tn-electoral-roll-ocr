"""Fallback template: one record per OCR text line.

This is what makes the app a general-purpose OCR tool rather than an
electoral-roll-only tool. It makes no assumptions about layout, so it works
on any PDF -- invoices, letters, reports -- at the cost of producing flat
rows instead of structured fields.
"""

from __future__ import annotations

import uuid

from ..schemas.core import (
    ColumnDef,
    ColumnType,
    FieldValue,
    Issue,
    IssueCode,
    IssueSeverity,
    LayoutInfo,
    OcrLine,
    Record,
)


class GenericTemplate:
    id = "generic"
    name = "Generic Text"
    description = (
        "Layout-agnostic fallback: emits one row per recognised text line with "
        "its confidence and position. Works on any document."
    )
    languages = ["*"]

    def columns(self) -> list[ColumnDef]:
        return [
            ColumnDef(key="line", label="#", type=ColumnType.NUMBER, width=70),
            ColumnDef(key="text", label="Extracted Text", type=ColumnType.TEXT,
                      width=560, required=True),
        ]

    def expected_grid(self) -> tuple[int, int] | None:
        return None

    def consensus_fields(self) -> list[str]:
        # Free text with no repeated-entity structure -- majority voting
        # across arbitrary prose would do harm, not good.
        return []

    def detect(self, lines: list[OcrLine], page_size: tuple[int, int]) -> float:
        # Always applicable, but always the lowest-ranked option so any
        # specific template that matches at all wins.
        return 0.05 if lines else 0.0

    def parse(
        self,
        lines: list[OcrLine],
        layout: LayoutInfo,
        page_id: str,
        page_size: tuple[int, int],
    ) -> list[Record]:
        records: list[Record] = []
        for i, line in enumerate(lines):
            record = Record(
                id=uuid.uuid4().hex[:12],
                page_id=page_id,
                index=i,
                template_id=self.id,
                bbox=line.bbox,
            )
            record.fields["line"] = FieldValue(
                key="line", original_value=str(i + 1), confidence=1.0
            )
            record.fields["text"] = FieldValue(
                key="text",
                original_value=line.text,
                confidence=line.confidence,
                bbox=line.bbox,
                source_line_ids=[line.id],
            )
            records.append(record)
        return records

    def validate(self, records: list[Record]) -> None:
        for record in records:
            text = record.fields.get("text")
            if not text:
                continue
            if not text.value.strip():
                text.issues.append(
                    Issue(code=IssueCode.MISSING_REQUIRED, severity=IssueSeverity.ERROR,
                          message="Empty text", field="text")
                )
            elif text.confidence < 0.60:
                text.issues.append(
                    Issue(
                        code=IssueCode.LOW_CONFIDENCE,
                        severity=IssueSeverity.WARNING,
                        message=f"Low OCR confidence ({text.confidence:.0%})",
                        field="text",
                    )
                )


TEMPLATE = GenericTemplate()
