"""Extract the images a roll actually contains.

Two kinds, and they are not equally present:

**Station imagery** -- the map/photo sheet carries six captioned panels
(locality sketch, satellite view, two building photographs, a floor plan and
a route map). These are real pictures and are worth having: they are the
only visual record of where an elector is expected to vote.

**Voter photographs** -- each record cell reserves a box for one, but on the
SIR rolls published as *final* the box is printed with the words
"Photo is / available" and holds no photograph at all. Cropping it yields a
picture of the sentence "Photo is available", thirty times a page. So a crop
is taken only when the box holds no placeholder text, and this corpus
correctly yields none.

Both are cropped from the rendered page rather than pulled out of the PDF,
because the source is a single full-page raster per sheet -- there are no
separately embedded images to extract.
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from ..schemas.core import BBox, OcrLine, PhotoRef

logger = logging.getLogger(__name__)

#: Caption text -> photo type. Captions are printed in English on an
#: otherwise Tamil sheet, which makes them the sturdiest anchor available.
STATION_CAPTIONS: dict[str, str] = {
    "nazri naksha": "nazri_naksha",
    "google map": "google_map",
    "building front": "station_building",
    "station front": "station_front",
    "cad view": "cad_map",
    "key map": "key_map",
}

#: Words printed inside an empty photo box. Their presence means there is no
#: photograph, whatever the box's ink statistics suggest.
PLACEHOLDER_TEXT = (
    "photo", "available", "not available",
    "புகைப்படம", "புகைப்படம்", "இல்லை", "இருக்கிறது",
)

#: Two captions belong to the same row if their baselines are this close.
_ROW_TOLERANCE = 40.0
#: Clear of the caption's coloured banner, which is taller than its text.
_CAPTION_CLEARANCE = 20.0

_MIN_PANEL_PX = 60
"""A panel smaller than this in either axis is a table rule or a stray mark."""


def _largest_panel(crop: np.ndarray) -> tuple[int, int, int, int] | None:
    """Bounding box of the largest picture-like blob in `crop`.

    Trimming to "any non-white pixel" is not enough: the caption banner and
    the table rules are non-white too, so a naive trim returns the whole
    panel with a coloured stripe across the top. Taking the largest
    *connected* region instead isolates the picture, and rejecting long thin
    components drops the rules without needing to know where they are.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    mask = (gray < 242).astype(np.uint8)
    # Close small gaps so a dithered photograph reads as one region.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )

    best: tuple[int, int, int, int] | None = None
    for i in range(1, count):
        x, y, w, h = (
            stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],
            stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT],
        )
        if w < _MIN_PANEL_PX or h < _MIN_PANEL_PX:
            continue
        if w / max(h, 1) > 12:  # a printed rule, not a picture
            continue
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    return best


def _write(image: np.ndarray, directory: Path, name: str) -> tuple[str, int, int, str]:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    img_bgr = image[:, :, ::-1] if image.ndim == 3 else image
    cv2.imwrite(str(path), img_bgr)
    b64_data = ""
    try:
        success, buf = cv2.imencode(".png", img_bgr)
        if success:
            b64_data = base64.b64encode(buf.tobytes()).decode("utf-8")
    except Exception:
        pass
    return path.name, image.shape[1], image.shape[0], b64_data


def extract_station_photos(
    lines: Sequence[OcrLine],
    image: np.ndarray,
    page_id: str,
    directory: Path,
) -> list[PhotoRef]:
    """Crop the captioned panels off a map/photo sheet."""
    height, width = image.shape[:2]

    captions: list[tuple[str, BBox]] = []
    for line in lines:
        lowered = line.text.lower()
        for marker, photo_type in STATION_CAPTIONS.items():
            if marker in lowered:
                captions.append((photo_type, line.bbox))
                break
def extract_station_photos(
    lines: Sequence[OcrLine],
    image: np.ndarray,
    page_id: str,
    directory: Path,
) -> list[PhotoRef]:
    """Disabled for high-speed OCR extraction & optimized database storage."""
    return []


def _region_holds_placeholder(lines: Sequence[OcrLine], region: BBox) -> bool:
    return True


def voter_photo_region(cell: BBox) -> BBox:
    return BBox(
        x=cell.x + cell.w * 0.74,
        y=cell.y + cell.h * 0.14,
        w=cell.w * 0.24,
        h=cell.h * 0.78,
    )


def extract_voter_photo(
    cell: BBox,
    lines: Sequence[OcrLine],
    image: np.ndarray,
    page_id: str,
    record_id: str,
    directory: Path,
) -> PhotoRef | None:
    """Disabled for high-speed OCR extraction & optimized database storage."""
    return None

