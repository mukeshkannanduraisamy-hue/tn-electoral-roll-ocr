"""Export endpoints: preview before download, then download."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import FileRow, PageRow, _page_from_row, get_session
from ..schemas.core import ExportRequest, Page
from ..services import export_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _collect_pages(session: Session, request: ExportRequest) -> list[Page]:
    """Load exactly the pages the request touches, in document order."""
    stmt = select(PageRow)

    if request.page_ids:
        stmt = stmt.where(PageRow.id.in_(request.page_ids))
    elif request.file_ids:
        stmt = stmt.where(PageRow.file_id.in_(request.file_ids))

    rows = (
        session.execute(stmt.order_by(PageRow.file_id, PageRow.page_number))
        .scalars()
        .all()
    )
    return [_page_from_row(session, row) for row in rows]


DEFAULT_TAMIL_COLUMNS = [
    "வரிசை எண் (S.No)",
    "அடையாள அட்டை எண் (EPIC ID)",
    "பெயர் (Name)",
    "உறவு முறை (Relation)",
    "உறவினரின் பெயர் (Relation Name)",
    "வீட்டு எண் (House No)",
    "வயது (Age)",
    "பாலினம் (Gender)",
]


@router.post("/preview")
def preview_export(
    request: ExportRequest, session: Session = Depends(get_session)
) -> dict:
    """Header and first rows of the export, so the user sees it before saving."""
    pages = _collect_pages(session, request)
    if not pages:
        return {"columns": DEFAULT_TAMIL_COLUMNS, "rows": [], "total_rows": 0}
    return export_service.preview(pages, request)


@router.post("")
def download_export(
    request: ExportRequest, session: Session = Depends(get_session)
) -> Response:
    pages = _collect_pages(session, request)
    try:
        content, filename, media_type = export_service.export(pages, request)
    except export_service.ExportError as exc:
        raise HTTPException(400, str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Lets the browser fetch layer read the filename on a blob download.
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
