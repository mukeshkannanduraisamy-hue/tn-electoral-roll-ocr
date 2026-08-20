"""CRUD, promotion and reporting for the curated voter table."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import shutil
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import asc, desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..auth import require_user
from ..db import (
    AuditLogRow,
    FileRow,
    OCRBlockRow,
    PageRow,
    PhotoRow,
    PollingStationRow,
    RecordRow,
    UserRow,
    VoterRow,
    get_session,
    record_audit,
    row_to_record,
)
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


#: Fields whose changes are worth an audit entry. Bookkeeping columns
#: (`search_text`, `updated_by`) change on every write and would bury the
#: edits a reviewer actually made.
AUDITED_FIELDS = (
    "epic", "serial", "name", "relation_type", "relation_name",
    "house_number", "age", "gender", "part_number", "constituency",
    "verified", "notes", "is_deleted", "deletion_reason",
)


def _apply_fields(
    row: VoterRow,
    data: dict,
    username: str,
    session: Session | None = None,
    *,
    audit_action: str = "updated",
) -> int:
    """Apply `data` to `row`, logging each field that actually changed.

    Returns the number of audited changes. Auditing happens here rather than
    in each endpoint because this is the one place every write path goes
    through -- create, update and promotion all call it, and a per-endpoint
    log is one forgotten call away from an incomplete trail.
    """
    changes = 0
    for key, value in data.items():
        if value is None:
            continue
        previous = getattr(row, key, None)
        setattr(row, key, value)

        if session is None or key not in AUDITED_FIELDS or previous == value:
            continue
        record_audit(
            session,
            row.id,
            action=audit_action,
            user=username,
            field_name=key,
            old_value=None if previous is None else str(previous),
            new_value=str(value),
            file_id=row.source_file_id,
            page_id=row.source_page_id,
        )
        changes += 1

    row.search_text = _search_text(row)
    row.updated_by = username
    row.updated_at = _utcnow()
    return changes


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("", response_model=VoterPage)
def list_voters(
    search: str | None = Query(None, description="Matches name, EPIC, house, part"),
    gender: str | None = Query(None),
    relation_type: str | None = Query(None),
    part_number: str | None = Query(None),
    constituency: str | None = Query(None),
    house_number: str | None = Query(None),
    has_photo: bool | None = Query(None),
    polling_station_id: str | None = Query(None),
    is_supplement: bool | None = Query(None),
    is_deleted: bool | None = Query(None, description="True: only struck-off electors; False: only active"),
    min_serial: int | None = Query(None, ge=0),
    max_serial: int | None = Query(None, ge=0),
    min_page: int | None = Query(None, ge=1),
    max_page: int | None = Query(None, ge=1),
    source_file_name: str | None = Query(None),
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
        if relation_type:
            stmt = stmt.where(VoterRow.relation_type == relation_type)
        if part_number:
            stmt = stmt.where(VoterRow.part_number == part_number)
        if constituency:
            stmt = stmt.where(VoterRow.constituency == constituency)
        if house_number:
            stmt = stmt.where(VoterRow.house_number.like(f"%{house_number.strip()}%"))
        if has_photo is not None:
            if has_photo:
                stmt = stmt.where(VoterRow.photo_path.isnot(None), VoterRow.photo_path != "")
            else:
                stmt = stmt.where((VoterRow.photo_path.is_(None)) | (VoterRow.photo_path == ""))
        if polling_station_id:
            stmt = stmt.where(VoterRow.polling_station_id == polling_station_id)
        if is_supplement is not None:
            stmt = stmt.where(VoterRow.is_supplement.is_(is_supplement))
        if is_deleted is not None:
            stmt = stmt.where(VoterRow.is_deleted.is_(is_deleted))
        if min_serial is not None:
            stmt = stmt.where(VoterRow.serial >= min_serial)
        if max_serial is not None:
            stmt = stmt.where(VoterRow.serial <= max_serial)
        if min_page is not None:
            stmt = stmt.where(VoterRow.page_number >= min_page)
        if max_page is not None:
            stmt = stmt.where(VoterRow.page_number <= max_page)
        if source_file_name:
            stmt = stmt.where(VoterRow.source_file_name.like(f"%{source_file_name.strip()}%"))
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

    age_counts = session.execute(
        select(
            func.floor(VoterRow.age / 10).label("decade"),
            func.count()
        )
        .where(VoterRow.age.isnot(None))
        .group_by("decade")
    ).all()
    buckets: dict[str, int] = {}
    for decade, count in age_counts:
        if decade is None:
            continue
        d = int(decade)
        low = min(d * 10, 90)
        label = f"{low}-{low + 9}" if low < 90 else "90+"
        buckets[label] = buckets.get(label, 0) + count

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

    avg_age_row = session.execute(
        select(func.avg(VoterRow.age)).where(VoterRow.age.isnot(None))
    ).scalar_one_or_none()
    missing_age = session.execute(
        select(func.count()).select_from(VoterRow).where(VoterRow.age.is_(None))
    ).scalar_one()

    return {
        "total": total,
        "verified": verified,
        "unverified": max(total - verified, 0),
        "by_gender": {k or "Unknown": v for k, v in by_gender.items()},
        "by_relation": {k or "Unknown": v for k, v in by_relation.items()},
        "age_buckets": buckets,
        "by_part": [{"part": str(p), "count": cnt} for p, cnt in parts],
        "average_age": round(float(avg_age_row), 1) if avg_age_row is not None else None,
        "missing_age": missing_age,
    }


@router.get("/extracted-options")
def get_extracted_options(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict:
    """Returns Assembly Constituencies, Part Numbers, and voter counts extracted into DB."""
    constituencies_rows = session.execute(
        select(VoterRow.constituency).distinct().where(VoterRow.constituency != "")
    ).scalars().all()
    constituencies = sorted(list(set(constituencies_rows)))
    constituencies = sorted(list(set(constituencies_rows)))

    part_counts = session.execute(
        select(VoterRow.constituency, VoterRow.part_number, func.count(VoterRow.id))
        .where(VoterRow.part_number != "")
        .group_by(VoterRow.constituency, VoterRow.part_number)
        .order_by(VoterRow.part_number)
    ).all()

    # Build a lookup of section names from the notes field per part
    part_section_names: dict[str, str] = {}
    section_rows = session.execute(
        select(VoterRow.part_number, VoterRow.notes)
        .where(VoterRow.part_number != "")
        .where(VoterRow.notes != "")
    ).all()
    for part, notes in section_rows:
        if part not in part_section_names and notes:
            # Try to find section name from the search_text or notes
            pass

    # Also check source_file_name for section info
    source_names = session.execute(
        select(VoterRow.part_number, VoterRow.source_file_name)
        .where(VoterRow.part_number != "")
        .distinct()
    ).all()
    for part, src in source_names:
        if part not in part_section_names and src:
            part_section_names[part] = src

    ac_parts: dict[str, list[dict]] = {}
    for ac, part, count in part_counts:
        ac_key = ac or constituencies[0]
        if ac_key not in ac_parts:
            ac_parts[ac_key] = []

        # Build a descriptive name from the source file or part number
        src_name = part_section_names.get(str(part), "")
        if src_name:
            short = src_name.replace("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-", "Part ").replace("-WI", "").replace(" (1)", "").replace(".pdf", "")
        else:
            short = f"Part {part}"

        ac_parts[ac_key].append({
            "part_number": str(part),
            "voter_count": count,
            "name": short,
            "location": "58-பென்னாகரம் (Pennagaram)",
            "pin": "636810"
        })

    # Sort parts numerically within each constituency
    for ac_key in ac_parts:
        ac_parts[ac_key].sort(key=lambda p: int(p["part_number"]) if p["part_number"].isdigit() else 0)



    return {
        "districts": ["தர்மபுரி (Dharmapuri)"] if constituencies else [],
        "constituencies": constituencies,
        "parts_by_ac": ac_parts,
    }


#: A household is a handful of people; anything past this is a data-quality
#: problem (a placeholder house number shared by a whole part) and would make
#: the solver's pairwise name matching quadratically slow.
MAX_HOUSEHOLD_ROWS = 200


def _find_voter(session: Session, voter_id: str) -> VoterRow | None:
    if not voter_id:
        return None
    vid = str(voter_id).strip()
    if not vid or vid in ("undefined", "null", "[object Object]"):
        return None

    # 1. Primary key match
    row = session.get(VoterRow, vid)
    if row is not None:
        return row

    # 2. Case-insensitive EPIC match
    row = session.execute(
        select(VoterRow).where(func.upper(VoterRow.epic) == vid.upper())
    ).scalars().first()
    if row is not None:
        return row

    # 3. Numeric serial match
    if vid.isdigit():
        row = session.execute(
            select(VoterRow).where(VoterRow.serial == int(vid))
        ).scalars().first()
        if row is not None:
            return row

    # 4. Partial ID / EPIC match fallback
    row = session.execute(
        select(VoterRow).where(
            (VoterRow.id.like(f"%{vid}%")) | (VoterRow.epic.like(f"%{vid}%"))
        )
    ).scalars().first()
    if row is not None:
        return row

    return None


def resolve_household(session: Session, voter_id: str) -> dict:
    """Household and resolved families for one elector.

    Extracted from the endpoint so the assistant's `household_of` tool answers
    with exactly what the Family tab shows. Two code paths producing two
    different households for the same person is a bug waiting to be reported as
    a data problem.
    """
    target_row = _find_voter(session, voter_id)

    if not target_row:
        raise HTTPException(404, f"Voter {voter_id!r} not found")

    target_dict = Voter.model_validate(target_row).model_dump()

    from ..services.family_tree_solver import (
        building_key,
        is_missing_house,
        resolve_family_trees,
    )

    # Find housemates sharing the same building, or nearby serial numbers when
    # the record carries no house number at all.
    grouping = "serial_window" if is_missing_house(target_row.house_number) else "house"

    if grouping == "house":
        target_building = building_key(target_row.house_number)
        stmt = select(VoterRow)
        # A house number only identifies an address within its own part of the
        # roll; the same number recurs in every other part.
        if target_row.part_number:
            stmt = stmt.where(VoterRow.part_number == target_row.part_number)
        # Narrow in SQL on the leading segment, then confirm in Python with
        # building_key. Matching the raw prefix rather than a SQL-normalised
        # expression keeps one source of truth for the key: SQL only has to be
        # generous, and Python decides membership exactly.
        lead = target_building.split("-")[0]
        if lead:
            stmt = stmt.where(func.upper(func.trim(VoterRow.house_number)).like(f"{lead}%"))
    else:
        target_building = ""
        # Fallback by Part + Serial window (+/- 15)
        stmt = select(VoterRow).where(VoterRow.part_number == target_row.part_number)
        if target_row.serial is not None:
            stmt = stmt.where(
                VoterRow.serial >= max(1, target_row.serial - 15),
                VoterRow.serial <= target_row.serial + 15,
            )

    candidates = session.execute(stmt.order_by(asc(VoterRow.serial))).scalars().all()

    if grouping == "house":
        candidates = [
            r for r in candidates if building_key(r.house_number) == target_building
        ]

    truncated = len(candidates) > MAX_HOUSEHOLD_ROWS
    rows = candidates[:MAX_HOUSEHOLD_ROWS]
    housemates = [Voter.model_validate(r).model_dump() for r in rows]

    # The target must be present even if the filters above excluded it (a blank
    # part number, or a serial outside its own window).
    if not any(m["id"] == voter_id for m in housemates):
        housemates.append(target_dict)

    families = resolve_family_trees(housemates)

    # The spellings this address actually appears under. Worth showing: a
    # reviewer looking at "2-332" needs to know why an elector recorded at
    # "2/332-1" is in the same tree.
    house_variants = sorted(
        {
            (m.get("house_number") or "").strip()
            for m in housemates
            if (m.get("house_number") or "").strip()
        }
    )

    # The family containing the target is the one the UI renders as its canvas;
    # the rest are other people at the same address.
    primary_family_id = next(
        (
            f["family_id"]
            for f in families
            if any(m.get("id") == voter_id for m in f.get("members", []))
        ),
        families[0]["family_id"] if families else None,
    )

    return {
        "target_voter_id": voter_id,
        "household": {
            "house_number": target_row.house_number,
            "building_key": target_building,
            "house_variants": house_variants,
            "part_number": target_row.part_number,
            "constituency": target_row.constituency,
            "size": len(housemates),
            "grouping": grouping,
            "truncated": truncated,
        },
        "primary_family_id": primary_family_id,
        "families": families,
    }


@router.get("/{voter_id}/family-tree")
def get_voter_family_tree(
    voter_id: str,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict:
    """Resolve the voter's household into deterministic family trees.

    Returns the whole household rather than only the component containing the
    voter: when a relationship cannot be resolved the household fragments into
    several one-person families, and returning just one of them would hide real
    people living at the address.
    """
    return resolve_household(session, voter_id)


@router.post("/ai-copilot")
def ai_copilot_endpoint(
    payload: dict,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict:
    """Answer a question, attaching a chart when the question is statistical.

    Figures in ``infographic`` come from SQL, never from the model: the model
    only chooses which measure to chart and writes the surrounding commentary.
    See ``app/services/infographic.py`` for why that split matters.

    The assistant does not change the interface — it answers, and the operator
    decides what to do about it.
    """
    user_message = str(payload.get("message") or "").strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else None

    from ..services import app_settings, infographic as info
    from ..services.nvidia_ai_service import (
        local_infographic_spec,
        narrate_infographic,
        propose_infographic_spec,
        query_nvidia_copilot,
        wants_infographic,
    )

    creds = app_settings.resolve_ai_credentials(session)

    result = query_nvidia_copilot(user_message, creds, context)
    result["infographic"] = None
    result["ai_configured"] = creds.configured

    if not wants_infographic(user_message):
        return result

    raw_spec = propose_infographic_spec(user_message, info.catalogue(), creds)
    try:
        spec = info.validate_spec(raw_spec or {})
    except info.SpecError as exc:
        # The model asked for something outside the vocabulary, or is not
        # configured at all. Fall back to the keyword matcher rather than
        # serving no chart.
        logger.info("Rejected AI infographic spec (%s); using local matcher", exc)
        try:
            spec = info.validate_spec(local_infographic_spec(user_message))
        except info.SpecError:
            return result

    try:
        chart = info.build_infographic(session, spec)
    except Exception:
        logger.exception("Failed to build infographic for %r", user_message)
        return result

    chart["insights"] = narrate_infographic(user_message, chart, creds)
    result["infographic"] = chart
    return result


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
    row = _find_voter(session, voter_id)
    if row is None:
        raise HTTPException(404, "Voter not found")
    return Voter.model_validate(row)


@router.get("/{voter_id}/ocr-blocks")
def get_voter_ocr_blocks(
    voter_id: str,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    """Per-field OCR provenance for one voter.

    Boxes are on the LayoutLMv3 0-1000 grid, so a client scales them by the
    size it is actually displaying the page at rather than by the DPI the
    page happened to be rendered at.
    """
    row = _find_voter(session, voter_id)
    if row is None:
        raise HTTPException(404, "Voter not found")

    blocks = (
        session.execute(
            select(OCRBlockRow)
            .where(OCRBlockRow.record_id == row.source_record_id)
            .order_by(OCRBlockRow.bbox_y0, OCRBlockRow.bbox_x0)
        ).scalars().all()
        if row.source_record_id
        else []
    )

    page = session.get(PageRow, row.source_page_id) if row.source_page_id else None
    confidences = [b.confidence for b in blocks if b.confidence > 0]

    return {
        "voter_id": voter_id,
        "record_id": row.source_record_id,
        "page_id": row.source_page_id,
        "page_number": row.page_number,
        "page_width": page.width if page else 0,
        "page_height": page.height if page else 0,
        "page_type": page.page_type if page else "",
        # The scale the boxes are expressed on, so a client never has to
        # guess or hard-code it.
        "bbox_scale": 1000,
        "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "min_confidence": round(min(confidences), 4) if confidences else 0.0,
        "blocks": [
            {
                "id": b.id,
                "field_name": b.field_name,
                "bbox": [b.bbox_x0, b.bbox_y0, b.bbox_x1, b.bbox_y1],
                "raw_text": b.raw_text,
                "corrected_text": b.corrected_text,
                "edited": bool(b.corrected_text),
                "confidence": round(b.confidence, 4),
            }
            for b in blocks
        ],
    }


@router.get("/{voter_id}/history")
def get_voter_history(
    voter_id: str,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    """The edit trail for one voter, newest first."""
    row = _find_voter(session, voter_id)
    if row is None:
        raise HTTPException(404, "Voter not found")

    entries = session.execute(
        select(AuditLogRow)
        .where(AuditLogRow.voter_id == voter_id)
        .order_by(desc(AuditLogRow.timestamp), desc(AuditLogRow.id))
        .limit(limit)
    ).scalars().all()

    return {
        "voter_id": voter_id,
        "total": len(entries),
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "field_name": e.field_name,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "user": e.user_id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ],
    }


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
    # No per-field audit on creation: every field is "new", and listing all
    # twelve says nothing a single "created" entry does not.
    _apply_fields(row, payload.model_dump(), user.username)
    session.add(row)
    record_audit(
        session, row.id, action="created", user=user.username,
        new_value=f"{row.epic} {row.name}".strip(),
    )
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
    row = _find_voter(session, voter_id)
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

    _apply_fields(row, data, user.username, session)
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
    row = _find_voter(session, voter_id)
    if row is not None:
        logger.info("User %r deleted voter %s (%s)", user.username, voter_id, row.epic)
        # Logged before the delete, while the row can still be described.
        # The entry outlives the voter deliberately -- "who removed this
        # elector" is the question an audit trail exists to answer.
        record_audit(
            session, row.id, action="deleted", user=user.username,
            old_value=f"{row.epic} {row.name}".strip(),
            file_id=row.source_file_id, page_id=row.source_page_id,
        )
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
        record_audit(
            session, row.id, action="deleted", user=user.username,
            old_value=f"{row.epic} {row.name}".strip(),
            file_id=row.source_file_id, page_id=row.source_page_id,
        )
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


_REVISION_RE = re.compile(r"revision\s*(\d+)", re.IGNORECASE)


def revision_of(file_name: str | None) -> int:
    """Which revision of a roll a file holds, read from its name.

    The name is the only place this exists. The cover sheet gives a
    `revision_year` -- 2026 for every document in the corpus -- and a
    `revision_type` that is the Tamil for "year of revision"; neither
    separates a first revision from a second. The publisher's file name does,
    consistently. An unrecognised name yields 0 so it loses to every real
    revision rather than silently outranking one.
    """
    match = _REVISION_RE.search(file_name or "")
    return int(match.group(1)) if match else 0


@dataclass(frozen=True)
class PromotionCandidate:
    """One record's claim to be *the* row for an elector."""

    record_id: str
    epic: str
    revision: int
    is_deleted: bool
    is_supplement: bool
    page_number: int
    index: int
    is_clean: bool = True
    deletion_reason: str = ""


