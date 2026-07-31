"""What the roll covers, and the polling stations behind it.

`polling_station` returns the station's *declared* elector counts alongside
what was actually extracted. Those two numbers disagreeing is the single most
useful integrity signal in the corpus, and nothing else surfaces it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ....db import FileRow, PageRow, PollingStationRow, RecordRow, VoterRow
from ..registry import ToolError, register

#: `roll_overview` slices its parts and constituencies lists to keep the
#: prompt bounded; past these many distinct values the corresponding
#: `*_count` field (the true total) will exceed the length of the list, and
#: that is the caller's signal the list was cut short.
MAX_PARTS = 100
MAX_CONSTITUENCIES = 50


class RollOverviewArgs(BaseModel):
    pass


@register(
    name="roll_overview",
    description=(
        "The shape of the corpus: how many electors, files, pages and records, "
        "which parts and constituencies are covered, and which polling "
        "stations exist. Use this first when a question is about scope. The "
        f"parts list is capped at {MAX_PARTS} and constituencies at "
        f"{MAX_CONSTITUENCIES}; `part_count` and `constituency_count` give the "
        "true totals when a list is shorter than the corpus actually has."
    ),
    args_model=RollOverviewArgs,
    label="Reading roll overview",
)
def roll_overview(session: Session, _args: RollOverviewArgs) -> Dict[str, Any]:
    def count(model) -> int:
        return session.execute(select(func.count()).select_from(model)).scalar_one()

    parts = session.execute(
        select(distinct(VoterRow.part_number)).where(VoterRow.part_number != "")
    ).scalars().all()
    constituencies = session.execute(
        select(distinct(VoterRow.constituency)).where(VoterRow.constituency != "")
    ).scalars().all()

    return {
        "voters": count(VoterRow),
        "files": count(FileRow),
        "pages": count(PageRow),
        "records": count(RecordRow),
        "polling_stations": count(PollingStationRow),
        "parts": sorted(parts)[:MAX_PARTS],
        "part_count": len(parts),
        "constituencies": sorted(constituencies)[:MAX_CONSTITUENCIES],
        "constituency_count": len(constituencies),
    }


class PollingStationArgs(BaseModel):
    part_number: Optional[str] = None
    station_id: Optional[str] = None


@register(
    name="polling_station",
    description=(
        "A polling station's details and its declared elector counts, together "
        "with how many electors were actually extracted for that part. A "
        "difference between the two means the roll and the extraction disagree."
    ),
    args_model=PollingStationArgs,
    label="Reading polling station",
)
def polling_station(session: Session, args: PollingStationArgs) -> Dict[str, Any]:
    if not args.part_number and not args.station_id:
        raise ToolError("Provide part_number or station_id.")

    stmt = select(PollingStationRow)
    stmt = (
        stmt.where(PollingStationRow.id == args.station_id.strip())
        if args.station_id
        else stmt.where(PollingStationRow.part_number == (args.part_number or "").strip())
    )
    station = session.execute(stmt).scalars().first()
    if station is None:
        raise ToolError(f"No polling station for {args.station_id or args.part_number!r}.")

    extracted = session.execute(
        select(func.count())
        .select_from(VoterRow)
        .where(VoterRow.part_number == station.part_number)
    ).scalar_one()

    return {
        "station": {
            "station_id": station.id,
            "part_number": station.part_number,
            "name": station.name,
            "name_tam": station.name_tam,
            "building_name": station.building_name,
            "address": station.address,
            "district": station.district,
            "ac_number": station.ac_number,
            "ac_name": station.ac_name,
        },
        "declared": {
            "total_electors": station.total_electors,
            "male_electors": station.male_electors,
            "female_electors": station.female_electors,
            "third_gender_electors": station.third_gender_electors,
        },
        "extracted": {"total_electors": extracted},
        "difference": extracted - int(station.total_electors or 0),
    }
