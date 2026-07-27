"""PDF inspection and rasterisation (PyMuPDF).

Design note -- why we don't just render everything at 300 DPI
-------------------------------------------------------------
A large share of real-world scanned PDFs (the electoral-roll corpus included)
are a *single full-page raster image* wrapped in a PDF container. Rendering
those at an arbitrary 300 DPI resamples an image that has no extra detail to
give, and the later upscale then resamples a second time. Two lossy
interpolations stacked on top of each other visibly smears small glyphs.

So: when a page is dominated by one image, we render at that image's native
resolution -- effectively handing back the original pixels untouched -- and
leave all scaling to the single, controlled upscale in `preprocess.py`.
Vector/text pages have no native resolution and fall back to the configured
DPI as usual.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)

POINTS_PER_INCH = 72.0


class PdfError(Exception):
    """Raised for a PDF we cannot open or render (corrupt, encrypted, ...)."""


@dataclass(frozen=True)
class PdfInfo:
    page_count: int
    is_encrypted: bool
    producer: str
    page_sizes: list[tuple[float, float]]
    """Per page (width, height) in points."""


@dataclass(frozen=True)
class RenderedPage:
    image: np.ndarray
    """RGB uint8, shape (H, W, 3)."""
    width: int
    height: int
    dpi: float
    native: bool
    """True if rendered at the page's own image resolution (no resampling)."""


def inspect(path: str | Path) -> PdfInfo:
    """Read structural metadata without rendering anything."""
    path = Path(path)
    if not path.exists():
        raise PdfError(f"File not found: {path}")
    try:
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise PdfError("PDF is password-protected")
            sizes = [(p.rect.width, p.rect.height) for p in doc]
            return PdfInfo(
                page_count=doc.page_count,
                is_encrypted=doc.is_encrypted,
                producer=(doc.metadata or {}).get("producer") or "",
                page_sizes=sizes,
            )
    except PdfError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any PyMuPDF failure uniformly
        raise PdfError(f"Cannot read PDF: {exc}") from exc


def _estimate_native_dpi(page: fitz.Page) -> float | None:
    """DPI of the dominant image on the page, or None if there isn't one.

    "Dominant" means a single image whose placed area covers >=80% of the
    page. That is the signature of a scanned/rasterised page.
    """
    try:
        images = page.get_images(full=True)
    except Exception:  # noqa: BLE001
        return None
    if not images:
        return None

    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return None

    best: tuple[float, float] | None = None  # (coverage, dpi)
    for img in images:
        xref = img[0]
        pixel_w = img[2]
        if not pixel_w:
            continue
        try:
            rects = page.get_image_rects(xref)
        except Exception:  # noqa: BLE001
            continue
        for rect in rects:
            coverage = (rect.width * rect.height) / page_area
            if rect.width <= 0:
                continue
            dpi = pixel_w / (rect.width / POINTS_PER_INCH)
            if best is None or coverage > best[0]:
                best = (coverage, dpi)

    if best and best[0] >= 0.80:
        return best[1]
    return None


def render_page(path: str | Path, page_number: int) -> RenderedPage:
    """Rasterise a single page (1-based) to an RGB numpy array."""
    path = Path(path)
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"Cannot open PDF: {exc}") from exc

    with doc:
        if doc.needs_pass:
            raise PdfError("PDF is password-protected")
        if not 1 <= page_number <= doc.page_count:
            raise PdfError(
                f"Page {page_number} out of range (document has {doc.page_count})"
            )

        page = doc[page_number - 1]
        native_dpi = _estimate_native_dpi(page)

        if native_dpi and native_dpi > 0:
            dpi = native_dpi
            native = True
        else:
            dpi = float(settings.render_dpi)
            native = False

        # Clamp so a pathological page can't exhaust memory.
        width_in = page.rect.width / POINTS_PER_INCH
        height_in = page.rect.height / POINTS_PER_INCH
        projected = (width_in * dpi) * (height_in * dpi)
        if projected > settings.max_page_pixels:
            scale = (settings.max_page_pixels / projected) ** 0.5
            dpi *= scale
            native = False
            logger.warning(
                "Page %s of %s clamped to %.0f DPI (%.1fMpx budget)",
                page_number,
                path.name,
                dpi,
                settings.max_page_pixels / 1e6,
            )

        zoom = dpi / POINTS_PER_INCH
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        except Exception as exc:  # noqa: BLE001
            raise PdfError(f"Failed to render page {page_number}: {exc}") from exc

        arr = np.frombuffer(pix.samples, dtype=np.uint8)
        arr = arr.reshape(pix.height, pix.width, pix.n)
        if pix.n == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif pix.n == 4:
            arr = arr[:, :, :3]
        # Copy: `pix.samples` is a view over memory owned by the Pixmap.
        arr = np.ascontiguousarray(arr)

        return RenderedPage(
            image=arr,
            width=pix.width,
            height=pix.height,
            dpi=dpi,
            native=native,
        )


def render_all(path: str | Path):
    """Yield every page in order. Generator so large documents stay streamable."""
    info = inspect(path)
    for n in range(1, info.page_count + 1):
        yield n, render_page(path, n)
