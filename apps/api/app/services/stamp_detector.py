"""Locating the DELETED stamp on a struck-off elector's card.

A Special Intensive Revision roll stamps removed electors with a large diagonal
`DELETED` watermark. Two obvious ways to find it both fail:

* **Reading it.** The stamp sits at 55-68 degrees and PaddleOCR never returns a
  line matching "DELETED". It does return fragments -- a stray `C` at 0.945
  confidence on one card, most likely the outline of the `D` -- which is worse
  than silence, because a fragment can be mistaken for a field value.
* **Thresholding it.** The stamp is hollow outline text whose strokes are nearly
  as dark as the printed text. The intensity histogram inside a stamped card is
  smooth, not bimodal.

So it is found by shape. A stamp glyph is tall relative to the cell, hollow, and
not axis-aligned -- the last condition being what separates it from the card
border and the photo box, the two large hollow rectangles every card carries.

Boxes are returned rather than a boolean for two reasons: an OCR line whose box
falls inside a mark is stamp ink and can be dropped before parsing, and the
recovery pass needs to know which pixels to subtract before re-reading a cell.

This module knows nothing about electoral rolls. It takes an image and returns
geometry; the template layer decides what that means.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Ink is anything darker than this. Deliberately generous: the stamp and the text
# are both near-black, and separating them is the shape test's job, not this one.
_INK_MAX = 175

# A stamp glyph spans a real fraction of the cell. Field text never does.
_MIN_HEIGHT_FRACTION = 0.20

# Fraction of its own bounding box a component fills. Outline glyphs come in low;
# solid blobs and filled text come in high.
_MAX_FILL = 0.34

# How closely a component's area must match its rotated box before it counts as a
# rectangle, and how near an axis it must sit. Together these drop furniture.
_RECT_AREA_TOLERANCE = 0.25
_AXIS_DEGREES = 6.0

_MIN_SIDE_PX = 4


@dataclass(frozen=True)
class StampMark:
    """One glyph-sized piece of stamp ink, in cell-local pixel coordinates."""

    x: int
    y: int
    w: int
    h: int
    angle: float
    """Orientation of the component's minimum-area box, folded into 0-90."""


def _is_axis_aligned_rectangle(
    box_area: int, rotated_area: float, angle: float
) -> bool:
    """True for the card border and the photo box.

    A rectangle drawn square to the page fills its rotated box as completely as
    it fills its upright one, and its minimum-area box sits on an axis. A rotated
    glyph satisfies neither.
    """
    if box_area <= 0:
        return False
    if abs(box_area - rotated_area) / box_area >= _RECT_AREA_TOLERANCE:
        return False
    return angle < _AXIS_DEGREES or angle > 90.0 - _AXIS_DEGREES


def find_stamp_marks(cell: np.ndarray) -> list[StampMark]:
    """Stamp components in `cell`, empty when the cell is unstamped.

    `cell` is a single-channel crop of one elector's card.
    """
    if cell.ndim != 2:
        cell = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)

    ink = (cell < _INK_MAX).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)

    min_height = cell.shape[0] * _MIN_HEIGHT_FRACTION
    marks: list[StampMark] = []

    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if h < min_height or w < _MIN_SIDE_PX or h < _MIN_SIDE_PX:
            continue
        if area / (w * h) >= _MAX_FILL:
            continue

        contours, _ = cv2.findContours(
            (labels[y:y + h, x:x + w] == index).astype(np.uint8),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            continue

        (_, _), (rot_w, rot_h), raw_angle = cv2.minAreaRect(contours[0])
        if rot_w < 1 or rot_h < 1:
            continue

        angle = raw_angle % 90
        if _is_axis_aligned_rectangle(w * h, rot_w * rot_h, angle):
            continue

        marks.append(StampMark(int(x), int(y), int(w), int(h), float(angle)))

    return marks


def covers(mark: StampMark, box: tuple[float, float, float, float]) -> bool:
    """Whether `box` (x, y, w, h) sits inside `mark`.

    Used to discard OCR lines that recognised stamp ink as text.
    """
    bx, by, bw, bh = box
    return (
        bx >= mark.x
        and by >= mark.y
        and bx + bw <= mark.x + mark.w
        and by + bh <= mark.y + mark.h
    )
