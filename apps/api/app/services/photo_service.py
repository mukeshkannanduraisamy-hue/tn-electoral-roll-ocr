"""Image extraction — deliberately disabled.

A roll contains two kinds of image, and neither is extracted any more:

**Station imagery** — the map/photo sheet carries six captioned panels
(locality sketch, satellite view, two building photographs, a floor plan and
a route map). These were cropped from the rendered page and stored, with a
base64 copy in the database.

**Voter photographs** — each record cell reserves a box for one, but on the
SIR rolls published as *final* the box is printed with the words "Photo is /
available" and holds no photograph at all, so this corpus never yielded any.

Both were turned off in d521a23 to keep the database small: the base64 copies
dominated row size for something the review workflow does not read. The intact
implementations — panel detection by largest connected component, placeholder
detection, the caption vocabulary — are preserved in git at 59cd3be, which is
where to start from if station imagery is ever wanted back.

The functions survive as stubs rather than being deleted outright because
`pipeline` still calls `extract_station_photos` on a map sheet, and a stub
that returns nothing keeps that call site honest about what it gets.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np

from ..schemas.core import BBox, OcrLine, PhotoRef

logger = logging.getLogger(__name__)


def extract_station_photos(
    lines: Sequence[OcrLine],
    image: np.ndarray,
    page_id: str,
    directory: Path,
) -> list[PhotoRef]:
    """No station imagery is extracted. See the module docstring."""
    return []


def extract_voter_photo(
    cell: BBox,
    lines: Sequence[OcrLine],
    image: np.ndarray,
    page_id: str,
    record_id: str,
    directory: Path,
) -> PhotoRef | None:
    """No voter photograph is extracted. See the module docstring."""
    return None
