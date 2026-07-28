"""Background OCR job execution with live progress.

Why a process pool
------------------
PaddleOCR inference is CPU-bound Python plus native code that does not
release the GIL predictably, so threads would serialise. Processes give real
parallelism.

Why the workers are long-lived
------------------------------
Constructing a `PaddleOCR` costs ~8 seconds. A pool that respawned workers
per task would spend more time loading weights than doing OCR, so workers
are created once with an initialiser that warms the model and are then
reused for every page in every job.

Progress delivery
-----------------
Work runs in a plain thread (so it survives the request that started it) and
publishes events to per-subscriber `asyncio.Queue`s via
`loop.call_soon_threadsafe`. The job row is also updated in SQLite after
every page, so a browser that reconnects mid-job recovers the true state
rather than waiting for the next event.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from concurrent.futures import (
    Executor,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

from ..config import settings
from ..db import (
    FileRow,
    JobRow,
    PageRow,
    load_pages_for_file,
    save_page,
    session_scope,
)
from ..schemas.core import (
    FileStatus,
    Job,
    JobEvent,
    JobStatus,
    Page,
    PageStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker process
# ---------------------------------------------------------------------------


def _init_worker() -> None:
    """Runs once per worker process: load and warm the OCR models."""
    logging.basicConfig(level=logging.WARNING)
    try:
        from . import ocr_service

        ocr_service.warmup()
    except Exception as exc:  # noqa: BLE001 - a cold worker still beats a dead one
        logger.warning("Worker warmup failed: %s", exc)


def existing_page_ids(session, file_id: str) -> dict[int, str]:
    """Map page_number -> existing page id for one file.

    Used so re-processing reuses a page's identity. See the call site for why
    generating a fresh id instead duplicates every record on the page.
    """
    return dict(
        session.execute(
            select(PageRow.page_number, PageRow.id).where(
                PageRow.file_id == file_id
            )
        ).all()
    )


def _process_page_task(
    pdf_path: str,
    page_number: int,
    file_id: str,
    template_id: str,
    lang: str | None,
    page_id: str,
) -> str:
    """Top-level so it is picklable. Returns the Page as a JSON string."""
    from . import pipeline

    page = pipeline.process_page(
        pdf_path,
        page_number,
        file_id,
        template_id=template_id,
        lang=lang,
        page_id=page_id,
    )
    return page.model_dump_json()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class JobManager:
    def __init__(self) -> None:
        self._executor: Executor | None = None
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._cancelled: set[str] = set()

    # ------------------------------------------------------------- lifecycle

    def executor(self) -> Executor:
        """The pool jobs run on.

        Two modes, chosen by `OCR_OCR_WORKERS`:

        * ``>= 1`` -- a process pool. Real parallelism across pages, but each
          worker loads its own ~0.9 GB copy of the models on top of the API
          process's own set.
        * ``0``    -- a single background thread inside the API process. It
          reuses the model set already loaded there, roughly halving total
          memory, and is what makes the app fit on a small cloud instance.
          PaddleOCR spends most of its time in native code that releases the
          GIL, so a lone thread is not much slower than a lone process.
        """
        with self._lock:
            if self._executor is None:
                if settings.ocr_workers >= 1:
                    logger.info(
                        "Starting OCR process pool with %d worker(s)",
                        settings.ocr_workers,
                    )
                    self._executor = ProcessPoolExecutor(
                        max_workers=settings.ocr_workers,
                        initializer=_init_worker,
                    )
                else:
                    logger.info(
                        "OCR_WORKERS=0 -- running jobs in-process on one thread "
                        "(lower memory, no page parallelism)"
                    )
                    self._executor = ThreadPoolExecutor(
                        max_workers=1, thread_name_prefix="ocr"
                    )
            return self._executor

    def shutdown(self) -> None:
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None

    # ------------------------------------------------------------ pub / sub

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.setdefault(job_id, []).append((loop, queue))
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id, [])
            self._subscribers[job_id] = [(l, q) for l, q in subs if q is not queue]

    def _publish(self, event: JobEvent) -> None:
        with self._lock:
            subs = list(self._subscribers.get(event.job_id, []))
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                # The subscriber's loop has closed; the SSE handler cleans up.
                pass

    # --------------------------------------------------------------- control

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    # ---------------------------------------------------------------- submit

    def submit(self, file_ids: list[str], template_id: str = "auto",
               lang: str | None = None) -> Job:
        """Queue a job and start it on a background thread."""
        job_id = uuid.uuid4().hex[:12]

        with session_scope() as session:
            total_pages = 0
            for file_id in file_ids:
                row = session.get(FileRow, file_id)
                if row:
                    total_pages += max(row.page_count, 1)

            job_row = JobRow(
                id=job_id,
                file_ids=list(file_ids),
                status=JobStatus.QUEUED.value,
                total_pages=total_pages,
            )
            session.add(job_row)

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, file_ids, template_id, lang),
            name=f"ocr-job-{job_id}",
            daemon=True,
        )
        thread.start()

        with session_scope() as session:
            return _job_schema(session.get(JobRow, job_id))

    # ------------------------------------------------------------- execution

    def _run_job(self, job_id: str, file_ids: list[str], template_id: str,
                 lang: str | None) -> None:
        started = datetime.now(timezone.utc)
        try:
            self._update_job(job_id, status=JobStatus.RUNNING.value, started_at=started)
            self._publish(JobEvent(type="progress", job_id=job_id,
                                   data={"status": "running"}))

            futures: list[tuple[Future, str, str, int]] = []
            executor = self.executor()

            # Fan every page of every file into the pool at once; the pool's
            # own queue handles ordering and back-pressure.
            with session_scope() as session:
                for file_id in file_ids:
                    file_row = session.get(FileRow, file_id)
                    if file_row is None:
                        continue
                    file_row.status = FileStatus.PROCESSING.value
                    pdf_path = file_row.stored_path
                    page_count = max(file_row.page_count, 1)

                    # `pages_done` is a per-run counter. Without this reset it
                    # keeps climbing across re-runs and the UI shows progress
                    # like "2 of 1 pages".
                    file_row.pages_done = 0

                    # Page identity must be derived from (file, page number),
                    # never freshly generated. A new uuid per run creates a
                    # SECOND page row for the same physical page, so
                    # re-processing a file duplicates every record instead of
                    # replacing it -- 30 voters silently become 60, and every
                    # export double-counts them.
                    existing_ids = existing_page_ids(session, file_id)

                    for page_number in range(1, page_count + 1):
                        page_id = existing_ids.get(
                            page_number, uuid.uuid4().hex[:12]
                        )
                        future = executor.submit(
                            _process_page_task,
                            pdf_path,
                            page_number,
                            file_id,
                            template_id,
                            lang,
                            page_id,
                        )
                        futures.append((future, file_id, file_row.name, page_number))

            completed = failed = 0
            touched_files: set[str] = set()

            future_map = {
                future: (file_id, file_name, page_number)
                for future, file_id, file_name, page_number in futures
            }

            for future in as_completed(future_map):
                file_id, file_name, page_number = future_map[future]
                if self.is_cancelled(job_id):
                    future.cancel()
                    continue
                try:
                    page = Page.model_validate_json(future.result())
                    with session_scope() as session:
                        save_page(session, page, file_id)
                        # FIX B3: Use atomic SQL increment to avoid stale ORM
                        # cached value being read back and overwriting the DB.
                        session.execute(
                            update(FileRow)
                            .where(FileRow.id == file_id)
                            .values(pages_done=FileRow.pages_done + 1)
                        )
                        # Only update template_id if not already set
                        if page.template_id:
                            file_row = session.get(FileRow, file_id)
                            if file_row and not file_row.template_id:
                                file_row.template_id = page.template_id

                    # FIX B2: Normalize page.status to string before comparing
                    page_status = page.status if isinstance(page.status, str) else page.status.value
                    if page_status == PageStatus.ERROR.value:
                        failed += 1
                    else:
                        completed += 1

                    touched_files.add(file_id)
                    self._publish(
                        JobEvent(
                            type="page_done",
                            job_id=job_id,
                            data={
                                "file_id": file_id,
                                "page_id": page.id,
                                "page_number": page_number,
                                "records": len(page.records),
                                "status": page_status,
                            },
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    logger.exception("Page %d of %s failed: %s", page_number, file_name, exc)
                    self._publish(
                        JobEvent(type="error", job_id=job_id,
                                 data={"file_id": file_id,
                                       "page_number": page_number,
                                       "message": str(exc)})
                    )

                self._update_job(job_id, completed_pages=completed,
                                 failed_pages=failed,
                                 current_item=f"{file_name} p{page_number}")
                self._publish(
                    JobEvent(type="progress", job_id=job_id,
                             data={"completed": completed, "failed": failed,
                                   "total": len(futures),
                                   "file_id": file_id,
                                   "file_name": file_name,
                                   "page_number": page_number})
                )

            # Spelling consensus needs every page of a file at once, so it
            # runs after the fan-in rather than per page.
            for file_id in touched_files:
                self._apply_consensus(file_id)
                with session_scope() as session:
                    file_row = session.get(FileRow, file_id)
                    if file_row:
                        file_row.status = FileStatus.COMPLETED.value
                self._publish(JobEvent(type="file_done", job_id=job_id,
                                       data={"file_id": file_id}))

            status = (
                JobStatus.CANCELLED.value
                if self.is_cancelled(job_id)
                else JobStatus.COMPLETED.value
            )
            self._update_job(job_id, status=status,
                             finished_at=datetime.now(timezone.utc))
            self._publish(JobEvent(type="job_done", job_id=job_id,
                                   data={"status": status,
                                         "completed": completed,
                                         "failed": failed}))

        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job_id)
            self._update_job(job_id, status=JobStatus.FAILED.value, error=str(exc),
                             finished_at=datetime.now(timezone.utc))
            self._publish(JobEvent(type="error", job_id=job_id,
                                   data={"message": str(exc)}))

    def _apply_consensus(self, file_id: str) -> None:
        """Harmonise spellings across every page of one file."""
        if not settings.consensus_enabled:
            return
        try:
            from . import consensus

            with session_scope() as session:
                pages = load_pages_for_file(session, file_id)
                if not pages:
                    return
                report = consensus.apply_consensus(pages)
                if report.suggestions:
                    for page in pages:
                        save_page(session, page, file_id)
                    logger.info(
                        "Consensus on %s: %d corrections", file_id, report.suggestions
                    )
        except Exception:  # noqa: BLE001 - never fail a job over post-processing
            logger.exception("Consensus failed for file %s", file_id)

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _update_job(job_id: str, **fields) -> None:
        with session_scope() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return
            for key, value in fields.items():
                setattr(row, key, value)


def _job_schema(row: JobRow | None) -> Job:
    from ..db import job_to_schema

    if row is None:
        raise ValueError("Job not found")
    return job_to_schema(row)


# Module-level singleton; FastAPI shuts it down on application exit.
manager = JobManager()
