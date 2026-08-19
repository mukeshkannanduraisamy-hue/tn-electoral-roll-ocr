"""FastAPI application entry point.

Run with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import init_db, reconcile_interrupted_work
from .auth import ensure_admin_user, require_user
from .routers import (
    ai_chat, auth, export, files, jobs, pages, photos, polling_stations, records,
    templates, validation, voters,
)
# Aliased: `settings` is already the config object imported above.
from .routers import settings as settings_router
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
    try:
        reconcile_interrupted_work()
    except Exception as exc:
        logger.warning("Startup reconciliation skipped: %s", exc)
    try:
        ensure_admin_user()
    except Exception as exc:
        logger.warning("Startup admin user check skipped: %s", exc)
    logger.info("Data directory: %s", settings.data_dir)
    logger.info(
        "OCR: lang=%s version=%s device=%s workers=%d",
        settings.ocr_lang,
        settings.ocr_version,
        settings.ocr_device,
        settings.ocr_workers,
    )
    # Load every worker thread's PaddleOCR engine now instead of on the first
    # job's first page. Backgrounded so /api/health and static assets are
    # reachable immediately instead of waiting on ~8s per worker.
    threading.Thread(
        target=manager.warmup_workers,
        name="ocr-warmup",
        daemon=True,
    ).start()
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

# A wildcard origin and credentials are mutually exclusive: browsers refuse
# `Access-Control-Allow-Origin: *` on any request carrying cookies, and the
# session cookie is now exactly that. `allow_origin_regex=".*"` makes
# Starlette echo the caller's actual origin instead, which is the only way to
# express "any origin, with credentials".
#
# In the supported setup this never fires -- the browser talks to Next, which
# proxies to the API server-side, so requests are same-origin.
_cors_kwargs: dict = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["Content-Disposition"],  # lets the browser read export filenames
}
if _origins == ["*"]:
    _cors_kwargs["allow_origin_regex"] = ".*"
    _cors_kwargs["allow_origins"] = []
    if settings.auth_enabled:
        logger.warning(
            "OCR_CORS_ORIGINS is '*'. Set it to the frontend origin in "
            "production so a hostile page cannot call this API with the "
            "user's session cookie."
        )
else:
    _cors_kwargs["allow_origins"] = _origins

logger.info("CORS origins: %s", _origins)
app.add_middleware(CORSMiddleware, **_cors_kwargs)

# Everything that touches voter data sits behind authentication.
#
# Applied at the router level rather than on each function: there are ~30
# endpoints, and a per-signature dependency is one forgotten parameter away
# from silently exposing PII. A new endpoint added to any of these routers is
# protected by construction.
PROTECTED = [Depends(require_user)]

# Open by design: login itself cannot require a session, and /api/auth/status
# is what the UI polls to decide whether to show the login screen.
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

app.include_router(voters.router, prefix="/api/voters", tags=["voters"])
app.include_router(polling_stations.router, prefix="/api/polling-stations", tags=["polling_stations"], dependencies=PROTECTED)
app.include_router(photos.router, prefix="/api/photos", tags=["photos"],
                   dependencies=PROTECTED)
app.include_router(files.router, prefix="/api/files", tags=["files"],
                   dependencies=PROTECTED)
app.include_router(pages.router, prefix="/api/pages", tags=["pages"],
                   dependencies=PROTECTED)
app.include_router(records.router, prefix="/api/records", tags=["records"],
                   dependencies=PROTECTED)
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"],
                   dependencies=PROTECTED)
app.include_router(export.router, prefix="/api/export", tags=["export"],
                   dependencies=PROTECTED)
app.include_router(templates.router, prefix="/api/templates", tags=["templates"],
                   dependencies=PROTECTED)
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"],
                   dependencies=PROTECTED)
app.include_router(ai_chat.router, prefix="/api/ai", tags=["ai"], dependencies=PROTECTED)
app.include_router(validation.router, prefix="/api/validation", tags=["validation"], dependencies=PROTECTED)


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


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception):
    """Return a JSON 500 instead of dropping the TCP connection.

    Without this, an unhandled exception in a synchronous endpoint causes
    uvicorn to close the socket before sending a response, which the Next.js
    proxy reports as ECONNRESET / 'socket hang up'.
    """
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )
