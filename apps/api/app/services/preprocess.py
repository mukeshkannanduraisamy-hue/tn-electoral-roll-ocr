"""Image preprocessing applied before OCR.

Order matters and is deliberate:

    deskew -> denoise -> upscale -> CLAHE -> unsharp

* **deskew first** so every later filter works on axis-aligned strokes.
* **denoise before CLAHE.** Electoral-roll scans carry paper grain; running
  contrast enhancement first would amplify that grain into speckle that the
  detector then happily boxes as text.
* **upscale before CLAHE/unsharp** so the local-contrast and sharpening
  kernels operate at the resolution the recogniser will actually see.
* **unsharp last**, mild, to recover the edge definition that bicubic
  interpolation softens -- this is what makes Tamil ligatures separable.

Every stage is individually switchable via settings so the chain can be
tuned (or bypassed) per corpus without code changes.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_RGBA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def estimate_skew(gray: np.ndarray) -> float:
    """Estimate page skew in degrees via the dominant near-horizontal ruling.

    These forms are full of long printed rules, which are a far more stable
    skew signal than text baselines. Returns 0.0 when no confident estimate
    is available.
    """
    # Work at a reduced size -- skew is a global property and this is ~10x faster.
    scale = 1000.0 / max(gray.shape)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray

    edges = cv2.Canny(small, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 720,
        threshold=100,
        minLineLength=small.shape[1] // 4,
        maxLineGap=20,
    )
    if lines is None:
        return 0.0

    angles: list[float] = []
    for x1, y1, x2, y2 in lines[:, 0]:
        if x2 == x1:
            continue
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Keep near-horizontal lines only.
        if abs(angle) <= settings.deskew_max_angle:
            angles.append(angle)

    if len(angles) < 5:
        return 0.0

    angle = float(np.median(angles))
    if abs(angle) < 0.1 or abs(angle) > settings.deskew_max_angle:
        return 0.0
    return angle


def deskew(image: np.ndarray, angle: float | None = None) -> tuple[np.ndarray, float]:
    """Rotate the image to remove small skew. Returns (image, angle_applied)."""
    if not settings.deskew_enabled:
        return image, 0.0

    if angle is None:
        angle = estimate_skew(to_gray(image))
    if angle == 0.0:
        return image, 0.0

    h, w = image.shape[:2]
    centre = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    logger.debug("Deskewed by %.2f deg", angle)
    return rotated, angle


def denoise(gray: np.ndarray) -> np.ndarray:
    if not settings.denoise_enabled:
        return gray

    if settings.ocr_performance_mode in ("turbo", "balanced"):
        # Fast edge-preserving bilateral filter: ~30ms vs ~5200ms for fastNlMeansDenoising
        return cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)

    return cv2.fastNlMeansDenoising(
        gray,
        None,
        h=settings.denoise_strength,
        templateWindowSize=7,
        searchWindowSize=21,
    )


def upscale(image: np.ndarray, factor: float | None = None) -> np.ndarray:
    factor = settings.upscale_factor if factor is None else factor
    if factor <= 1.0:
        return image
    return cv2.resize(
        image,
        None,
        fx=factor,
        fy=factor,
        # INTER_CUBIC beats INTER_LANCZOS4 here: Lanczos ringing around the
        # thin printed rules confuses the morphological cell detector.
        interpolation=cv2.INTER_CUBIC,
    )


def apply_clahe(gray: np.ndarray) -> np.ndarray:
    if not settings.clahe_enabled:
        return gray
    clahe = cv2.createCLAHE(
        clipLimit=settings.clahe_clip_limit,
        tileGridSize=(settings.clahe_tile_grid, settings.clahe_tile_grid),
    )
    return clahe.apply(gray)


def unsharp(gray: np.ndarray) -> np.ndarray:
    """Mild unsharp mask: sharpened = (1+a)*img - a*blur(img)."""
    if not settings.unsharp_enabled:
        return gray
    radius = settings.unsharp_radius
    ksize = radius * 2 + 1
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    amount = settings.unsharp_amount
    return cv2.addWeighted(gray, 1.0 + amount, blurred, -amount, 0)


class PreprocessResult:
    """The OCR-ready image, the display image, and the geometry linking them.

    There are three coordinate spaces in play and conflating them is the
    easiest way to end up with bounding boxes that don't line up:

    ``raw``      what PyMuPDF rendered, before any correction.
    ``display``  raw after deskew, at the same resolution. **This is the
                 canonical space** -- it is what gets written to disk, shown
                 in the browser, and used for cell detection.
    ``ocr``      display after upscale/CLAHE/unsharp. What PaddleOCR sees.

    ``scale`` converts display -> ocr. Divide any coordinate PaddleOCR
    returns by it to land back in display space. Because cell detection also
    runs on ``display_image``, cells and text boxes share one space.
    """

    def __init__(
        self,
        image: np.ndarray,
        display_image: np.ndarray,
        scale: float,
        skew_angle: float,
        original_size: tuple[int, int],
    ) -> None:
        self.image = image
        self.display_image = display_image
        self.scale = scale
        self.skew_angle = skew_angle
        self.original_width, self.original_height = original_size

    def to_display(self, x: float, y: float) -> tuple[float, float]:
        return x / self.scale, y / self.scale


def is_blank_page(image: np.ndarray, threshold: float = 252.0) -> bool:
    """Detect if a page is effectively blank (white/empty).

    Pages from corrupt PDFs (e.g. Part 37) render as pure white. Skipping
    them early saves OCR time and prevents phantom records.
    """
    gray = to_gray(image)
    return float(gray.mean()) > threshold


def preprocess(image: np.ndarray, upscale_factor: float | None = None) -> PreprocessResult:
    """Run the full chain. Input RGB or gray; output is 3-channel RGB.

    PaddleOCR expects a 3-channel image, so the grayscale working copy is
    expanded back to RGB at the end.

    Includes adaptive contrast: very faded pages (mean_intensity > 240)
    get stronger CLAHE to recover text from low-contrast scans.
    """
    original_h, original_w = image.shape[:2]

    # Deskew defines the `display` space that everything downstream shares.
    rotated, angle = deskew(image)
    display = rotated if rotated.ndim == 3 else cv2.cvtColor(rotated, cv2.COLOR_GRAY2RGB)

    gray = to_gray(rotated)
    gray = denoise(gray)

    factor = settings.upscale_factor if upscale_factor is None else upscale_factor
    scaled = upscale(gray, factor)
    actual_scale = scaled.shape[1] / original_w if original_w else 1.0

    # Adaptive CLAHE: faded/low-contrast pages get stronger enhancement
    page_mean = float(scaled.mean())
    if settings.clahe_enabled and page_mean > 240:
        # Very faded page — boost CLAHE clip limit for better text recovery
        clahe_obj = cv2.createCLAHE(
            clipLimit=max(settings.clahe_clip_limit, 4.0),
            tileGridSize=(settings.clahe_tile_grid, settings.clahe_tile_grid),
        )
        enhanced = clahe_obj.apply(scaled)
        logger.debug("Adaptive CLAHE applied (page_mean=%.1f, clip=4.0)", page_mean)
    else:
        enhanced = apply_clahe(scaled)

    enhanced = unsharp(enhanced)

    rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)

    return PreprocessResult(
        image=rgb,
        display_image=display,
        scale=actual_scale,
        skew_angle=angle,
        original_size=(original_w, original_h),
    )


def binarize(gray: np.ndarray) -> np.ndarray:
    """Adaptive threshold used by the layout detector (not by OCR).

    Returns an inverted binary image (ink = 255) because every morphological
    operation downstream assumes foreground is white.
    """
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=25,
        C=10,
    )
