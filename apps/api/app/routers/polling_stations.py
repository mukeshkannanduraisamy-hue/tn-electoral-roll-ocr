"""Polling stations: the part-level view of a roll.

One row per part, read off that part's cover sheet by
`services.roll_metadata`. The summary sheet's reconciliation travels with it,
because "is this part's data complete?" is the first thing anyone asks of a
station and the answer is only meaningful next to the station itself.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import require_user
from ..db import PhotoRow, PollingStationRow, SummaryRow, UserRow, VoterRow, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


def _photo_dict(photo: PhotoRow) -> dict[str, Any]:
    return {
        "id": photo.id,
        "photo_type": photo.photo_type,
        "file_path": photo.file_path,
        "width": photo.width,
        "height": photo.height,
    }


def _reconciliation_dict(summary: SummaryRow | None) -> dict[str, Any] | None:
    """How the extracted records compare with what the roll prints.

    `difference` is signed: positive means extraction produced more records
    than the roll says exist, which points at a page counted twice or a
    misdetected grid; negative means records are missing.
    """
    if summary is None:
        return None
    difference = (
        summary.extracted_records - summary.printed_total
        if summary.printed_total is not None
        else None
    )
    return {
        "extracted_records": summary.extracted_records,
        "printed_total": summary.printed_total,
        "difference": difference,
        "reconciled": summary.reconciled,
        "source": summary.reconciliation_source,
        "base_total": summary.base_total,
        "additions_total": summary.additions_total,
        "deletions_total": summary.deletions_total,
        "corrections": summary.corrections,
    }


def _station_dict(
    row: PollingStationRow,
    *,
    voter_count: int,
    photos: list[PhotoRow],
    summary: SummaryRow | None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "file_id": row.file_id,
        "part_number": row.part_number,
        "name": row.name or f"Polling Station Part {row.part_number}",
        "name_tam": row.name_tam,
        "building_name": row.building_name,
        "section_details": row.section_details,
        # --- constituency -------------------------------------------------
        "ac_number": row.ac_number,
        "ac_name": row.ac_name,
        "pc_number": row.pc_number,
        "pc_name": row.pc_name,
        # --- station ------------------------------------------------------
        "station_number": row.station_number,
        "station_type": row.station_type,
        "address": row.address,
        # --- location -----------------------------------------------------
        "district": row.district,
        "taluk": row.taluk,
        "pincode": row.pincode,
        # --- electors -----------------------------------------------------
        "serial_start": row.serial_start,
        "serial_end": row.serial_end,
        "total_electors": row.total_electors or voter_count,
        "male_electors": row.male_electors,
        "female_electors": row.female_electors,
        "third_gender_electors": row.third_gender_electors,
        "voter_count": voter_count,
        # --- provenance and quality ---------------------------------------
        "source_page_id": row.source_page_id,
        "details": row.payload or {},
        "reconciliation": _reconciliation_dict(summary),
        "photo_count": len(photos),
        "photos": [_photo_dict(p) for p in photos],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _voter_count(session: Session, part_number: str) -> int:
    return session.execute(
        select(func.count())
        .select_from(VoterRow)
        .where(VoterRow.part_number == part_number)
    ).scalar_one()


def _photos_for(session: Session, station_id: str) -> list[PhotoRow]:
    return list(
        session.execute(
            select(PhotoRow).where(PhotoRow.polling_station_id == station_id)
        ).scalars().all()
    )


def _summary_for(session: Session, file_id: str) -> SummaryRow | None:
    return session.execute(
        select(SummaryRow).where(SummaryRow.file_id == file_id)
    ).scalars().first()


@router.get("")
def list_polling_stations(
    search: str | None = Query(None),
    file_id: str | None = Query(None),
    part_number: str | None = Query(None),
    district: str | None = Query(None),
    reconciled: bool | None = Query(
        None, description="Filter to parts whose extraction matches the printed total"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    stmt = select(PollingStationRow)
    if search:
        s = f"%{search.lower().strip()}%"
        stmt = stmt.where(
            or_(
                func.lower(PollingStationRow.name).like(s),
                func.lower(PollingStationRow.building_name).like(s),
                func.lower(PollingStationRow.part_number).like(s),
                func.lower(PollingStationRow.ac_name).like(s),
                func.lower(PollingStationRow.district).like(s),
                func.lower(PollingStationRow.taluk).like(s),
                func.lower(PollingStationRow.pincode).like(s),
            )
        )
    if file_id:
        stmt = stmt.where(PollingStationRow.file_id == file_id)
    if part_number:
        stmt = stmt.where(PollingStationRow.part_number == part_number)
    if district:
        stmt = stmt.where(func.lower(PollingStationRow.district) == district.lower())
    if reconciled is not None:
        stmt = stmt.join(
            SummaryRow, SummaryRow.file_id == PollingStationRow.file_id
        ).where(SummaryRow.reconciled.is_(reconciled))

    total = session.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    rows = session.execute(
        stmt.order_by(PollingStationRow.part_number, PollingStationRow.id)
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    items = [
        _station_dict(
            r,
            voter_count=_voter_count(session, r.part_number),
            photos=_photos_for(session, r.id),
            summary=_summary_for(session, r.file_id),
        )
        for r in rows
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/{station_id}")
def get_polling_station(
    station_id: str,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    row = session.get(PollingStationRow, station_id)
    if row is None:
        raise HTTPException(404, "Polling station not found")

    voters = session.execute(
        select(VoterRow).where(VoterRow.part_number == row.part_number).limit(100)
    ).scalars().all()

    payload = _station_dict(
        row,
        voter_count=_voter_count(session, row.part_number),
        photos=_photos_for(session, station_id),
        summary=_summary_for(session, row.file_id),
    )
    payload["voter_samples"] = [
        {
            "id": v.id,
            "epic": v.epic,
            "name": v.name,
            "gender": v.gender,
            "age": v.age,
            "house_number": v.house_number,
        }
        for v in voters
    ]
    return payload
