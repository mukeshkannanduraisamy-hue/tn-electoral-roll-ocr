"""Validation & Audit API endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..db import UserRow
from ..routers.auth import require_user
from ..services import validator_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
def get_validation_summary(
    user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    """Get the overall validation summary across all PDF electoral rolls."""
    audit = validator_service.get_cached_audit()
    return audit.get("summary", {})


@router.get("/reports")
def get_validation_reports(
    status: str | None = Query(None, description="Filter by status: PASS, PARTIAL, FAIL"),
    search: str | None = Query(None, description="Search by PDF name or part number"),
    ac: str | None = Query(None, description="Filter by Assembly Constituency number"),
    user: UserRow = Depends(require_user),
) -> list[dict[str, Any]]:
    """Get PDF-wise validation status and metrics."""
    audit = validator_service.get_cached_audit()
    reports = audit.get("reports", [])

    if ac:
        reports = [r for r in reports if r.get("ac_number") == ac]
    if status:
        stat_upper = status.strip().upper()
        reports = [r for r in reports if r.get("status") == stat_upper]
    if search:
        s_lower = search.strip().lower()
        reports = [
            r for r in reports
            if s_lower in r.get("pdf_file", "").lower() or s_lower in str(r.get("part_number", ""))
        ]

    return reports


@router.get("/mismatches")
def get_validation_mismatches(
    pdf_file: str | None = Query(None, description="Filter by specific PDF filename"),
    part_number: str | None = Query(None, description="Filter by Part number"),
    field_name: str | None = Query(None, description="Filter by Field Name"),
    q: str | None = Query(None, description="Search across mismatch differences"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    """Get paginated mismatch items with side-by-side field values and differences."""
    audit = validator_service.get_cached_audit()
    mismatches = audit.get("mismatches", [])

    if pdf_file:
        mismatches = [m for m in mismatches if m.get("pdf_file") == pdf_file]
    if part_number:
        mismatches = [m for m in mismatches if str(m.get("part_number")) == str(part_number)]
    if field_name:
        mismatches = [m for m in mismatches if m.get("field_name") == field_name]
    if q:
        q_lower = q.strip().lower()
        mismatches = [
            m for m in mismatches
            if q_lower in m.get("pdf_file", "").lower()
            or q_lower in str(m.get("serial_number", ""))
            or q_lower in m.get("pdf_value", "").lower()
            or q_lower in m.get("db_value", "").lower()
            or q_lower in m.get("difference", "").lower()
        ]

    total = len(mismatches)
    sliced = mismatches[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": sliced,
    }


@router.post("/scan")
def trigger_validation_scan(
    ac: str | None = None,
    user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    """Trigger a fresh validation scan across all PDFs in the repository."""
    logger.info("User %r triggered a validation audit scan", user.username)
    result = validator_service.run_audit_scan(filter_ac=ac)
    return {
        "status": "ok",
        "summary": result.get("summary", {}),
        "total_reports": len(result.get("reports", [])),
        "total_mismatches": result.get("total_mismatches", 0),
    }
