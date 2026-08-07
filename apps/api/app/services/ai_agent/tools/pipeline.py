"""The state of the OCR corpus: files, pages, jobs.

"Why are there only 3,473 electors when I uploaded six files?" is a pipeline
question, not a roll question, and until now the assistant could not tell the
difference.

Each list here is capped, because the prompt cannot hold an unbounded table
and a model asking "how are my files doing" is not trying to read the whole
row set. But a cap that quietly hides rows is worse than no answer at all for
a tool whose entire job is reporting corpus state, so every result discloses
`total` (how many rows actually matched) alongside `returned` (how many came
back) and `truncated` (whether the two differ) -- the same contract
`search_voters` uses in `electors.py`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....db import FileRow, JobRow, PageRow, RecordRow
from ..registry import ToolError, register

#: A model asking "how are my files doing" wants a status check, not to read
#: the whole table -- but past this many rows the payload must say
#: `truncated` rather than let a partial listing pass as complete.
MAX_FILES = 50
MAX_PAGES = 50
MAX_JOBS = 10


def _total(session: Session, stmt) -> int:
    return session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


class FileStatusArgs(BaseModel):
    file_id: Optional[str] = Field(None, description="Omit to list every file")


@register(
    name="file_status",
    description=(
        "Processing state of one uploaded PDF or of every file: status, pages "
        "done out of total, page count, template and any error. Lists at "
        f"most {MAX_FILES} files at a time; the response's `total` and "
        "`truncated` say whether more exist than were returned."
    ),
    args_model=FileStatusArgs,
    label="Checking file status",
)
def file_status(session: Session, args: FileStatusArgs) -> Dict[str, Any]:
    base_stmt = select(FileRow)
    if args.file_id:
        base_stmt = base_stmt.where(FileRow.id == args.file_id.strip())

    total = _total(session, base_stmt)
    files = session.execute(
        base_stmt.order_by(FileRow.created_at.desc()).limit(MAX_FILES)
    ).scalars().all()
    if args.file_id and not files:
        raise ToolError(f"No file with id {args.file_id!r}.")

    return {
        "files": [
            {
                "file_id": f.id,
                "name": f.name,
                "status": f.status,
                "page_count": f.page_count,
                "pages_done": f.pages_done,
                "size_bytes": f.size_bytes,
                "template_id": f.template_id,
                "languages": f.languages,
                "error": f.error,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in files
        ],
        "returned": len(files),
        "total": total,
        "truncated": total > len(files),
    }


class PageDetailsArgs(BaseModel):
    page_id: Optional[str] = None
    file_id: Optional[str] = None
    page_number: Optional[int] = None
    failed_only: bool = Field(
        False, description="List only failed pages (works with or without file_id)"
    )


@register(
    name="page_details",
    description=(
        "One page, the pages of a file, or -- with no arguments -- pages "
        "across the whole corpus: page type, classification confidence, OCR "
        "duration, error, and how many records it produced. Set failed_only "
        "to list just the pages that failed; this works with or without "
        "file_id, so 'which pages failed OCR' can be asked with no "
        "arguments at all. Errors if file_id is given but does not match a "
        "real file; an empty list means nothing matched the filter. Lists "
        f"at most {MAX_PAGES} pages at a time, ordered by file then page "
        "number; the response's `total` and `truncated` say whether more "
        "exist than were returned."
    ),
    args_model=PageDetailsArgs,
    label="Inspecting pages",
)
def page_details(session: Session, args: PageDetailsArgs) -> Dict[str, Any]:
    base_stmt = select(PageRow)
    if args.page_id:
        base_stmt = base_stmt.where(PageRow.id == args.page_id.strip())
    elif args.file_id:
        file_id = args.file_id.strip()
        # An unknown file and a real file with no matching pages are
        # different facts -- "no such file" vs. "that file has no failed
        # pages" are opposite answers to "did anything go wrong here?" --
        # so the file's existence is checked independently of whatever the
        # page filter below then matches (which may legitimately be empty).
        file_exists = session.execute(
            select(FileRow.id).where(FileRow.id == file_id)
        ).scalar_one_or_none()
        if file_exists is None:
            raise ToolError(f"No file with id {args.file_id!r}.")

        base_stmt = base_stmt.where(PageRow.file_id == file_id)
        if args.page_number is not None:
            base_stmt = base_stmt.where(PageRow.page_number == args.page_number)
        if args.failed_only:
            base_stmt = base_stmt.where(PageRow.status == "failed")
    else:
        # Neither page_id nor file_id: survey the whole corpus. This is the
        # only way "which pages failed OCR?" (a corpus-wide question) can be
        # answered at all -- previously this branch raised, so a model asking
        # the obvious question got the same refusal on every retry.
        if args.page_number is not None:
            base_stmt = base_stmt.where(PageRow.page_number == args.page_number)
        if args.failed_only:
            base_stmt = base_stmt.where(PageRow.status == "failed")

    total = _total(session, base_stmt)
    pages = session.execute(
        base_stmt.order_by(PageRow.file_id, PageRow.page_number).limit(MAX_PAGES)
    ).scalars().all()
    if args.page_id and not pages:
        raise ToolError(f"No page with id {args.page_id!r}.")

    rows = []
    for p in pages:
        record_count = session.execute(
            select(func.count()).select_from(RecordRow).where(RecordRow.page_id == p.id)
        ).scalar_one()
        rows.append(
            {
                "page_id": p.id,
                "file_id": p.file_id,
                "page_number": p.page_number,
                "status": p.status,
                "page_type": p.page_type,
                "classification_confidence": round(float(p.classification_confidence or 0.0), 3),
                "template_id": p.template_id,
                "ocr_ms": p.ocr_ms,
                "error": p.error,
                "records": record_count,
            }
        )
    return {
        "pages": rows,
        "returned": len(rows),
        "total": total,
        "truncated": total > len(rows),
    }


class JobStatusArgs(BaseModel):
    job_id: Optional[str] = Field(None, description="Omit for the most recent jobs")


@register(
    name="job_status",
    description=(
        "OCR job queue state: queued, running or finished, with completed and "
        "failed page counts and the item currently being processed. Lists at "
        f"most {MAX_JOBS} of the most recent jobs; the response's `total` "
        "and `truncated` say whether more exist than were returned."
    ),
    args_model=JobStatusArgs,
    label="Checking jobs",
)
def job_status(session: Session, args: JobStatusArgs) -> Dict[str, Any]:
    base_stmt = select(JobRow)
    if args.job_id:
        base_stmt = base_stmt.where(JobRow.id == args.job_id.strip())

    total = _total(session, base_stmt)
    jobs = session.execute(
        base_stmt.order_by(JobRow.created_at.desc()).limit(MAX_JOBS)
    ).scalars().all()
    if args.job_id and not jobs:
        raise ToolError(f"No job with id {args.job_id!r}.")

    return {
        "jobs": [
            {
                "job_id": j.id,
                "status": j.status,
                "file_ids": j.file_ids,
                "total_pages": j.total_pages,
                "completed_pages": j.completed_pages,
                "failed_pages": j.failed_pages,
                "current_item": j.current_item,
                "error": j.error,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in jobs
        ],
        "returned": len(jobs),
        "total": total,
        "truncated": total > len(jobs),
    }
