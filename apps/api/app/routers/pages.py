"""Page retrieval, imagery and single-page re-OCR."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import FileRow, PageRow, get_session, load_page, save_page
from ..schemas.core import Page
from ..services import pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{page_id}", response_model=Page)
def get_page(page_id: str, session: Session = Depends(get_session)) -> Page:
    page = load_page(session, page_id)
    if page is None:
        raise HTTPException(404, "Page not found")
    return page


@router.get("/{page_id}/image")
def get_page_image(page_id: str, session: Session = Depends(get_session)):
    """Serve the rendered page image.

    This is the deskewed render, which is the coordinate space every stored
    bounding box refers to -- serving the raw PDF render instead would put
    every overlay box slightly out of alignment.
    """
    row = session.get(PageRow, page_id)
    if row is None or not row.image_path:
        raise HTTPException(404, "Page image not found")

    path = settings.pages_dir / row.image_path
    if not path.exists():
        raise HTTPException(404, "Page image file is missing")

    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/{page_id}/reocr", response_model=Page)
async def reocr_page(
    page_id: str,
    template_id: str = Query("auto"),
    lang: str | None = Query(None),
    upscale: float | None = Query(None, ge=1.0, le=6.0),
    session: Session = Depends(get_session),
) -> Page:
    """Re-run OCR on one page, optionally with different settings.

    Runs asynchronously in worker threadpool to avoid blocking Uvicorn's event loop.
    """
    row = session.get(PageRow, page_id)
    if row is None:
        raise HTTPException(404, "Page not found")

    file_row = session.get(FileRow, row.file_id)
    if file_row is None or not file_row.stored_path:
        raise HTTPException(400, "Source PDF is no longer available")

    original_upscale = settings.upscale_factor
    try:
        if upscale is not None:
            settings.upscale_factor = upscale
        # Pass by KEYWORD. `process_page`'s 6th positional parameter is
        # `save_image`, not `page_id` -- sending these positionally silently
        # bound page_id to save_image, left page_id None, and made the
        # pipeline mint a fresh page row on every re-OCR. That orphaned the
        # old row and duplicated all 30 records for the page.
        page = await run_in_threadpool(
            pipeline.process_page,
            file_row.stored_path,
            row.page_number,
            row.file_id,
            template_id=template_id,
            lang=lang,
            page_id=page_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Re-OCR failed for page %s", page_id)
        raise HTTPException(500, f"Re-OCR failed: {exc}") from exc
    finally:
        settings.upscale_factor = original_upscale

    save_page(session, page, row.file_id)
    return page