def _latest_revision_per_epic(
    candidates: Sequence[PromotionCandidate],
) -> dict[str, int]:
    latest: dict[str, int] = {}
    for c in candidates:
        if c.revision > latest.get(c.epic, -1):
            latest[c.epic] = c.revision
    return latest


def resolve_deletions(
    candidates: Iterable[PromotionCandidate],
) -> dict[str, str]:
    """Which electors are struck off. Returns epic -> deletion reason.

    Separate from `resolve_duplicate_epics` because a deletion is a *status*,
    and the record carrying it is often the worst copy of the elector's
    details. A struck-through cell reads badly -- the stamp costs the age line
    a digit -- so it routinely fails validation, and 187 such records on the
    Penn corpus were dropped by `only_clean` before ever being considered.
    That left 160 electors the roll had struck off sitting active in the
    curated table. Deciding the deletion here lets the clean main-roll entry
    keep supplying the name and age while the deletion still lands.

    Only the highest revision present for an elector gets a vote, so a
    Revision 2 that lists them as active overrides a Revision 1 deletion --
    that is a reinstatement, and it has to be representable.

    Presence in the mapping is the deletion; the reason may be empty.
    """
    candidates = list(candidates)
    latest = _latest_revision_per_epic(candidates)
    deletions: dict[str, str] = {}
    for c in candidates:
        if not c.is_deleted or c.revision != latest[c.epic]:
            continue
        # First stated reason wins; a later blank must not erase it.
        if not deletions.get(c.epic):
            deletions[c.epic] = c.deletion_reason
    return deletions


