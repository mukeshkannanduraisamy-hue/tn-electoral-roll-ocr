"""CRUD, promotion and reporting for the curated voter table."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import require_user
from ..db import FileRow, PageRow, RecordRow, UserRow, VoterRow, get_session, row_to_record
from ..schemas.voters import (
    SORTABLE,
    PromotionConflict,
    PromotionRequest,
    PromotionResult,
    Voter,
    VoterCreate,
    VoterPage,
    VoterUpdate,
    normalise_epic,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _search_text(row: VoterRow) -> str:
    parts = [
        row.epic, row.name, row.relation_name, row.house_number,
        row.part_number, row.constituency, str(row.serial or ""),
    ]
    return " ".join(p for p in parts if p).lower()


def _apply_fields(row: VoterRow, data: dict, username: str) -> None:
    for key, value in data.items():
        if value is not None:
            setattr(row, key, value)
    row.search_text = _search_text(row)
    row.updated_by = username
    row.updated_at = _utcnow()


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("", response_model=VoterPage)
def list_voters(
    search: str | None = Query(None, description="Matches name, EPIC, house, part"),
    gender: str | None = Query(None),
    part_number: str | None = Query(None),
    source_file_id: str | None = Query(None),
    verified: bool | None = Query(None),
    min_age: int | None = Query(None, ge=0, le=200),
    max_age: int | None = Query(None, ge=0, le=200),
    sort: str = Query("created_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> VoterPage:
    if sort not in SORTABLE:
        raise HTTPException(
            400, f"Cannot sort by {sort!r}. Allowed: {', '.join(sorted(SORTABLE))}"
        )

    def apply(stmt):
        if search:
            stmt = stmt.where(VoterRow.search_text.like(f"%{search.lower().strip()}%"))
        if gender:
            stmt = stmt.where(VoterRow.gender == gender)
        if part_number:
            stmt = stmt.where(VoterRow.part_number == part_number)
        if source_file_id:
            stmt = stmt.where(VoterRow.source_file_id == source_file_id)
        if verified is not None:
            stmt = stmt.where(VoterRow.verified.is_(verified))
        if min_age is not None:
            stmt = stmt.where(VoterRow.age >= min_age)
        if max_age is not None:
            stmt = stmt.where(VoterRow.age <= max_age)
        return stmt

    direction = asc if order == "asc" else desc
    rows = session.execute(
        apply(select(VoterRow))
        .order_by(direction(getattr(VoterRow, sort)), VoterRow.id)
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    total = session.execute(
        apply(select(func.count()).select_from(VoterRow))
    ).scalar_one()

    return VoterPage(
        items=[Voter.model_validate(r) for r in rows],
        total=total, offset=offset, limit=limit,
    )


@router.get("/stats")
def voter_stats(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict:
    """Summary figures for the dashboard cards."""
    total = session.execute(select(func.count()).select_from(VoterRow)).scalar_one()

    by_gender = dict(
        session.execute(
            select(VoterRow.gender, func.count()).group_by(VoterRow.gender)
        ).all()
    )
    by_relation = dict(
        session.execute(
            select(VoterRow.relation_type, func.count()).group_by(VoterRow.relation_type)
        ).all()
    )

    # Age histogram in decade buckets, computed in SQL rather than by pulling
    # every row into Python.
    age_rows = session.execute(
        select(VoterRow.age).where(VoterRow.age.isnot(None))
    ).scalars().all()
    buckets: dict[str, int] = {}
    for age in age_rows:
        low = min(int(age) // 10 * 10, 90)
        buckets[f"{low}-{low + 9}" if low < 90 else "90+"] = (
            buckets.get(f"{low}-{low + 9}" if low < 90 else "90+", 0) + 1
        )

    verified = session.execute(
        select(func.count()).select_from(VoterRow).where(VoterRow.verified.is_(True))
    ).scalar_one()

    parts = session.execute(
        select(VoterRow.part_number, func.count())
        .where(VoterRow.part_number != "")
        .group_by(VoterRow.part_number)
        .order_by(desc(func.count()))
        .limit(20)
    ).all()

    return {
        "total": total,
        "verified": verified,
        "unverified": total - verified,
        "by_gender": by_gender,
        "by_relation_type": by_relation,
        "age_buckets": dict(sorted(buckets.items())),
        "by_part": [{"part": p or "(none)", "count": c} for p, c in parts],
        "average_age": round(sum(age_rows) / len(age_rows), 1) if age_rows else None,
        "missing_age": total - len(age_rows),
    }


@router.get("/export")
def export_voters(
    format: str = Query("xlsx", pattern="^(xlsx|csv|pdf)$"),
    search: str | None = Query(None),
    gender: str | None = Query(None),
    part_number: str | None = Query(None),
    source_file_id: str | None = Query(None),
    verified: bool | None = Query(None),
    include_meta: bool = Query(False, description="Add provenance and audit columns"),
    sort: str = Query("serial"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50_000, ge=1, le=200_000),
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> Response:
    """Download the (filtered) voter table.

    Takes the same filters as the list endpoint, so what you see on screen is
    what you get in the file.
    """
    from ..services import voter_export

    if sort not in SORTABLE:
        raise HTTPException(400, f"Cannot sort by {sort!r}")

    stmt = select(VoterRow)
    if search:
        stmt = stmt.where(VoterRow.search_text.like(f"%{search.lower().strip()}%"))
    if gender:
        stmt = stmt.where(VoterRow.gender == gender)
    if part_number:
        stmt = stmt.where(VoterRow.part_number == part_number)
    if source_file_id:
        stmt = stmt.where(VoterRow.source_file_id == source_file_id)
    if verified is not None:
        stmt = stmt.where(VoterRow.verified.is_(verified))

    direction = asc if order == "asc" else desc
    rows = session.execute(
        stmt.order_by(direction(getattr(VoterRow, sort)), VoterRow.id).limit(limit)
    ).scalars().all()

    try:
        content, filename, media_type = voter_export.export(rows, format, include_meta)
    except voter_export.ExportError as exc:
        # Most often: no Tamil-capable font for PDF. The message says how to
        # fix it, so surface it rather than a generic 500.
        raise HTTPException(400, str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{voter_id}", response_model=Voter)
def get_voter(
    voter_id: str,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> Voter:
    row = session.get(VoterRow, voter_id)
    if row is None:
        raise HTTPException(404, "Voter not found")
    return Voter.model_validate(row)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


@router.post("", response_model=Voter, status_code=201)
def create_voter(
    payload: VoterCreate,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> Voter:
    existing = session.execute(
        select(VoterRow).where(VoterRow.epic == payload.epic)
    ).scalar_one_or_none()
    if existing is not None:
        # Checked explicitly so the message names the conflicting record,
        # rather than surfacing a raw IntegrityError.
        raise HTTPException(
            409,
            f"EPIC {payload.epic} already belongs to '{existing.name}' "
            f"(record {existing.id})",
        )

    row = VoterRow(id=uuid.uuid4().hex[:12], created_by=user.username)
    _apply_fields(row, payload.model_dump(), user.username)
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:  # lost a race between the check and the insert
        session.rollback()
        raise HTTPException(409, f"EPIC {payload.epic} already exists") from exc
    return Voter.model_validate(row)


@router.patch("/{voter_id}", response_model=Voter)
def update_voter(
    voter_id: str,
    payload: VoterUpdate,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> Voter:
    row = session.get(VoterRow, voter_id)
    if row is None:
        raise HTTPException(404, "Voter not found")

    data = payload.model_dump(exclude_unset=True)

    if "epic" in data and data["epic"] and data["epic"] != row.epic:
        clash = session.execute(
            select(VoterRow).where(
                VoterRow.epic == data["epic"], VoterRow.id != voter_id
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(
                409,
                f"EPIC {data['epic']} already belongs to '{clash.name}' "
                f"(record {clash.id})",
            )

    # `verified` is a real boolean, so `if value is not None` in _apply_fields
    # would drop an explicit False. Handle it before the generic pass.
    if "verified" in data and data["verified"] is not None:
        row.verified = bool(data.pop("verified"))

    _apply_fields(row, data, user.username)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "EPIC already exists") from exc
    return Voter.model_validate(row)


@router.delete("/{voter_id}", status_code=204, response_class=Response)
def delete_voter(
    voter_id: str,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> Response:
    row = session.get(VoterRow, voter_id)
    if row is not None:
        logger.info("User %r deleted voter %s (%s)", user.username, voter_id, row.epic)
        session.delete(row)
    # Idempotent: deleting something already gone is a success.
    return Response(status_code=204)


@router.post("/bulk-delete")
def bulk_delete(
    payload: dict,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    ids = payload.get("voter_ids") or []
    if not ids:
        raise HTTPException(400, "No voter_ids provided")
    rows = session.execute(select(VoterRow).where(VoterRow.id.in_(ids))).scalars().all()
    for row in rows:
        session.delete(row)
    logger.info("User %r bulk-deleted %d voters", user.username, len(rows))
    return {"deleted": len(rows), "requested": len(ids)}


# ---------------------------------------------------------------------------
# Promotion from OCR output
# ---------------------------------------------------------------------------


def _field_value(record, key: str) -> str:
    field = record.fields.get(key)
    if field is None:
        return ""
    return (field.edited_value if field.edited_value is not None
            else field.original_value) or ""


@router.post("/promote", response_model=PromotionResult)
def promote_records(
    payload: PromotionRequest,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> PromotionResult:
    """Copy reviewed OCR records into the curated table.

    A duplicate EPIC is reported as a conflict rather than raising, so one
    bad row cannot abort a 30-record page. That is the entire reason the two
    tables are separate.
    """
    stmt = select(RecordRow)
    if payload.record_ids:
        stmt = stmt.where(RecordRow.id.in_(payload.record_ids))
    elif payload.page_id:
        stmt = stmt.where(RecordRow.page_id == payload.page_id)
    elif payload.file_id:
        stmt = stmt.where(RecordRow.file_id == payload.file_id)
    else:
        raise HTTPException(400, "Provide record_ids, page_id or file_id")

    if payload.only_clean:
        stmt = stmt.where(RecordRow.error_count == 0)

    rows = session.execute(stmt.order_by(RecordRow.page_number, RecordRow.index)).scalars().all()
    if not rows:
        raise HTTPException(404, "No matching records to promote")

    # Page/file context, fetched once rather than per record.
    file_names = dict(session.execute(select(FileRow.id, FileRow.name)).all())
    page_meta = {
        p.id: (p.payload or {}) for p in
        session.execute(
            select(PageRow).where(PageRow.id.in_({r.page_id for r in rows}))
        ).scalars().all()
    }

    result = PromotionResult()
    seen_in_batch: dict[str, str] = {}

    for row in rows:
        record = row_to_record(row)
        epic = normalise_epic(_field_value(record, "epic"))
        name = _field_value(record, "name")

        if not epic:
            result.conflicts.append(PromotionConflict(
                record_id=row.id, reason="No EPIC number on this record",
                incoming_name=name))
            result.skipped += 1
            continue

        # A page can contain the same misread EPIC twice; catch that before
        # the database does, so the message is useful.
        if epic in seen_in_batch:
            result.conflicts.append(PromotionConflict(
                record_id=row.id, epic=epic,
                reason="Duplicate EPIC within this same batch",
                incoming_name=name))
            result.skipped += 1
            continue

        existing = session.execute(
            select(VoterRow).where(VoterRow.epic == epic)
        ).scalar_one_or_none()

        if existing is not None and payload.on_conflict == "skip":
            result.conflicts.append(PromotionConflict(
                record_id=row.id, epic=epic,
                reason="EPIC already exists in the voter database",
                existing_voter_id=existing.id, existing_name=existing.name,
                incoming_name=name))
            result.skipped += 1
            continue

        meta = page_meta.get(row.page_id, {})
        header = meta.get("header_text", "") or ""
        age_raw = _field_value(record, "age")
        serial_raw = _field_value(record, "serial")

        values = {
            "epic": epic,
            "name": name,
            "serial": int(serial_raw) if serial_raw.isdigit() else None,
            "relation_type": _field_value(record, "relation_type"),
            "relation_name": _field_value(record, "relation_name"),
            "house_number": _field_value(record, "house_number"),
            "age": int(age_raw) if age_raw.isdigit() else None,
            "gender": _field_value(record, "gender"),
            "constituency": header[:255],
            "source_record_id": row.id,
            "source_page_id": row.page_id,
            "source_file_id": row.file_id,
            "source_file_name": file_names.get(row.file_id, ""),
            "page_number": row.page_number,
        }

        if existing is not None:  # on_conflict == "update"
            _apply_fields(existing, values, user.username)
            result.updated += 1
            result.voter_ids.append(existing.id)
        else:
            voter = VoterRow(id=uuid.uuid4().hex[:12], created_by=user.username)
            _apply_fields(voter, values, user.username)
            session.add(voter)
            result.created += 1
            result.voter_ids.append(voter.id)

        seen_in_batch[epic] = row.id

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, f"Promotion failed on a uniqueness conflict: {exc}") from exc

    logger.info(
        "User %r promoted %d created / %d updated / %d skipped",
        user.username, result.created, result.updated, result.skipped,
    )
    return result
