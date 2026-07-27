"""FastAPI application entry point.

Run with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db, reconcile_interrupted_work
from .routers import export, files, jobs, pages, records, templates
from .services.job_queue import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    init_db()
    # Jobs cannot outlive the process that runs them, so anything still
    # marked in-flight at boot was orphaned by a restart. Clear it before
    # serving traffic, or the UI shows work that will never complete.
    reconcile_interrupted_work()
    logger.info("Data directory: %s", settings.data_dir)
    logger.info(
        "OCR: lang=%s version=%s device=%s workers=%d",
        settings.ocr_lang,
        settings.ocr_version,
        settings.ocr_device,
        settings.ocr_workers,
    )
    yield
    # The pool holds several GB of model weights; release it deterministically.
    manager.shutdown()


app = FastAPI(
    title="OCR Workspace API",
    description=(
        "PaddleOCR-backed extraction, review and export for scanned PDFs, "
        "with pluggable document templates."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

def _cors_origins() -> list[str]:
    """Normalise the configured origins.

    CORS matches on a full origin (`https://host`), but Render's
    `fromService: property: host` injects a bare hostname. Accept either form
    and add the scheme, otherwise every cross-origin request is rejected with
    no obvious cause.
    """
    origins: list[str] = []
    for raw in settings.cors_origins.split(","):
        value = raw.strip().rstrip("/")
        if not value:
            continue
        if value == "*":
            return ["*"]
        if "://" not in value:
            # localhost keeps http; anything else on the internet is https.
            scheme = "http" if value.startswith(("localhost", "127.0.0.1")) else "https"
            value = f"{scheme}://{value}"
        origins.append(value)
    return origins


_origins = _cors_origins()
logger.info("CORS origins: %s", _origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # so the browser can read export filenames
)

app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(pages.router, prefix="/api/pages", tags=["pages"])
app.include_router(records.router, prefix="/api/records", tags=["records"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])


@app.get("/", tags=["meta"])
def root() -> dict:
    """Root endpoint welcoming visitors and providing system links."""
    return {
        "service": "Tamil Nadu Electoral Roll OCR API",
        "status": "online",
        "docs": "/docs",
        "health": "/api/health",
        "settings": "/api/settings",
    }


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "ocr_lang": settings.ocr_lang,
        "ocr_version": settings.ocr_version,
        "ocr_device": settings.ocr_device,
        "workers": settings.ocr_workers,
        "consensus_enabled": settings.consensus_enabled,
    }


@app.get("/api/settings", tags=["meta"])
def read_settings() -> dict:
    """Surface the tunables the UI displays in its settings panel."""
    return {
        "ocr_lang": settings.ocr_lang,
        "ocr_version": settings.ocr_version,
        "ocr_device": settings.ocr_device,
        "render_dpi": settings.render_dpi,
        "upscale_factor": settings.upscale_factor,
        "ocr_text_score_thresh": settings.ocr_text_score_thresh,
        "expected_grid_rows": settings.expected_grid_rows,
        "expected_grid_cols": settings.expected_grid_cols,
        "grid_deviation_tolerance": settings.grid_deviation_tolerance,
        "label_fuzzy_threshold": settings.label_fuzzy_threshold,
        "consensus_enabled": settings.consensus_enabled,
        "consensus_auto_apply": settings.consensus_auto_apply,
        "consensus_min_ratio": settings.consensus_min_ratio,
    }


@app.exception_handler(ValueError)
async def value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
