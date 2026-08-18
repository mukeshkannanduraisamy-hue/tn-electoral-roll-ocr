"""Images cropped out of roll pages: station imagery and voter photographs."""

from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import settings
from ..db import PhotoRow, UserRow, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


def _photo_dict(photo: PhotoRow) -> dict[str, Any]:
    return {
        "id": photo.id,
        "photo_type": photo.photo_type,
        "file_id": photo.file_id,
        "page_id": photo.page_id,
        "record_id": photo.record_id,
        "voter_id": photo.voter_id,
        "polling_station_id": photo.polling_station_id,
        "width": photo.width,
        "height": photo.height,
        "url": f"/api/photos/{photo.id}/image",
        "created_at": photo.created_at.isoformat() if photo.created_at else None,
    }


@router.get("")
def list_photos(
    voter_id: str | None = Query(None),
    polling_station_id: str | None = Query(None),
    file_id: str | None = Query(None),
    page_id: str | None = Query(None),
    photo_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> dict[str, Any]:
    stmt = select(PhotoRow)
    if voter_id:
        stmt = stmt.where(PhotoRow.voter_id == voter_id)
    if polling_station_id:
        stmt = stmt.where(PhotoRow.polling_station_id == polling_station_id)
    if file_id:
        stmt = stmt.where(PhotoRow.file_id == file_id)
    if page_id:
        stmt = stmt.where(PhotoRow.page_id == page_id)
    if photo_type:
        stmt = stmt.where(PhotoRow.photo_type == photo_type)

    rows = session.execute(
        stmt.order_by(PhotoRow.photo_type, PhotoRow.id).limit(limit)
    ).scalars().all()
    return {"items": [_photo_dict(p) for p in rows], "total": len(rows)}


@router.get("/{photo_id}/image")
def get_photo_image(
    photo_id: str,
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> Response:
    row = session.get(PhotoRow, photo_id)
    if row is None:
        raise HTTPException(404, "Photo not found")

    if row.image_data:
        try:
            raw = base64.b64decode(row.image_data)
            return Response(content=raw, media_type="image/png")
        except Exception:
            pass

    path = (settings.photos_dir / row.file_path).resolve()
    try:
        path.relative_to(settings.photos_dir.resolve())
    except ValueError:
        logger.warning("Photo %s points outside the photos directory", photo_id)
        raise HTTPException(404, "Photo not found") from None

    if not path.is_file():
        raise HTTPException(404, "Photo file is missing from disk")

    return FileResponse(path, media_type="image/png")
