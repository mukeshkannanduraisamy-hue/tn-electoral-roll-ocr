"""Job submission, status and the SSE progress stream."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..db import FileRow, JobRow, get_session, job_to_schema
from ..schemas.core import Job, JobStatus
from ..services.job_queue import manager

logger = logging.getLogger(__name__)
router = APIRouter()

# Without periodic traffic, proxies and browsers drop an idle SSE connection.
HEARTBEAT_SECONDS = 15


class JobRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list)
    template_id: str = "auto"
    lang: str | None = None
    all_pending: bool = False
    """Process every file currently in the pending state."""


@router.post("", response_model=Job)
def create_job(payload: JobRequest, session: Session = Depends(get_session)) -> Job:
    file_ids = list(payload.file_ids)

    if payload.all_pending:
        pending = (
            session.execute(
                select(FileRow.id).where(FileRow.status == "pending")
            )
            .scalars()
            .all()
        )
        file_ids = list(dict.fromkeys([*file_ids, *pending]))

    if not file_ids:
        raise HTTPException(400, "No files to process")

    missing = [
        fid for fid in file_ids if session.get(FileRow, fid) is None
    ]
    if missing:
        raise HTTPException(404, f"Unknown file ids: {', '.join(missing)}")

    return manager.submit(file_ids, template_id=payload.template_id, lang=payload.lang)


@router.get("", response_model=list[Job])
def list_jobs(session: Session = Depends(get_session)) -> list[Job]:
    rows = (
        session.execute(select(JobRow).order_by(JobRow.created_at.desc()).limit(50))
        .scalars()
        .all()
    )
    return [job_to_schema(r) for r in rows]


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, session: Session = Depends(get_session)) -> Job:
    row = session.get(JobRow, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    return job_to_schema(row)


@router.post("/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: str, session: Session = Depends(get_session)) -> Job:
    row = session.get(JobRow, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    manager.cancel(job_id)
    return job_to_schema(row)


@router.post("/{job_id}/pause", response_model=Job)
def pause_job(job_id: str, session: Session = Depends(get_session)) -> Job:
    row = session.get(JobRow, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    manager.pause(job_id)
    return job_to_schema(row)


@router.post("/{job_id}/resume", response_model=Job)
def resume_job(job_id: str, session: Session = Depends(get_session)) -> Job:
    row = session.get(JobRow, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    manager.resume(job_id)
    return job_to_schema(row)



@router.get("/{job_id}/events")
async def job_events(job_id: str):
    """Server-sent events for live progress.

    The first message is always the current job state, so a client that
    connects late -- or reconnects after a page refresh -- immediately has
    the truth instead of waiting for the next page to finish.
    """
    from ..db import session_scope

    with session_scope() as session:
        row = session.get(JobRow, job_id)
        if row is None:
            raise HTTPException(404, "Job not found")
        snapshot = job_to_schema(row)

    queue = manager.subscribe(job_id)

    async def stream():
        try:
            yield {
                "event": "snapshot",
                "data": snapshot.model_dump_json(),
            }

            terminal = {
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
            }
            if snapshot.status in terminal:
                return

            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue

                yield {
                    "event": event.type,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }

                if event.type == "job_done":
                    break
        except asyncio.CancelledError:
            raise
        finally:
            manager.unsubscribe(job_id, queue)

    return EventSourceResponse(stream())
