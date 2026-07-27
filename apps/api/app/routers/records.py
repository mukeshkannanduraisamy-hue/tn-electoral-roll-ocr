"""Record querying and editing.

Filtering happens in SQL against the denormalised columns written by
`db.record_to_row`, so the review queue stays fast on large corpora instead
of deserialising every record to count its issues.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import RecordRow, get_session, record_to_row, row_to_record
from ..schemas.core import Record

logger = logging.getLogger(__name__)
router = APIRouter()


class RecordPage(BaseModel):
    items: list[Record]
    total: int
    offset: int
    limit: int


class FieldEdit(BaseModel):
    key: str
    value: str | None = None
    """None resets the field to its original OCR value."""


class RecordUpdate(BaseModel):
    edits: list[FieldEdit] = Field(default_factory=list)
    reviewed: bool | None = None


class BulkUpdate(BaseModel):
    record_ids: list[str]
    reviewed: bool | None = None
    accept_suggestions: bool = False
    reset_all: bool = False


@router.get("", response_model=RecordPage)
def list_records(
    file_id: str | None = Query(None),
    page_id: str | None = Query(None),
    search: str | None = Query(None, description="Case-insensitive substring"),
    only_issues: bool = Query(False, description="Records with validation errors"),
    only_edited: bool = Query(False),
    unreviewed: bool = Query(False),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    max_confidence: float | None = Query(None, ge=0.0, le=1.0),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    session: Session = Depends(get_session),
) -> RecordPage:
    stmt = select(RecordRow)
    count_stmt = select(func.count()).select_from(RecordRow)

    def apply(statement):
        if file_id:
            statement = statement.where(RecordRow.file_id == file_id)
        if page_id:
            statement = statement.where(RecordRow.page_id == page_id)
        if search:
            statement = statement.where(
                RecordRow.search_text.like(f"%{search.lower()}%")
            )
        if only_issues:
            statement = statement.where(RecordRow.error_count > 0)
        if only_edited:
            statement = statement.where(RecordRow.edited.is_(True))
        if unreviewed:
            statement = statement.where(RecordRow.reviewed.is_(False))
        if min_confidence is not None:
            statement = statement.where(RecordRow.mean_confidence >= min_confidence)
        if max_confidence is not None:
            statement = statement.where(RecordRow.mean_confidence <= max_confidence)
        return statement

    stmt = apply(stmt).order_by(
        RecordRow.file_id, RecordRow.page_number, RecordRow.index
    ).offset(offset).limit(limit)
    total = session.execute(apply(count_stmt)).scalar_one()

    rows = session.execute(stmt).scalars().all()
    return RecordPage(
        items=[row_to_record(r) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/stats")
def record_stats(
    file_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict:
    """Counts for the dashboard header and review-queue badge."""
    base = select(func.count()).select_from(RecordRow)
    if file_id:
        base = base.where(RecordRow.file_id == file_id)

    def count(condition=None) -> int:
        stmt = base if condition is None else base.where(condition)
        return session.execute(stmt).scalar_one()

    total = count()
    return {
        "total": total,
        "with_errors": count(RecordRow.error_count > 0),
        "with_warnings": count(RecordRow.warning_count > 0),
        "edited": count(RecordRow.edited.is_(True)),
        "reviewed": count(RecordRow.reviewed.is_(True)),
        "clean": count(RecordRow.error_count == 0),
    }


# ── BULK must be declared BEFORE /{record_id} to avoid route shadowing ──────

@router.post("/bulk")
def bulk_update(
    payload: BulkUpdate, session: Session = Depends(get_session)
) -> dict:
    """Apply an action to many records at once (multi-select in the table).

    Registered *before* /{record_id} so FastAPI does not mistake the literal
    string "bulk" for a record id.
    """
    if not payload.record_ids:
        raise HTTPException(400, "No record_ids provided")

    rows = (
        session.execute(
            select(RecordRow).where(RecordRow.id.in_(payload.record_ids))
        )
        .scalars()
        .all()
    )

    changed = 0
    for row in rows:
        record = row_to_record(row)
        touched = False

        if payload.reset_all:
            for field in record.fields.values():
                if field.edited_value is not None:
                    field.edited_value = None
                    touched = True

        if payload.accept_suggestions:
            for field in record.fields.values():
                if field.suggested_value and field.value != field.suggested_value:
                    field.edited_value = field.suggested_value
                    touched = True

        if payload.reviewed is not None and record.reviewed != payload.reviewed:
            record.reviewed = payload.reviewed
            touched = True

        if touched:
            _persist(session, row, record)
            changed += 1

    return {"updated": changed, "requested": len(payload.record_ids)}


@router.get("/{record_id}", response_model=Record)
def get_record(record_id: str, session: Session = Depends(get_session)) -> Record:
    row = session.get(RecordRow, record_id)
    if row is None:
        raise HTTPException(404, "Record not found")
    return row_to_record(row)


@router.patch("/{record_id}", response_model=Record)
def update_record(
    record_id: str,
    payload: RecordUpdate,
    session: Session = Depends(get_session),
) -> Record:
    row = session.get(RecordRow, record_id)
    if row is None:
        raise HTTPException(404, "Record not found")

    record = row_to_record(row)

    for edit in payload.edits:
        field = record.fields.get(edit.key)
        if field is None:
            raise HTTPException(400, f"Unknown field: {edit.key}")
        # None means "reset to the original OCR reading".
        field.edited_value = edit.value
        # A human decision supersedes the machine's suggestion.
        if edit.value is not None:
            field.suggested_value = None

    if payload.reviewed is not None:
        record.reviewed = payload.reviewed

    _persist(session, row, record)
    return record


@router.post("/{record_id}/reset", response_model=Record)
def reset_record(record_id: str, session: Session = Depends(get_session)) -> Record:
    """Discard every edit on a record, restoring the raw OCR values."""
    row = session.get(RecordRow, record_id)
    if row is None:
        raise HTTPException(404, "Record not found")

    record = row_to_record(row)
    for field in record.fields.values():
        field.edited_value = None
    _persist(session, row, record)
    return record


def _persist(session: Session, row: RecordRow, record: Record) -> None:
    """Write a record back, refreshing every denormalised column."""
    data = record_to_row(record, row.file_id, row.page_number)
    for key, value in data.items():
        setattr(row, key, value)
