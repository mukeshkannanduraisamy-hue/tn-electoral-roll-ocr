"""PaddleOCR wrapper.

Two things this module exists to get right:

**Warm models.** Constructing a `PaddleOCR` costs ~8s (weights load + graph
build). Doing that per page would dominate runtime, so instances are cached
per (lang, version, device) for the life of the process. Worker processes are
long-lived precisely so this cache stays warm.

**Defensive result access.** PaddleOCR 3.x returns result objects that behave
as both attribute-bearing objects and dicts, and the exact surface has moved
between point releases. `_field()` reads either shape so a patch upgrade
can't silently break extraction.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import settings
from ..schemas.core import BBox, OcrLine

logger = logging.getLogger(__name__)

# Keyed on EVERY setting that affects construction, not just lang/version/
# device. The detection model and side-length limit are baked into the
# instance, so leaving them out of the key means changing them silently
# returns the old engine -- a setting that looks configurable but is not.
_InstanceKey = tuple[str, str, str, str, int]

# ---------------------------------------------------------------------------
# Engines are cached PER THREAD, and that is not an optimisation detail.
#
# A PaddleOCR predictor is NOT thread-safe. Two threads calling `predict()` on
# the same instance segfault the process outright -- reproduced here as a
# Windows ACCESS_VIOLATION (0xC0000005) inside
# paddlex/inference/models/runners/paddle_static/runner.py, with no Python
# traceback because the crash is below the interpreter.
#
# That is fatal rather than merely wrong: it takes down the whole API server
# mid-job, so every other page in flight dies with it. A module-level cache
# shared across a ThreadPoolExecutor hits this on the very first concurrent
# page.
#
# Threading itself is fine -- verified: two threads with a private engine each
# complete normally. So the cache is thread-local, and each worker thread pays
# for its own copy of the weights (~1 GB). Size `ocr_workers` against RAM
# accordingly; see config.ocr_workers.
# ---------------------------------------------------------------------------
_local = threading.local()


def _cache() -> dict[_InstanceKey, Any]:
    cache = getattr(_local, "instances", None)
    if cache is None:
        cache = {}
        _local.instances = cache
    return cache


def reset() -> None:
    """Drop this thread's cached engines so the next call rebuilds them.

    Used by benchmarks and tests that vary model configuration in-process.
    Only affects the calling thread -- there is no safe way to free another
    thread's predictor from here.
    """
    _cache().clear()


class OcrError(Exception):
    """OCR failed for a page."""


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------


_INIT_LOCK = threading.Lock()


def get_engine(
    lang: str | None = None,
    version: str | None = None,
    device: str | None = None,
):
    """Return a warm PaddleOCR instance, constructing it on first use."""
    lang = lang or settings.ocr_lang
    version = version or settings.ocr_version
    device = device or settings.ocr_device

    key: _InstanceKey = (
        lang, version, device,
        settings.ocr_det_model or "",
        settings.ocr_det_limit_side_len,
    )
    cache = _cache()
    if key in cache:
        return cache[key]

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:  # pragma: no cover - environment problem
        raise OcrError(
            "paddleocr is not installed. Run scripts/bootstrap.ps1 first."
        ) from exc

    logger.info("Loading PaddleOCR (lang=%s, version=%s, device=%s)...", lang, version, device)
    started = time.perf_counter()

    kwargs: dict[str, Any] = {
        "lang": lang,
        "device": device,
        "use_doc_orientation_classify": settings.ocr_use_doc_orientation_classify,
        "use_doc_unwarping": settings.ocr_use_doc_unwarping,
        "use_textline_orientation": settings.ocr_use_textline_orientation,
        "text_det_limit_side_len": settings.ocr_det_limit_side_len,
        # `max` keeps the long side at the limit instead of shrinking to it,
        # which would undo the upscale we just paid for.
        "text_det_limit_type": "max",
    }
    if version:
        kwargs["ocr_version"] = version
    if settings.ocr_det_model:
        # Explicit detection model -- used to drop to the mobile detector on
        # memory-constrained hosts. See config.ocr_det_model.
        kwargs["text_detection_model_name"] = settings.ocr_det_model
        # When text_detection_model_name is set, PaddleOCR skips `lang` resolution.
        # Explicitly pass text_recognition_model_name so Tamil recognition is preserved.
        if lang == "ta" and (version == "PP-OCRv5" or not version):
            kwargs["text_recognition_model_name"] = "ta_PP-OCRv5_mobile_rec"

    with _INIT_LOCK:
        # Re-check key inside lock in case another thread initialized it while waiting
        if key in cache:
            return cache[key]
        try:
            engine = PaddleOCR(**kwargs)
        except (TypeError, ValueError) as exc:
            # A kwarg this build doesn't accept, or a lang/version pair with no
            # published model. Retry with the minimal signature so the caller
            # still gets working OCR rather than a hard failure.
            logger.warning("PaddleOCR rejected full kwargs (%s); retrying minimal.", exc)
            try:
                engine = PaddleOCR(lang=lang, device=device)
            except Exception as exc2:  # noqa: BLE001
                raise OcrError(f"Could not initialise PaddleOCR: {exc2}") from exc2

    elapsed = time.perf_counter() - started
    logger.info(
        "PaddleOCR ready in %.1fs (thread %s, %d engine(s) held by this thread)",
        elapsed, threading.current_thread().name, len(cache) + 1,
    )
    cache[key] = engine
    return engine


def warmup(lang: str | None = None) -> float:
    """Load models and run one tiny inference. Returns seconds elapsed."""
    started = time.perf_counter()
    engine = get_engine(lang=lang)
    blank = np.full((64, 256, 3), 255, dtype=np.uint8)
    try:
        engine.predict(blank)
    except Exception as exc:  # noqa: BLE001 - a blank page may legitimately error
        logger.debug("Warmup inference returned: %s", exc)
    return time.perf_counter() - started


# ---------------------------------------------------------------------------
# Result normalisation
# ---------------------------------------------------------------------------


def _field(result: Any, *names: str) -> Any:
    """Read a field from a PaddleOCR result, whichever shape it takes."""
    for name in names:
        if isinstance(result, dict) and name in result:
            return result[name]
        value = getattr(result, name, None)
        if value is not None:
            return value
    # Some builds nest everything under `.json` / `.res`.
    for container in ("json", "res"):
        blob = getattr(result, container, None)
        if isinstance(blob, dict):
            if container == "json" and "res" in blob and isinstance(blob["res"], dict):
                blob = blob["res"]
            for name in names:
                if name in blob:
                    return blob[name]
    return None


def _poly_to_bbox(poly: Any) -> BBox:
    pts = np.asarray(poly, dtype=float).reshape(-1, 2)
    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)
    return BBox(
        x=float(x_min),
        y=float(y_min),
        w=float(x_max - x_min),
        h=float(y_max - y_min),
    )


@dataclass
class OcrPageResult:
    lines: list[OcrLine]
    elapsed_ms: int
    engine_lang: str


def _normalise(result: Any, scale: float) -> list[OcrLine]:
    """Convert one PaddleOCR result into our `OcrLine` list.

    `scale` converts preprocessed-image coordinates back to rendered-page
    coordinates so boxes align with the image the browser displays.
    """
    texts = _field(result, "rec_texts", "rec_text") or []
    scores = _field(result, "rec_scores", "rec_score") or []
    polys = _field(result, "rec_polys", "dt_polys", "rec_boxes", "boxes")

    if polys is None:
        polys = []

    lines: list[OcrLine] = []
    for i, text in enumerate(texts):
        text = (text or "").strip()
        if not text:
            continue

        score = float(scores[i]) if i < len(scores) else 0.0
        if score < settings.ocr_text_score_thresh:
            continue

        if i < len(polys):
            raw = polys[i]
            arr = np.asarray(raw, dtype=float)
            if arr.size == 4 and arr.ndim == 1:
                # [x_min, y_min, x_max, y_max]
                bbox = BBox(
                    x=float(arr[0]),
                    y=float(arr[1]),
                    w=float(arr[2] - arr[0]),
                    h=float(arr[3] - arr[1]),
                )
                polygon = [
                    (float(arr[0]), float(arr[1])),
                    (float(arr[2]), float(arr[1])),
                    (float(arr[2]), float(arr[3])),
                    (float(arr[0]), float(arr[3])),
                ]
            else:
                bbox = _poly_to_bbox(arr)
                polygon = [(float(p[0]), float(p[1])) for p in arr.reshape(-1, 2)]
        else:
            bbox = BBox(x=0, y=0, w=0, h=0)
            polygon = []

        # Map back to rendered-page coordinates.
        if scale and scale != 1.0:
            bbox = BBox(
                x=bbox.x / scale, y=bbox.y / scale, w=bbox.w / scale, h=bbox.h / scale
            )
            polygon = [(px / scale, py / scale) for px, py in polygon]

        lines.append(
            OcrLine(
                id=uuid.uuid4().hex[:12],
                text=text,
                confidence=round(score, 4),
                bbox=bbox,
                polygon=polygon,
            )
        )

    return lines


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_ocr(
    image: np.ndarray,
    scale: float = 1.0,
    lang: str | None = None,
) -> OcrPageResult:
    """Run OCR on a preprocessed RGB image.

    `scale` is `PreprocessResult.scale` -- the factor from rendered-page to
    preprocessed pixels. Boxes are divided by it on the way out.
    """
    lang = lang or settings.ocr_lang
    engine = get_engine(lang=lang)

    # PaddleOCR reads ndarray input as BGR (it is cv2-native internally).
    # Our pipeline works in RGB, so convert here rather than leaving a
    # channel-swap bug that only shows up as slightly worse accuracy.
    if image.ndim == 3 and image.shape[2] == 3:
        feed = image[:, :, ::-1].copy()
    else:
        feed = image

    started = time.perf_counter()
    try:
        results = engine.predict(feed)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip() or repr(exc)
        raise OcrError(f"OCR inference failed: {msg}") from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if not results:
        return OcrPageResult(lines=[], elapsed_ms=elapsed_ms, engine_lang=lang)

    lines: list[OcrLine] = []
    for result in results:
        lines.extend(_normalise(result, scale))

    # Reading order: top-to-bottom, then left-to-right within a band.
    lines.sort(key=lambda ln: (round(ln.bbox.cy / 10), ln.bbox.cx))

    return OcrPageResult(lines=lines, elapsed_ms=elapsed_ms, engine_lang=lang)


def run_ocr_batch(
    images: list[np.ndarray],
    scales: list[float] | None = None,
    lang: str | None = None,
) -> list[OcrPageResult]:
    """Run OCR on a batch of preprocessed RGB images for maximum throughput."""
    if not images:
        return []
    if scales is None:
        scales = [1.0] * len(images)
    
    # Process sequentially or in batch feed depending on PaddleOCR capabilities
    out_results: list[OcrPageResult] = []
    for img, scale in zip(images, scales):
        out_results.append(run_ocr(img, scale=scale, lang=lang))
    return out_results

