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
    """Find and crop whichever of the six standard station panels are present."""
    if not lines:
        return []

    photos: list[PhotoRef] = []
    for index, (_row_y, items) in enumerate(rows):
        # A panel runs from below its caption to just above the next row's.
        top = max(b.y2 for _t, b in items) + _CAPTION_CLEARANCE
        bottom = (
            rows[index + 1][0] - _CAPTION_CLEARANCE * 1.5
            if index + 1 < len(rows)
            else height * 0.95
        )
        if bottom - top < _MIN_PANEL_PX:
            continue

        for photo_type, bbox in items:
            left, right = (
                (0.02 * width, 0.50 * width)
                if bbox.cx < width / 2
                else (0.50 * width, 0.98 * width)
            )
            window = image[int(top):int(bottom), int(left):int(right)]
            if window.size == 0:
                continue

            found = _largest_panel(window)
            if found is None:
                logger.debug("No panel found for %s on page %s", photo_type, page_id)
                continue

            x, y, w, h = found
            crop = window[y:y + h, x:x + w]
            name, cw, ch = _write(
                crop, directory, f"{page_id}_{photo_type}_{uuid.uuid4().hex[:6]}.png"
            )
            photos.append(
                PhotoRef(
                    photo_type=photo_type,
                    file_path=name,
                    width=cw,
                    height=ch,
                    page_id=page_id,
                )
            )

    return photos


def _region_holds_placeholder(lines: Sequence[OcrLine], region: BBox) -> bool:
    for line in lines:
        if not region.contains_point(line.bbox.cx, line.bbox.cy):
            continue
        lowered = line.text.lower()
        if any(word in lowered for word in PLACEHOLDER_TEXT):
            return True
    return False


def voter_photo_region(cell: BBox) -> BBox:
    """Where the photograph sits inside a record cell.

    The right-hand quarter, below the serial/EPIC line. Fractions rather
    than pixels so this holds at any render resolution.
    """
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
    """Crop one voter's photograph, or None when the box is a placeholder.

    Returning None for a placeholder is the whole point: a final SIR roll
    prints "Photo is available" in every box, and storing 30 crops of that
    sentence per page would fill the photo table with pictures of text and
    put a meaningless thumbnail on every voter profile.
    """
    region = voter_photo_region(cell)
    if _region_holds_placeholder(lines, region):
        return None

    x0, y0 = max(int(region.x), 0), max(int(region.y), 0)
    x1 = min(int(region.x2), image.shape[1])
    y1 = min(int(region.y2), image.shape[0])
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None

    window = image[y0:y1, x0:x1]
    found = _largest_panel(window)
    if found is None:
        return None

    x, y, w, h = found
    name, cw, ch, b64 = _write(
        window[y:y + h, x:x + w],
        directory,
        f"{page_id}_{record_id}_photo.png",
    )
    return PhotoRef(
        photo_type="voter_crop",
        file_path=name,
        image_data=b64,
        width=cw,
        height=ch,
        page_id=page_id,
        record_id=record_id,
    )
