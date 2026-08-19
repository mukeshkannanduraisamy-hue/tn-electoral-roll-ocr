# Repo cleanup + OCR worker warm-start

## Problem

Two asks: (1) the repo has accumulated untracked one-off scripts and dumps
that aren't part of the app, and (2) the OCR extraction pipeline should be
faster. Investigation showed the pipeline is already heavily tuned (turbo
preprocessing mode, cached per-thread PaddleOCR engines, tuned worker counts,
mobile detection model) — `bench.py`'s own profiling notes that OCR inference
is ~94% of page time and everything else is noise. The one real, low-risk gap:
OCR engines build lazily on first use per worker thread, so the first job
after a boot/deploy pays ~8s × `ocr_workers` of serial model-load time inside
user-facing job latency instead of during startup.

## Scope

**Cleanup** (delete, untracked/unreferenced only):
- `scratch/*.py`, `scratch/*.json`, `scratch/*.txt` one-off analysis scripts
  and result dumps (not imported by the app)
- `apps/api/{bench,debug_p8_p16,debug_p8_p16_steps,extract_all_penn,ingest_all_penn,run_all_supervised,run_parts_1_17,extract_tam15_full,eval_penn_accuracy,score_ground_truth,build_ground_truth_sheet}.py` minus `bench.py`, which stays (it's the tool used to measure any future pipeline speed change, not a one-off script)
- `OCR/` nested folder (leftover Antigravity skill install, not project code)

Not touched: `DB.xlsx`, `manage.py`, `scratch/agentic-awesome-skills/`,
`scratch/hf_space/` (not in scope per user selection), anything under
`apps/api/app/` or `apps/api/tests/`.

**Perf**: pre-warm every OCR worker thread's PaddleOCR engine during API
startup (`lifespan`), instead of lazily on first `predict()` call per thread.

## Design

`job_queue.JobManager.executor()` lazily creates a `ThreadPoolExecutor` with
`resolve_worker_count(device, settings.ocr_workers)` threads, and each thread
builds its own cached engine (`ocr_service.get_engine`) the first time it
handles a page — this is required (engines are not thread-safe, sharing one
across threads segfaults). Today that first build happens mid-job.

Add a `job_queue.warmup_workers()` that forces the executor to exist and
submits one no-op warmup task per worker thread, waiting for all of them
before returning. Call it from `main.lifespan` after `init_db()`/
`ensure_admin_user()`, in a background thread so it doesn't block the app
from serving `/api/health` while models load (health checks / static asset
serving shouldn't wait on ~8s × N of model loading).

No change to `ocr_service.py` — `warmup()` already exists and does exactly
what's needed per-thread; `job_queue` just needs to invoke it once per pool
thread at boot instead of leaving it to the first real page.

## Risks

- Startup does more work before the pool is fully warm; mitigated by running
  it in a background thread so the API is reachable immediately, and jobs
  submitted before warmup finishes still work (they just pay the same cost
  they do today).
- None of this touches OCR accuracy, preprocessing, or output — it only moves
  when model loading happens.
