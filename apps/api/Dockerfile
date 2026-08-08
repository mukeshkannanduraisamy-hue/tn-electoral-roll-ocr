# =============================================================================
# OCR API - FastAPI + PaddleOCR
#
# Build context is the REPOSITORY ROOT, not this directory:
#     docker build -f apps/api/Dockerfile -t ocr-api .
#
# On Apple Silicon add --platform=linux/amd64: paddlepaddle publishes
# manylinux x86_64 wheels only, and an arm64 build fails at pip install.
# docker-compose.yml already pins this; a standalone build does not.
# =============================================================================

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Paddle spawns one OpenMP thread per core. On a small shared-vCPU host
    # that thrashes and inflates RSS, so cap it.
    OMP_NUM_THREADS=2

# PaddleOCR pulls in opencv, which needs these even in its headless form.
# libgomp1 is required by paddlepaddle itself.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
        # PDF reports embed a Tamil font. Without it ReportLab falls back to
        # a Latin-only face and every name renders as an empty box, so this
        # package is a functional requirement, not a nicety.
        fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so the ~1 GB paddle layer is cached across code changes.
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . ./

# Data (SQLite, uploads, rendered pages) and the model cache both belong on a
# mounted volume; these are only sane defaults if none is provided.
ENV OCR_DATA_DIR=/var/data \
    PADDLE_PDX_CACHE_HOME=/var/data/.paddlex
RUN mkdir -p /var/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# One worker on purpose: each holds its own ~1 GB copy of the models, so
# scale with a bigger instance rather than more workers.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
