"""Row-level lookup over the curated voter table.

These are the tools that let the assistant answer "who", not just "how many".
Every row carries `id` and `epic` so `guards.collect_citations` can bind a
citation to it; a record the model mentions that these tools did not return is
stripped before the reply leaves the server.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....db import OCRBlockRow, VoterRow
from ..registry import ToolError, register

#: A model that asks for 500 rows is trying to read the table rather than
#: answer a question, and the prompt cannot hold them anyway.
MAX_ROWS = 50


class SearchVotersArgs(BaseModel):
    search: Optional[str] = Field(None, description="Free text over name, EPIC, house, part")
    name: Optional[str] = None
    epic: Optional[str] = None
    part_number: Optional[str] = None
    constituency: Optional[str] = None
    gender: Optional[str] = Field(None, description="Male | Female | Third Gender")
    house_number: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    verified: Optional[bool] = None
    is_supplement: Optional[bool] = None
    is_deleted: Optional[bool] = Field(None, description="True: only struck-off electors; False: only active")
    source_file_id: Optional[str] = None
    limit: int = Field(20, ge=1, le=MAX_ROWS)
    offset: int = Field(0, ge=0)


def _row(voter: VoterRow) -> Dict[str, Any]:
    return {
        "id": voter.id,
        "epic": voter.epic,
        "name": voter.name,
        "age": voter.age,
        "gender": voter.gender,
        "relation_type": voter.relation_type,
        "relation_name": voter.relation_name,
        "house_number": voter.house_number,
        "part_number": voter.part_number,
        "constituency": voter.constituency,
        "verified": bool(voter.verified),
        "is_supplement": bool(voter.is_supplement),
        "is_deleted": bool(voter.is_deleted),
        "deletion_reason": voter.deletion_reason,
    }


def _apply(stmt, args: SearchVotersArgs):
    if args.search:
        stmt = stmt.where(VoterRow.search_text.like(f"%{args.search.strip().lower()}%"))
    if args.name:
        stmt = stmt.where(VoterRow.name.like(f"%{args.name.strip()}%"))
    if args.epic:
        stmt = stmt.where(VoterRow.epic == args.epic.strip().upper())
    if args.part_number:
        stmt = stmt.where(VoterRow.part_number == args.part_number.strip())
    if args.constituency:
        stmt = stmt.where(VoterRow.constituency == args.constituency.strip())
    if args.gender:
        stmt = stmt.where(VoterRow.gender == args.gender.strip())
    if args.house_number:
        stmt = stmt.where(VoterRow.house_number.like(f"%{args.house_number.strip()}%"))
    if args.min_age is not None:
        stmt = stmt.where(VoterRow.age >= args.min_age)
    if args.max_age is not None:
        stmt = stmt.where(VoterRow.age <= args.max_age)
    if args.verified is not None:
        stmt = stmt.where(VoterRow.verified.is_(args.verified))
    if args.is_supplement is not None:
        stmt = stmt.where(VoterRow.is_supplement.is_(args.is_supplement))
    if args.is_deleted is not None:
        stmt = stmt.where(VoterRow.is_deleted.is_(args.is_deleted))
    if args.source_file_id:
        stmt = stmt.where(VoterRow.source_file_id == args.source_file_id.strip())
    return stmt


@register(
    name="search_voters",
    description=(
        "Find electors on the curated roll by name, EPIC, part, constituency, "
        "gender, age range, house number, verification state, deletion status "
        "(is_deleted) or source file. "
        "Returns matching rows and the total number matched."
    ),
    args_model=SearchVotersArgs,
    label="Searching electors",
)
def search_voters(session: Session, args: SearchVotersArgs) -> Dict[str, Any]:
    total = session.execute(
        _apply(select(func.count()).select_from(VoterRow), args)
    ).scalar_one()

    stmt = _apply(select(VoterRow), args).order_by(
        VoterRow.part_number, VoterRow.serial, VoterRow.name
    )
    rows = session.execute(stmt.limit(args.limit).offset(args.offset)).scalars().all()

    return {
        "rows": [_row(v) for v in rows],
        "returned": len(rows),
        "total": total,
        "truncated": total > args.offset + len(rows),
    }


class GetVoterArgs(BaseModel):
    voter_id: Optional[str] = None
    epic: Optional[str] = None


def _find_one(session: Session, voter_id: Optional[str], epic: Optional[str]) -> VoterRow:
    if not voter_id and not epic:
        raise ToolError("Provide voter_id or epic.")
    stmt = select(VoterRow)
    stmt = (
        stmt.where(VoterRow.id == voter_id.strip())
        if voter_id
        else stmt.where(VoterRow.epic == (epic or "").strip().upper())
    )
    voter = session.execute(stmt).scalar_one_or_none()
    if voter is None:
        raise ToolError(f"No elector found for {voter_id or epic!r}.")
    return voter


@register(
    name="get_voter",
    description=(
        "Fetch one elector in full by voter_id or EPIC, including the OCR "
        "field confidences and the page the record was read from."
    ),
    args_model=GetVoterArgs,
    label="Opening elector record",
)
def get_voter(session: Session, args: GetVoterArgs) -> Dict[str, Any]:
    voter = _find_one(session, args.voter_id, args.epic)

    blocks: List[Dict[str, Any]] = []
    if voter.source_record_id:
        found = (
            session.execute(
                select(OCRBlockRow).where(OCRBlockRow.record_id == voter.source_record_id)
            )
            .scalars()
            .all()
        )
        blocks = [
            {
                "field_name": b.field_name,
                "raw_text": b.raw_text,
                "corrected_text": b.corrected_text,
                "confidence": round(float(b.confidence or 0.0), 3),
                "bbox": [b.bbox_x0, b.bbox_y0, b.bbox_x1, b.bbox_y1],
            }
            for b in found
        ]

    return {
        "voter": {**_row(voter), "serial": voter.serial, "notes": voter.notes},
        "provenance": {
            "source_file_id": voter.source_file_id,
            "source_file_name": voter.source_file_name,
            "page_id": voter.page_id,
            "page_number": voter.page_number,
            "source_record_id": voter.source_record_id,
            "polling_station_id": voter.polling_station_id,
        },
        "ocr_fields": blocks,
    }


class HouseholdArgs(BaseModel):
    voter_id: Optional[str] = None
    epic: Optional[str] = None


@register(
    name="household_of",
    description=(
        "The household an elector belongs to and the families resolved within "
        "it, with the evidence behind each link. Same result as the Family tab."
    ),
    args_model=HouseholdArgs,
    label="Resolving household",
)
def household_of(session: Session, args: HouseholdArgs) -> Dict[str, Any]:
    from ....routers.voters import resolve_household

    voter = _find_one(session, args.voter_id, args.epic)
    return resolve_household(session, voter.id)