def resolve_duplicate_epics(
    candidates: Iterable[PromotionCandidate],
) -> dict[str, str]:
    """Pick one record per EPIC. Returns epic -> winning record id.

    An EPIC repeating across a batch is normal, not a fault: a roll reprints
    an elector in its supplement to strike them off, and the corpus holds two
    revisions of some parts. Keeping whichever arrived first -- which is what
    scanning in page order does -- means the main roll's active entry always
    beats the supplement's deletion, because the supplement is further into
    the document. That silently dropped 184 deletions on this corpus.

    Precedence, highest first: later revision, then a record that passes
    validation, then a deletion, then a supplement, then the earlier entry.
    See the module test for why each rung is where it is.

    Cleanliness sits below the revision but above everything else on purpose.
    A later revision is the current roll whatever its OCR quality, but within
    one revision the readable copy of an elector should supply their details
    -- the struck-off reprint is the one most likely to be garbled. The
    deletion it carries is not lost by ranking it here; `resolve_deletions`
    applies that independently of who wins the fields.
    """
    best: dict[str, tuple[tuple, str]] = {}
    for c in candidates:
        # Negated position so that, among otherwise equal claims, `max` picks
        # the earliest rather than the latest -- two misreads of one EPIC on a
        # page are indistinguishable, and keeping the first is the behaviour
        # that was here before precedence existed.
        key = (c.revision, c.is_clean, c.is_deleted, c.is_supplement,
               -c.page_number, -c.index)
        current = best.get(c.epic)
        if current is None or key > current[0]:
            best[c.epic] = (key, c.record_id)
    return {epic: record_id for epic, (_key, record_id) in best.items()}


