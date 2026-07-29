"""Upload and manage source PDFs."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import FileRow, JobRow, PageRow, RecordRow, file_to_schema, get_session
from ..schemas.core import FileStatus, JobStatus, SourceFile
from ..services import pdf_service
from ..services.job_queue import manager

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def _cancel_jobs_for_file(session: Session, file_id: str) -> None:
    """Stop any in-flight extraction of a file that is being deleted.

    Without this the job runs to completion against a file that no longer
    exists: every page still renders and goes through OCR, then `save_page`
    drops the result because the parent row is gone. A 12-page roll spends
    several more minutes of full-core OCR producing nothing, and the pool
    stays busy so the *next* upload queues behind work that is already void.

    Cancellation is cooperative -- pages already inside `predict()` finish --
    so this bounds the waste rather than eliminating it.
    """
    live = (
        session.execute(
            select(JobRow).where(
                JobRow.status.in_([JobStatus.RUNNING.value, JobStatus.QUEUED.value])
            )
        )
        .scalars()
        .all()
    )
    for job in live:
        # `file_ids` is a JSON column; a job may batch several files and only
        # dies with the last one still standing.
        ids = job.file_ids if isinstance(job.file_ids, list) else []
        if file_id in ids:
            logger.info("Cancelling job %s: file %s deleted mid-run", job.id, file_id)
            manager.cancel(job.id)


def _is_managed_upload(stored_path: str) -> bool:
    """True when we created this file and may therefore delete it.

    Uploaded PDFs are copied into `settings.uploads_dir`; folder-imported
    PDFs are referenced where they already live. Only the former are ours
    to remove.
    """
    if not stored_path:
        return False
    try:
        resolved = Path(stored_path).resolve()
        uploads = settings.uploads_dir.resolve()
    except (OSError, ValueError):
        return False
    return resolved.is_relative_to(uploads)


@router.post("", response_model=list[SourceFile])
async def upload(
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
) -> list[SourceFile]:
    """Accept one or more PDFs, validating each before it is registered."""
    if not files:
        raise HTTPException(400, "No files provided")

    created: list[SourceFile] = []
    for upload_file in files:
        name = Path(upload_file.filename or "upload.pdf").name
        if not name.lower().endswith(".pdf"):
            raise HTTPException(400, f"{name}: only PDF files are supported")

        file_id = uuid.uuid4().hex[:12]
        stored = settings.uploads_dir / f"{file_id}.pdf"

        size = 0
        try:
            with stored.open("wb") as out:
                while chunk := await upload_file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            413,
                            f"{name}: exceeds the "
                            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                        )
                    out.write(chunk)
        except HTTPException:
            stored.unlink(missing_ok=True)
            raise
        finally:
            await upload_file.close()

        # Validate before registering so a corrupt PDF surfaces immediately
        # rather than at OCR time.
        try:
            info = pdf_service.inspect(stored)
        except pdf_service.PdfError as exc:
            stored.unlink(missing_ok=True)
            row = FileRow(
                id=file_id,
                name=name,
                size_bytes=size,
                status=FileStatus.ERROR.value,
                error=str(exc),
                stored_path="",
            )
            session.add(row)
            session.flush()
            created.append(file_to_schema(row))
            continue

        row = FileRow(
            id=file_id,
            name=name,
            size_bytes=size,
            page_count=info.page_count,
            status=FileStatus.PENDING.value,
            stored_path=str(stored),
            languages=[settings.ocr_lang],
        )
        session.add(row)
        session.flush()
        created.append(file_to_schema(row))

    return created


@router.get("", response_model=list[SourceFile])
def list_files(session: Session = Depends(get_session)) -> list[SourceFile]:
    rows = (
        session.execute(select(FileRow).order_by(FileRow.created_at.desc()))
        .scalars()
        .all()
    )
    return [file_to_schema(r) for r in rows]


# ── /import-folder MUST be declared BEFORE /{file_id} to avoid shadowing ───

@router.post("/import-folder", response_model=list[SourceFile])
def import_folder(
    payload: dict,
    session: Session = Depends(get_session),
) -> list[SourceFile]:
    """Register PDFs already on disk, without copying them.

    Uploading hundreds of files through the browser is slow and pointless
    when they are already on the same machine.  ``recursive`` walks
    subdirectories.

    Declared *before* ``/{file_id}`` so FastAPI does not mistake the literal
    string "import-folder" for a file id.

    Disabled unless ``OCR_ALLOW_FOLDER_IMPORT`` is on: reading paths chosen by
    the caller is a local-workflow convenience, not something to expose on a
    public host.
    """
    if not settings.allow_folder_import:
        raise HTTPException(
            403,
            "Folder import is disabled on this deployment. Upload the PDFs instead.",
        )

    folder = Path(str(payload.get("path", ""))).expanduser()
    recursive = bool(payload.get("recursive", True))
    if not folder.is_dir():
        raise HTTPException(400, f"Not a directory: {folder}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    paths = sorted(folder.glob(pattern))
    if not paths:
        return []

    existing = {
        r
        for r in session.execute(select(FileRow.stored_path)).scalars().all()
        if r
    }

    result_files: list[SourceFile] = []
    for path in paths:
        if str(path) in existing:
            existing_row = session.execute(
                select(FileRow).where(FileRow.stored_path == str(path))
            ).scalar_one_or_none()
            if existing_row is not None:
                result_files.append(file_to_schema(existing_row))
                continue
        file_id = uuid.uuid4().hex[:12]
        try:
            info = pdf_service.inspect(path)
            row = FileRow(
                id=file_id,
                name=path.name,
                size_bytes=path.stat().st_size,
                page_count=info.page_count,
                status=FileStatus.PENDING.value,
                stored_path=str(path),
                languages=[settings.ocr_lang],
            )
        except pdf_service.PdfError as exc:
            row = FileRow(
                id=file_id,
                name=path.name,
                size_bytes=path.stat().st_size,
                status=FileStatus.ERROR.value,
                error=str(exc),
                stored_path="",
            )
        session.add(row)
        session.flush()
        result_files.append(file_to_schema(row))

    return result_files


@router.get("/{file_id}", response_model=SourceFile)
def get_file(file_id: str, session: Session = Depends(get_session)) -> SourceFile:
    row = session.get(FileRow, file_id)
    if row is None:
        raise HTTPException(404, "File not found")
    return file_to_schema(row)


@router.get("/{file_id}/pages")
def list_pages(file_id: str, session: Session = Depends(get_session)) -> list[dict]:
    """Lightweight page index for the sidebar.

    Deliberately excludes lines and records -- the sidebar only needs
    identity, status and an issue badge count, and shipping full pages here
    would send megabytes per file.
    """
    if session.get(FileRow, file_id) is None:
        raise HTTPException(404, "File not found")

    rows = (
        session.execute(
            select(PageRow)
            .where(PageRow.file_id == file_id)
            .order_by(PageRow.page_number)
        )
        .scalars()
        .all()
    )

    summaries = []
    for row in rows:
        counts = session.execute(
            select(RecordRow.error_count, RecordRow.warning_count).where(
                RecordRow.page_id == row.id
            )
        ).all()
        summaries.append(
            {
                "id": row.id,
                "page_number": row.page_number,
                "status": row.status,
                "width": row.width,
                "height": row.height,
                "template_id": row.template_id,
                # Drives the document view: a cover sheet and a voter grid
                # hold entirely different things and cannot be rendered the
                # same way.
                "page_type": row.page_type,
                "classification_confidence": row.classification_confidence,
                "record_count": len(counts),
                "error_count": sum(c[0] for c in counts),
                "warning_count": sum(c[1] for c in counts),
                "ocr_ms": row.ocr_ms,
                "error": row.error,
            }
        )
    return summaries


@router.delete("/{file_id}", status_code=204, response_class=Response)
def delete_file(file_id: str, session: Session = Depends(get_session)) -> Response:
    row = session.get(FileRow, file_id)
    if row is None:
        return Response(status_code=204)

    # Before anything is unlinked: a job still holding this file will keep
    # rendering and OCR-ing pages it can no longer save.
    _cancel_jobs_for_file(session, file_id)

    # Remove rendered page images before the rows that point at them.
    page_rows = (
        session.execute(select(PageRow).where(PageRow.file_id == file_id))
        .scalars()
        .all()
    )
    for page_row in page_rows:
        if page_row.image_path:
            (settings.pages_dir / page_row.image_path).unlink(missing_ok=True)

    # Only delete PDFs we own.
    #
    # `import-folder` registers files *in place*, so `stored_path` points at
    # the user's original document rather than a copy in our uploads
    # directory. Unlinking unconditionally would destroy the source corpus
    # -- removing a file from the workspace must never delete the user's
    # data. Anything outside `uploads_dir` is only ever dereferenced.
    if row.stored_path and _is_managed_upload(row.stored_path):
        Path(row.stored_path).unlink(missing_ok=True)

    session.query(RecordRow).filter(RecordRow.file_id == file_id).delete(
        synchronize_session=False
    )
    session.query(PageRow).filter(PageRow.file_id == file_id).delete(
        synchronize_session=False
    )
    session.delete(row)
    return Response(status_code=204)
