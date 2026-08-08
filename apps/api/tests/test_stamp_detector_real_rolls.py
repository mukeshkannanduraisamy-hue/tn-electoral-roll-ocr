"""The stamp detector measured against real rolls.

The synthetic fixtures in `test_stamp_detector.py` prove the shape logic is
self-consistent. Only real pages prove it is *right*, because only they carry the
actual stamp: hollow outline glyphs whose strokes are as dark as the printed text,
overlapping that text, on a page whose card borders and photo boxes must not be
mistaken for it.

The rolls are gitignored -- they hold live elector names, EPIC numbers and ages,
which should not enter the repo -- so these tests skip when the PDF is absent
rather than shipping a copy of the data.

Ground truth was read off page 4 of TAM-16 at 200 dpi by eye. Serials 13-27:
stamped are 13, 14, 15, 16, 18, 20, 21, 22, 25, 27; live are 17, 19, 23, 24, 26.
Every stamped card also carried a reason-code prefix and no live card did.

TAM-15 was initially assumed to be a clean control and is not: serials 20 and 26
on its page 4 are genuinely stamped. The detector found them when a visual pass
had missed them, which is why they are pinned here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.services.stamp_detector import find_stamp_marks  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
ROLLS = REPO_ROOT / "PDF" / "Penn PDF"
TAM_16 = ROLLS / "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-16-WI (1).pdf"
TAM_15 = ROLLS / "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-15-WI (1).pdf"

fitz = pytest.importorskip("fitz", reason="pymupdf needed to render the rolls")

STAMPED_ON_TAM16_PAGE4 = {13, 14, 15, 16, 18, 20, 21, 22, 25, 27}
LIVE_ON_TAM16_PAGE4 = {17, 19, 23, 24, 26}

# Cards sit in a 10x3 grid. These fractions bracket the cells closely enough for
# a fixture; production reads real cell boxes from the layout service.
_GRID_ROWS, _GRID_COLS = 10, 3
_TOP, _USABLE_HEIGHT = 0.055, 0.90
_LEFT, _USABLE_WIDTH = 0.02, 0.96


def _render(pdf: Path, page_index: int, dpi: int = 200) -> np.ndarray:
    import cv2

    doc = fitz.open(pdf)
    try:
        pixmap = doc[page_index].get_pixmap(dpi=dpi)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        if pixmap.n >= 3:
            return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return image[:, :, 0].copy()
    finally:
        doc.close()


def _cell(page: np.ndarray, serial: int) -> np.ndarray:
    row, col = (serial - 1) // _GRID_COLS, (serial - 1) % _GRID_COLS
    height, width = page.shape
    cell_h = height * _USABLE_HEIGHT / _GRID_ROWS
    cell_w = width * _USABLE_WIDTH / _GRID_COLS
    top = int(height * _TOP + cell_h * row)
    left = int(width * _LEFT + cell_w * col)
    return page[top:top + int(cell_h), left:left + int(cell_w)]


needs_tam16 = pytest.mark.skipif(
    not TAM_16.exists(), reason=f"roll not present: {TAM_16.name}"
)
needs_tam15 = pytest.mark.skipif(
    not TAM_15.exists(), reason=f"roll not present: {TAM_15.name}"
)


@needs_tam16
@pytest.mark.parametrize("serial", sorted(STAMPED_ON_TAM16_PAGE4))
def test_stamped_card_is_detected(serial):
    page = _render(TAM_16, 3)
    assert find_stamp_marks(_cell(page, serial)), f"missed the stamp on {serial}"


@needs_tam16
@pytest.mark.parametrize("serial", sorted(LIVE_ON_TAM16_PAGE4))
def test_live_card_is_not_flagged(serial):
    """A false positive here strikes a living elector off the roll."""
    page = _render(TAM_16, 3)
    marks = find_stamp_marks(_cell(page, serial))
    assert marks == [], f"flagged live elector {serial}: {marks}"


@needs_tam15
@pytest.mark.parametrize("serial", [20, 26])
def test_stamps_missed_by_eye_on_tam15_are_detected(serial):
    page = _render(TAM_15, 3)
    assert find_stamp_marks(_cell(page, serial)), f"missed the stamp on {serial}"


@needs_tam16
def test_detected_stamp_angles_match_the_observed_range():
    """Real stamps measured 55-68 degrees; a wild angle means a wrong component."""
    page = _render(TAM_16, 3)
    angles = [
        mark.angle
        for serial in sorted(STAMPED_ON_TAM16_PAGE4)
        for mark in find_stamp_marks(_cell(page, serial))
    ]
    assert angles, "no stamp components found at all"
    assert all(40.0 <= angle <= 80.0 for angle in angles), sorted(angles)
