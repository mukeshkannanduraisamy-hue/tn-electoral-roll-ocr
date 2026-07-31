"""Data quality: which records should not be believed, and why.

The OCR pipeline stores its own uncertainty — per-record `min_confidence`, per
-field block confidences, error and warning counts — and the roll prints its own
declared totals in `polling_stations`. Neither is currently surfaced as a
question anyone can ask. These tools make both askable.

Every flagged row says *why* it was flagged. A list of suspect records with no
stated reason is an accusation, not a finding.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Integer, distinct, func, select
from sqlalchemy.orm import Session

from ....db import PollingStationRow, RecordRow, VoterRow
from ..registry import ToolError, register

#: Matches `infographic.MIN_PLAUSIBLE_AGE`. An elector below this is a mis-read.
MIN_PLAUSIBLE_AGE = 18
#: Tamil Nadu EPIC numbers are three letters then seven digits.
EPIC_PATTERN = "^[A-Z]{3}[0-9]{7}$"
_EPIC_RE = re.compile(EPIC_PATTERN)


class OcrQualityArgs(BaseModel):
    scope: Literal["file", "page", "part", "all"] = "all"
    id: Optional[str] = Field(None, description="File id, page id or part number")


@register(
    name="ocr_quality",
    description=(
        "OCR confidence and review state for a file, page, part or the whole "
        "corpus: mean and minimum confidence, error and warning counts, how "
        "many records were edited or reviewed."
    ),
    args_model=OcrQualityArgs,
    label="Measuring OCR quality",
)
def ocr_quality(session: Session, args: OcrQualityArgs) -> Dict[str, Any]:
    if args.scope != "all" and not args.id:
        raise ToolError(f"scope={args.scope!r} needs an id.")

    stmt = select(
        func.count(),
        func.avg(RecordRow.mean_confidence),
        func.min(RecordRow.min_confidence),
        func.sum(RecordRow.error_count),
        func.sum(RecordRow.warning_count),
        func.sum(func.cast(RecordRow.edited, Integer)),
        func.sum(func.cast(RecordRow.reviewed, Integer)),
    ).select_from(RecordRow)

    if args.scope == "file":
        stmt = stmt.where(RecordRow.file_id == args.id)
    elif args.scope == "page":
        stmt = stmt.where(RecordRow.page_id == args.id)
    elif args.scope == "part":
        # Records carry no part number; the voters promoted from them do.
        pages = select(distinct(VoterRow.page_id)).where(VoterRow.part_number == args.id)
        stmt = stmt.where(RecordRow.page_id.in_(pages))

    count, mean_c, min_c, errors, warnings, edited, reviewed = session.execute(
        stmt
    ).one()

    population = count
    if args.scope == "part":
        population = session.execute(
            select(func.count()).select_from(VoterRow).where(VoterRow.part_number == args.id)
        ).scalar_one()

    return {
        "scope": args.scope,
        "id": args.id,
        "records": count,
        "population": population,
        "mean_confidence": round(float(mean_c), 3) if mean_c is not None else None,
        "min_confidence": round(float(min_c), 3) if min_c is not None else None,
        "error_count": int(errors or 0),
        "warning_count": int(warnings or 0),
        "edited": int(edited or 0),
        "reviewed": int(reviewed or 0),
    }


class LowConfidenceArgs(BaseModel):
    file_id: Optional[str] = None
    threshold: float = Field(0.75, ge=0.0, le=1.0)
    limit: int = Field(20, ge=1, le=50)


@register(
    name="low_confidence_records",
    description=(
        "OCR records whose minimum field confidence falls below a threshold, "
        "worst first. A review queue: which records to check by hand."
    ),
    args_model=LowConfidenceArgs,
    label="Ranking low-confidence records",
)
def low_confidence_records(session: Session, args: LowConfidenceArgs) -> Dict[str, Any]:
    stmt = select(RecordRow).where(RecordRow.min_confidence < args.threshold)
    if args.file_id:
        stmt = stmt.where(RecordRow.file_id == args.file_id)
    rows = (
        session.execute(stmt.order_by(RecordRow.min_confidence).limit(args.limit))
        .scalars()
        .all()
    )
    return {
        "threshold": args.threshold,
        "rows": [
            {
                "record_id": r.id,
                "file_id": r.file_id,
                "page_id": r.page_id,
                "page_number": r.page_number,
                "min_confidence": round(float(r.min_confidence or 0.0), 3),
                "mean_confidence": round(float(r.mean_confidence or 0.0), 3),
                "error_count": r.error_count,
                "reviewed": bool(r.reviewed),
            }
            for r in rows
        ],
        "returned": len(rows),
    }


class AnomalyArgs(BaseModel):
    kind: Literal[
        "duplicate_epic",
        "implausible_age",
        "missing_field",
        "epic_format",
        "count_mismatch",
    ]
    part_number: Optional[str] = None
    limit: int = Field(25, ge=1, le=50)


def _citable(voter: VoterRow, reason: str) -> Dict[str, Any]:
    return {
        "id": voter.id,
        "epic": voter.epic,
        "name": voter.name,
        "age": voter.age,
        "gender": voter.gender,
        "part_number": voter.part_number,
        "reason": reason,
    }


@register(
    name="find_anomalies",
    description=(
        "Records that look wrong. kind=duplicate_epic finds repeated EPIC "
        "numbers; implausible_age finds electors under 18; missing_field finds "
        "blank name, gender or house number; epic_format finds EPICs that do "
        "not match three letters and seven digits; count_mismatch compares each "
        "polling station's declared elector total against how many were "
        "actually extracted."
    ),
    args_model=AnomalyArgs,
    label="Scanning for anomalies",
)
def find_anomalies(session: Session, args: AnomalyArgs) -> Dict[str, Any]:
    def scoped(stmt):
        return stmt.where(VoterRow.part_number == args.part_number) if args.part_number else stmt

    rows: List[Dict[str, Any]] = []

    if args.kind == "implausible_age":
        found = session.execute(
            scoped(
                select(VoterRow).where(
                    VoterRow.age.is_not(None), VoterRow.age < MIN_PLAUSIBLE_AGE
                )
            ).order_by(VoterRow.age).limit(args.limit)
        ).scalars().all()
        rows = [
            _citable(v, f"Age {v.age} is below the minimum elector age of {MIN_PLAUSIBLE_AGE}.")
            for v in found
        ]

    elif args.kind == "missing_field":
        found = session.execute(
            scoped(
                select(VoterRow).where(
                    (VoterRow.name == "")
                    | (VoterRow.gender == "")
                    | (VoterRow.house_number == "")
                )
            ).limit(args.limit)
        ).scalars().all()
        for v in found:
            blank = [
                f for f in ("name", "gender", "house_number") if not getattr(v, f)
            ]
            rows = rows + [_citable(v, f"Blank: {', '.join(blank)}.")]

    elif args.kind == "epic_format":
        # SQLite has no built-in REGEXP, so the pattern is applied in Python
        # over a bounded scan rather than pushed into the query.
        found = session.execute(scoped(select(VoterRow)).limit(500)).scalars().all()
        rows = [
            _citable(v, f"EPIC {v.epic!r} does not match three letters then seven digits.")
            for v in found
            if not _EPIC_RE.match((v.epic or "").upper())
        ][: args.limit]

    elif args.kind == "duplicate_epic":
        # The voters table enforces uniqueness, so duplicates can only survive
        # upstream in the OCR records. That is where to look.
        dupes = session.execute(
            select(RecordRow.search_text, func.count())
            .where(RecordRow.search_text != "")
            .group_by(RecordRow.search_text)
            .having(func.count() > 1)
            .limit(args.limit)
        ).all()
        rows = [
            {"search_text": text[:120], "occurrences": n,
             "reason": "The same extracted text appears on more than one record."}
            for text, n in dupes
        ]

    else:  # count_mismatch
        stations = session.execute(
            select(PollingStationRow).limit(args.limit)
        ).scalars().all()
        for st in stations:
            extracted = session.execute(
                select(func.count())
                .select_from(VoterRow)
                .where(VoterRow.part_number == st.part_number)
            ).scalar_one()
            declared = int(st.total_electors or 0)
            if declared and extracted != declared:
                rows.append(
                    {
                        "part_number": st.part_number,
                        "station_name": st.name,
                        "declared_electors": declared,
                        "extracted_electors": extracted,
                        "difference": extracted - declared,
                        "reason": "The roll's printed total and the extracted count disagree.",
                    }
                )

    return {"kind": args.kind, "rows": rows, "returned": len(rows)}