def execute_promotion(
    session: Session,
    rows: list[RecordRow],
    on_conflict: str = "overwrite",
    only_clean: bool = False,
    actor: str = "system",
) -> PromotionResult:
    """Core logic to promote RecordRows to VoterRows."""
    if not rows:
        return PromotionResult()

    # Page/file context, fetched once rather than per record.
    file_names = dict(session.execute(select(FileRow.id, FileRow.name)).all())
    pages = {
        p.id: p for p in
        session.execute(
            select(PageRow).where(PageRow.id.in_({r.page_id for r in rows}))
        ).scalars().all()
    }
    stations = {
        s.file_id: s for s in
        session.execute(
            select(PollingStationRow).where(
                PollingStationRow.file_id.in_({r.file_id for r in rows})
            )
        ).scalars().all()
    }
    photos_by_record = {
        p.record_id: p for p in
        session.execute(
            select(PhotoRow).where(
                PhotoRow.record_id.in_({r.id for r in rows}),
                PhotoRow.photo_type == "voter_crop",
            )
        ).scalars().all()
    }

    # Pre-parse rows and pre-fetch all existing VoterRow instances by EPIC in batch
    row_records = [(row, row_to_record(row)) for row in rows]

    if only_clean:
        row_records = [
            (row, record) for row, record in row_records
            if row.error_count == 0 or _field_value(record, "is_deleted") == "Yes"
        ]
        if not row_records:
            return PromotionResult()

    epic_list = list({
        normalise_epic(_field_value(rec, "epic"))
        for _, rec in row_records
    } - {""})

    existing_voters_map: dict[str, VoterRow] = {}
    if epic_list:
        for i in range(0, len(epic_list), 500):
            chunk = epic_list[i : i + 500]
            v_rows = session.execute(
                select(VoterRow).where(VoterRow.epic.in_(chunk))
            ).scalars().all()
            for v in v_rows:
                existing_voters_map[v.epic] = v

    candidates = [
        PromotionCandidate(
            record_id=row.id,
            epic=normalise_epic(_field_value(record, "epic")),
            revision=revision_of(file_names.get(row.file_id, "")),
            is_deleted=_field_value(record, "is_deleted") == "Yes",
            is_supplement=bool(
                (page := pages.get(row.page_id))
                and page.page_type == "supplement_page"
            ),
            page_number=row.page_number or 0,
            index=row.index or 0,
            is_clean=row.error_count == 0,
            deletion_reason=_field_value(record, "deletion_reason"),
        )
        for row, record in row_records
        if normalise_epic(_field_value(record, "epic"))
    ]
    winning_record_ids = resolve_duplicate_epics(candidates)
    deleted_epics = resolve_deletions(candidates)

    result = PromotionResult()
    seen_in_batch: dict[str, str] = {}

    for row, record in row_records:
        epic = normalise_epic(_field_value(record, "epic"))
        name = _field_value(record, "name")

        if not epic:
            result.conflicts.append(PromotionConflict(
                record_id=row.id, reason="No EPIC number on this record",
                incoming_name=name))
            result.skipped += 1
            continue

        winner_id = winning_record_ids.get(epic)
        if winner_id is not None and winner_id != row.id:
            result.conflicts.append(PromotionConflict(
                record_id=row.id, epic=epic,
                reason="Superseded by another record for this elector",
                incoming_name=name))
            result.skipped += 1
            continue

        if epic in seen_in_batch:
            result.conflicts.append(PromotionConflict(
                record_id=row.id, epic=epic,
                reason="Duplicate EPIC within this same batch",
                incoming_name=name))
            result.skipped += 1
            continue

        existing = existing_voters_map.get(epic)

        if existing is not None and on_conflict == "skip":
            result.conflicts.append(PromotionConflict(
                record_id=row.id, epic=epic,
                reason="EPIC already exists in the voter database",
                existing_voter_id=existing.id, existing_name=existing.name,
                incoming_name=name))
            result.skipped += 1
            continue

        page = pages.get(row.page_id)
        station = stations.get(row.file_id)
        header = ((page.payload or {}).get("header_text", "") if page else "") or ""
        age_raw = _field_value(record, "age")
        serial_raw = _field_value(record, "serial")

        is_supplement = bool(page and page.page_type == "supplement_page")

        constituency = header[:255]
        if station and station.ac_name:
            constituency = (
                f"{station.ac_number}-{station.ac_name}"
                if station.ac_number
                else station.ac_name
            )[:255]

        values = {
            "epic": epic,
            "name": name,
            "serial": int(serial_raw) if serial_raw.isdigit() else None,
            "relation_type": _field_value(record, "relation_type"),
            "relation_name": _field_value(record, "relation_name"),
            "house_number": _field_value(record, "house_number"),
            "age": int(age_raw) if age_raw.isdigit() else None,
            "gender": _field_value(record, "gender"),
            "part_number": station.part_number if station else "",
            "constituency": constituency,
            "polling_station_id": station.id if station else None,
            "is_supplement": is_supplement,
            "is_deleted": epic in deleted_epics,
            "section_name": (
                _field_value(record, "section_name")
                or (station.address if station else None)
            ),
            "deletion_reason": (
                deleted_epics.get(epic)
                or _field_value(record, "deletion_reason")
            ),
            "source_record_id": row.id,
            "source_page_id": row.page_id,
            "source_file_id": row.file_id,
            "source_file_name": file_names.get(row.file_id, ""),
            "page_number": row.page_number,
            "page_id": row.page_id,
        }

        if existing is not None:
            _apply_fields(
                existing, values, actor, session, audit_action="promoted"
            )
            result.updated += 1
            result.voter_ids.append(existing.id)
        else:
            voter = VoterRow(id=uuid.uuid4().hex[:12], created_by=actor)
            _apply_fields(voter, values, actor)
            session.add(voter)
            record_audit(
                session, voter.id, action="promoted", user=actor,
                new_value=f"{voter.epic} {voter.name}".strip(),
                file_id=row.file_id, page_id=row.page_id,
            )
            result.created += 1
            result.voter_ids.append(voter.id)
            existing_voters_map[epic] = voter

        photo = photos_by_record.get(row.id)
        if photo is not None:
            photo.voter_id = existing.id if existing is not None else result.voter_ids[-1]

        seen_in_batch[epic] = row.id

    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, f"Promotion failed on a uniqueness conflict: {exc}") from exc

    logger.info(
        "Actor %r promoted %d created / %d updated / %d skipped",
        actor, result.created, result.updated, result.skipped,
    )
    return result


