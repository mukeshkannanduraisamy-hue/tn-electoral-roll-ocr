"""Background OCR job execution with live progress.

Why a small thread pool
-----------------------
Pages run on a `ThreadPoolExecutor` of a few threads. Threads rather than
processes because they avoid the Windows process-spawn deadlocks and the
second copy of the weights a process pool costs; few of them because the
measured gain from the second worker is 11-18% and from the third is 2%.

Worth knowing before optimising anything here: the pool is not what decides
throughput. The same page takes 16.6 s on the CPU and 2.3 s on a GTX 1650, so
`ocr_service.resolve_device` outweighs every knob in this module put together.
`CPU_WORKER_LIMIT` carries the full table.

Why the workers are long-lived
------------------------------
Constructing a `PaddleOCR` costs ~8 seconds. A pool that respawned workers
per task would spend more time loading weights than doing OCR, so the pool
is created once, warmed at startup by `warmup_workers`, and reused for every
page in every job.

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
import logging
import threading
import time
import uuid
from concurrent.futures import (
    Executor,
    Future,
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime, timezone

from sqlalchemy import select, update

from ..config import settings
from ..db import (
    FileRow,
    JobRow,
    PageRow,
    load_pages_for_file,
    save_page,
    save_part_metadata,
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


# How many pages may be OCR'd at once, by device. Measured on this project's
# GTX 1650: one engine occupies 591 MiB and three workers peaked at 2177 MiB of
# 4096. A fourth would not fit with room to spare, and an unbounded count taken
# from `ocr_workers` -- 8 is a plausible setting -- would ask for about 4.7 GiB
# on a 4 GiB card and fail mid-job.
#
# Raising these should follow a VRAM measurement rather than the CPU core count,
# since it is card memory that runs out first.
GPU_WORKER_LIMIT = 3

# The CPU limit is 2 for the same reason, arrived at the same way. Eight voter
# pages of the TAM-15 roll through `process_page`, device forced per run:
#
#                  1 worker      2 workers     3 workers
#     cpu          16.60 s/pg    14.97 s/pg    14.74 s/pg     (1.00 / 1.11 / 1.13)
#     gpu:0         2.33 s/pg     2.01 s/pg     1.98 s/pg     (1.00 / 1.16 / 1.18)
#
# Two things fall out. The device is worth 7x and the worker count is worth
# 13-18%, so this constant is not where the performance of this pipeline is
# decided -- `resolve_device` is. And on both devices the curve flattens after
# the second worker: MKL-DNN already spreads a single page across every core,
# and a GPU serialises compute whatever the caller does, so the third thread
# competes with the first two rather than adding to them. Since engines are
# thread-local (~1 GB of host memory each, see `ocr_service`), buying 2% with
# a third CPU worker is not a trade worth making. The GPU keeps 3 because its
# engines cost card memory instead, and 3 x 591 MiB still fits a 4 GB card.
#
# Output was identical at every setting (240 records), which is the point of
# measuring accuracy alongside speed.
CPU_WORKER_LIMIT = 2


def resolve_worker_count(device: str, configured: int) -> int:
    """How many pages to OCR at once on `device`.

    Never more than `configured`: a deployment that asks for one worker gets
    one, whatever the hardware.
    """
    limit = GPU_WORKER_LIMIT if device.startswith("gpu") else CPU_WORKER_LIMIT
    return max(1, min(configured, limit))


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

    page = pipeline.process_page_with_retry(
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
        self._paused: set[str] = set()

    # ------------------------------------------------------------- lifecycle

    def executor(self) -> Executor:
        """The execution pool jobs run on.

        Threads, not processes: page tasks start immediately, with no
        process-spawn deadlocks on Windows and no second copy of the weights.

        Threads do NOT buy much page-level parallelism -- 11-18% at the second
        worker and ~2% at the third, on either device. They are still the right
        choice; the reason is startup and memory, not speed.
        """
        with self._lock:
            if self._executor is None:
                # A GPU takes fewer workers than a CPU but more than one: about
                # a third of each page is CPU work either side of inference, and
                # with a single worker the card idles through all of it. See
                # `resolve_worker_count` for the measurements.
                from . import ocr_service

                device = ocr_service.resolve_device()
                workers = resolve_worker_count(device, settings.ocr_workers)
                logger.info(
                    "Starting OCR ThreadPoolExecutor with %d worker(s) on %s",
                    workers, device,
                )
                self._executor = ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="ocr-worker"
                )
            return self._executor

    def shutdown(self) -> None:
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None

    def warmup_workers(self) -> None:
        """Force every pool thread to build and warm its OCR engine now.

        Each thread builds its engine lazily on its first page (engines are
        thread-local -- see `ocr_service`), so without this the cost lands
        inside the first job's latency after every boot or deploy. One task
        per worker, all submitted together, guarantees every thread in the
        pool gets a turn rather than the pool's own scheduler running a few
        tasks back-to-back on the same thread.
        """
        from . import ocr_service

        executor = self.executor()
        workers = getattr(executor, "_max_workers", 1)
        futures = [executor.submit(ocr_service.warmup) for _ in range(workers)]
        for future in futures:
            try:
                future.result()
            except Exception:  # noqa: BLE001 - a cold pool still beats a dead one
                logger.exception("OCR worker warmup failed")

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

    def pause(self, job_id: str) -> None:
        with self._lock:
            self._paused.add(job_id)

    def resume(self, job_id: str) -> None:
        with self._lock:
            self._paused.discard(job_id)

    def is_paused(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._paused


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

            # Per-file totals and tallies, alongside the job-wide ones. The
            # progress event used to carry only the job-wide figures, and the
            # UI stored those against each file -- so on a multi-file job every
            # file showed the whole job's numbers, and a file's bar filled as
            # other files completed.
            file_page_totals: dict[str, int] = {}
            for _f, f_id, _name, _pno in futures:
                file_page_totals[f_id] = file_page_totals.get(f_id, 0) + 1
            file_done: dict[str, int] = {f_id: 0 for f_id in file_page_totals}
            file_failed: dict[str, int] = {f_id: 0 for f_id in file_page_totals}

            future_map = {
                future: (file_id, file_name, page_number)
                for future, file_id, file_name, page_number in futures
            }

            start_time = time.perf_counter()

            for future in as_completed(future_map):
                while self.is_paused(job_id) and not self.is_cancelled(job_id):
                    time.sleep(0.5)

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
                        file_failed[file_id] = file_failed.get(file_id, 0) + 1
                    else:
                        completed += 1
                        file_done[file_id] = file_done.get(file_id, 0) + 1

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

                elapsed_sec = max(time.perf_counter() - start_time, 0.001)
                processed = completed + failed
                pages_per_sec = round(processed / elapsed_sec, 2)
                remaining = max(0, len(futures) - processed)
                eta_seconds = round(remaining / pages_per_sec, 1) if pages_per_sec > 0 else 0

                self._update_job(job_id, completed_pages=completed,
                                 failed_pages=failed,
                                 current_item=f"{file_name} p{page_number}")
                self._publish(
                    JobEvent(type="progress", job_id=job_id,
                             data={"completed": completed, "failed": failed,
                                   "total": len(futures),
                                   "file_id": file_id,
                                   "file_name": file_name,
                                   "page_number": page_number,
                                   # This file's own tally, so a row in the UI
                                   # can show its own progress rather than the
                                   # job's. Named distinctly from the job-wide
                                   # keys above precisely so the two cannot be
                                   # confused again.
                                   "file_completed": file_done.get(file_id, 0),
                                   "file_failed": file_failed.get(file_id, 0),
                                   "file_total": file_page_totals.get(file_id, 0),
                                   "pages_per_sec": pages_per_sec,
                                   "eta_seconds": eta_seconds})
                )


            # Spelling consensus, section reconciliation, part metadata, and auto DB promotion
            for file_id in touched_files:
                self._apply_consensus(file_id)
                self._reconcile_sections(file_id)
                self._extract_part_metadata(file_id)
                self._auto_promote_to_db(file_id)
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

    def _reconcile_sections(self, file_id: str) -> None:
        """Settle one section name per part, across every page of the file.

        Runs after the fan-in for the same reason consensus does: a page cannot
        tell that its section is one OCR reading among several, nor that it has
        none because a supplement page does not reprint the header.
        """
        try:
            from . import section_reconciliation

            with session_scope() as session:
                pages = load_pages_for_file(session, file_id)
                if not pages:
                    return

                report = section_reconciliation.apply_sections(pages)
                if report.records_changed:
                    for page in pages:
                        save_page(session, page, file_id)
                    logger.info(
                        "Sections reconciled on %s: %d records, %d pages inherited",
                        file_id, report.records_changed, report.pages_inherited,
                    )
        except Exception:  # noqa: BLE001 - never fail a job over post-processing
            logger.exception("Section reconciliation failed for file %s", file_id)

    def _extract_part_metadata(self, file_id: str) -> None:
        """Read the cover and summary sheets, and reconcile against them.

        Runs after the fan-in for the same reason consensus does: it needs
        every page of the file at once, both to find the two sheets and to
        count what extraction actually produced.
        """
        try:
            from . import roll_metadata

            with session_scope() as session:
                pages = load_pages_for_file(session, file_id)
                if not pages:
                    return
                metadata = roll_metadata.build(pages, file_id)
                save_part_metadata(session, file_id, metadata)

            reconciliation = metadata.reconciliation
            logger.info(
                "Part metadata for %s: %d records extracted, %s prints %s (%s)",
                file_id,
                reconciliation.extracted_records,
                reconciliation.source or "no sheet",
                reconciliation.printed_total,
                "reconciled" if reconciliation.matches else "MISMATCH",
            )
        except Exception:  # noqa: BLE001 - never fail a job over post-processing
            logger.exception("Part metadata extraction failed for file %s", file_id)

    def _auto_promote_to_db(self, file_id: str) -> None:
        """Auto-promote extracted OCR records to the curated voters table."""
        try:
            from ..routers.voters import auto_promote_file

            with session_scope() as session:
                res = auto_promote_file(session, file_id, actor="ocr_auto_pipeline")
                logger.info(
                    "Auto-promoted %s to DB: %d created, %d updated, %d skipped",
                    file_id,
                    res.created,
                    res.updated,
                    res.skipped,
                )
        except Exception:  # noqa: BLE001
            logger.exception("Auto-promotion to DB failed for file %s", file_id)

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
