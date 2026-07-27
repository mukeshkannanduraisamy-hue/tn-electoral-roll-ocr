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


@router.post("/preview")
def preview_export(
    request: ExportRequest, session: Session = Depends(get_session)
) -> dict:
    """Header and first rows of the export, so the user sees it before saving."""
    pages = _collect_pages(session, request)
    if not pages:
        raise HTTPException(404, "No pages match the selection")
    return export_service.preview(pages, request)


@router.post("")
def download_export(
    request: ExportRequest, session: Session = Depends(get_session)
) -> Response:
    pages = _collect_pages(session, request)
    if not pages:
        raise HTTPException(404, "No pages match the selection")

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