def auto_promote_file(session: Session, file_id: str, actor: str = "system") -> PromotionResult:
    """Auto-promote records for a single file into the voters table."""
    rows = session.execute(
        select(RecordRow).where(RecordRow.file_id == file_id).order_by(RecordRow.page_number, RecordRow.index)
    ).scalars().all()
    if not rows:
        return PromotionResult()
    return execute_promotion(session, rows, on_conflict="overwrite", only_clean=False, actor=actor)


@router.post("/promote", response_model=PromotionResult)
def promote_records(
    payload: PromotionRequest,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> PromotionResult:
    """Copy reviewed OCR records into the curated table."""
    stmt = select(RecordRow)
    if payload.record_ids:
        stmt = stmt.where(RecordRow.id.in_(payload.record_ids))
    elif payload.page_id:
        stmt = stmt.where(RecordRow.page_id == payload.page_id)
    elif payload.file_id:
        stmt = stmt.where(RecordRow.file_id == payload.file_id)
    elif payload.all_documents:
        pass
    else:
        raise HTTPException(400, "Provide record_ids, page_id, file_id, or all_documents")

    rows = session.execute(stmt.order_by(RecordRow.page_number, RecordRow.index)).scalars().all()
    if not rows:
        raise HTTPException(404, "No matching records to promote")

    return execute_promotion(
        session,
        rows,
        on_conflict=payload.on_conflict,
        only_clean=payload.only_clean,
        actor=user.username,
    )


@router.post("/promote-all", response_model=PromotionResult)
def promote_all_records(
    on_conflict: str = Query("overwrite", pattern="^(skip|overwrite)$"),
    only_clean: bool = Query(False),
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> PromotionResult:
    """Promote every OCR record in the database to the curated voter table."""
    rows = session.execute(
        select(RecordRow).order_by(RecordRow.page_number, RecordRow.index)
    ).scalars().all()
    if not rows:
        return PromotionResult()
    return execute_promotion(
        session,
        rows,
        on_conflict=on_conflict,
        only_clean=only_clean,
        actor=user.username,
    )


@router.post("/reset-database")
def reset_database(
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    """Truncate all data tables and clean cached files."""
    try:
        tables = [
            "audit_logs", "ocr_blocks", "photos", "records", "summaries",
            "polling_stations", "pages", "files", "voters", "jobs"
        ]
        if session.bind.dialect.name == "sqlite":
            for table in tables:
                session.execute(text(f"DELETE FROM {table};"))
        else:
            session.execute(
                text("TRUNCATE TABLE voters, records, pages, files, polling_stations, summaries, photos, ocr_blocks, audit_logs, jobs CASCADE;")
            )
        session.commit()

        for sub in ["pages", "photos", "uploads"]:
            p = settings.data_dir / sub
            if p.exists():
                for item in p.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        try:
                            item.unlink(missing_ok=True)
                        except Exception:
                            pass
        logger.info("User %r reset the database and cleared caches", user.username)
        return {"status": "ok", "message": "All database records and file caches have been completely deleted."}
    except Exception as e:
        session.rollback()
        logger.error("Failed to reset database: %s", e)
        raise HTTPException(500, f"Database reset failed: {e}") from e

