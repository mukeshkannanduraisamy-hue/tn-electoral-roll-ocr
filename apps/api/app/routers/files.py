"""Upload and manage source PDFs."""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import FileRow, JobRow, PageRow, RecordRow, file_to_schema, get_session
from ..schemas.core import (
    FileStatus,
    FolderPdfItem,
    FolderScanRequest,
    FolderScanResponse,
    Job,
    JobStatus,
    SourceFile,
)
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
            file_data=None,
            languages=[settings.ocr_lang],
        )
        session.add(row)
        session.flush()
        created.append(file_to_schema(row))

    return created


@router.get("", response_model=list[SourceFile])
def list_files(session: Session = Depends(get_session)) -> list[SourceFile]:
    try:
        rows = (
            session.execute(select(FileRow).order_by(FileRow.created_at.desc()))
            .scalars()
            .all()
        )
        if not rows:
            return []

        # Bulk query record counts per file
        rec_counts = dict(
            session.execute(
                select(RecordRow.file_id, func.count(RecordRow.id)).group_by(RecordRow.file_id)
            ).all()
        )

        # Bulk query total OCR duration in ms per file
        ocr_durations = dict(
            session.execute(
                select(PageRow.file_id, func.sum(PageRow.ocr_ms)).group_by(PageRow.file_id)
            ).all()
        )

        result: list[SourceFile] = []
        for r in rows:
            schema = file_to_schema(r)
            schema.records_count = rec_counts.get(r.id, 0)
            total_ocr_ms = ocr_durations.get(r.id, 0) or 0
            if total_ocr_ms > 0:
                schema.ocr_duration_sec = round(total_ocr_ms / 1000.0, 1)
            result.append(schema)
        return result
    except Exception as exc:
        logger.error("Failed to list files: %s", exc, exc_info=True)
        raise HTTPException(500, f"Failed to fetch files from database: {exc}")


# ── Special named routes MUST be declared BEFORE /{file_id} to avoid shadowing ───

@router.post("/scan-folder", response_model=FolderScanResponse)
def scan_folder(
    payload: FolderScanRequest,
    session: Session = Depends(get_session),
) -> FolderScanResponse:
    """Scan a local directory for PDFs, returning metadata and current DB registration/processing status."""
    folder_raw = payload.path.strip()
    if not folder_raw:
        raise HTTPException(400, "Folder path cannot be empty")

    folder = Path(folder_raw).expanduser().resolve()
    if not folder.is_dir():
        raise HTTPException(400, f"Directory not found: {folder}")

    pattern = "**/*.pdf" if payload.recursive else "*.pdf"
    try:
        paths = sorted(folder.glob(pattern))
    except Exception as e:
        raise HTTPException(400, f"Failed to scan folder: {e}")

    # Query registered files from DB
    db_files = session.execute(select(FileRow)).scalars().all()
    files_by_path = {f.stored_path: f for f in db_files if f.stored_path}
    files_by_name = {f.name: f for f in db_files if f.name}

    # Aggregate records and ocr_ms
    rec_counts = dict(
        session.execute(
            select(RecordRow.file_id, func.count(RecordRow.id)).group_by(RecordRow.file_id)
        ).all()
    )
    ocr_durations = dict(
        session.execute(
            select(PageRow.file_id, func.sum(PageRow.ocr_ms)).group_by(PageRow.file_id)
        ).all()
    )

    items: list[FolderPdfItem] = []
    completed_cnt = 0
    pending_cnt = 0
    processing_cnt = 0
    error_cnt = 0
    unregistered_cnt = 0
    total_size = 0
    total_pages = 0

    for p in paths:
        str_path = str(p)
        size = p.stat().st_size if p.exists() else 0
        total_size += size

        db_file = files_by_path.get(str_path) or files_by_name.get(p.name)

        if db_file:
            is_reg = True
            fid = db_file.id
            stat = db_file.status
            pdone = db_file.pages_done
            pg_count = db_file.page_count
            rcount = rec_counts.get(fid, 0)
            ocr_ms = ocr_durations.get(fid, 0) or 0
            ocr_sec = round(ocr_ms / 1000.0, 1) if ocr_ms > 0 else None
            err = db_file.error
            c_at = db_file.created_at

            if stat == "completed":
                completed_cnt += 1
            elif stat == "processing":
                processing_cnt += 1
            elif stat == "error":
                error_cnt += 1
            else:
                pending_cnt += 1
        else:
            is_reg = False
            fid = None
            stat = "unregistered"
            pdone = 0
            rcount = 0
            ocr_sec = None
            err = None
            c_at = None
            unregistered_cnt += 1
            # Fast page count inspect
            try:
                info = pdf_service.inspect(p)
                pg_count = info.page_count
            except Exception:
                pg_count = 0

        total_pages += pg_count

        items.append(
            FolderPdfItem(
                name=p.name,
                stored_path=str_path,
                folder_name=p.parent.name,
                size_bytes=size,
                page_count=pg_count,
                is_registered=is_reg,
                file_id=fid,
                status=stat,
                pages_done=pdone,
                records_count=rcount,
                ocr_duration_sec=ocr_sec,
                error=err,
                created_at=c_at,
            )
        )

    return FolderScanResponse(
        folder_path=str(folder),
        folder_name=folder.name,
        total_files=len(items),
        total_pages=total_pages,
        total_size_bytes=total_size,
        completed_count=completed_cnt,
        pending_count=pending_cnt,
        processing_count=processing_cnt,
        error_count=error_cnt,
        unregistered_count=unregistered_cnt,
        items=items,
    )


@router.post("/reprocess", response_model=Job)
def reprocess_files(
    payload: dict,
    session: Session = Depends(get_session),
) -> Job:
    """Reset file status and re-submit an OCR extraction job."""
    file_ids = payload.get("file_ids", [])
    template_id = payload.get("template_id", "auto")
    if not file_ids:
        raise HTTPException(400, "No file IDs provided for re-processing")

    for fid in file_ids:
        row = session.get(FileRow, fid)
        if row is not None:
            row.status = FileStatus.PENDING.value
            row.pages_done = 0
            row.error = None
    session.flush()

    return manager.submit(file_ids, template_id=template_id)


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

    target = Path(str(payload.get("path", ""))).expanduser()
    recursive = bool(payload.get("recursive", True))
    if target.is_file():
        if target.suffix.lower() != ".pdf":
            raise HTTPException(400, f"Not a PDF file: {target}")
        paths = [target]
    elif target.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"
        paths = sorted(target.glob(pattern))
    else:
        raise HTTPException(400, f"Path does not exist: {target}")

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

    # Bulk query record error/warning aggregations grouped by page_id for this file
    record_stats = session.execute(
        select(
            RecordRow.page_id,
            func.count(RecordRow.id).label("record_count"),
            func.coalesce(func.sum(RecordRow.error_count), 0).label("error_count"),
            func.coalesce(func.sum(RecordRow.warning_count), 0).label("warning_count"),
        )
        .where(RecordRow.file_id == file_id)
        .group_by(RecordRow.page_id)
    ).all()

    stats_by_page = {
        r[0]: (r[1], int(r[2]), int(r[3]))
        for r in record_stats
    }

    summaries = []
    for row in rows:
        rec_count, err_count, warn_count = stats_by_page.get(row.id, (0, 0, 0))
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
                "record_count": rec_count,
                "error_count": err_count,
                "warning_count": warn_count,
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
