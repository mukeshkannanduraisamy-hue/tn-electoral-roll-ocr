"""Finding the DELETED stamp by shape rather than by reading it.

The stamp is rotated 55-68 degrees, so PaddleOCR never returns a line matching
"DELETED" -- it returns fragments (a stray `C` at 0.945 on serial 13, most
likely the outline of the `D`). Detection therefore cannot go through OCR.

Nor can it go through brightness. The stamp is drawn as hollow outline text
whose strokes are nearly as dark as the printed text; the intensity histogram
inside a stamped card is smooth, not bimodal, so no threshold splits them.

What separates them is shape: a stamp glyph is tall relative to the cell, hollow
(it fills little of its own bounding box), and not axis-aligned. That last
condition is what keeps the card border and the photo box -- the two large
hollow rectangles every card has -- from being mistaken for stamp ink.

The synthetic cards here reproduce those properties so the suite runs anywhere.
The real rolls are gitignored (they carry live elector names and EPIC numbers and
should not enter the repo), so the measurement against real pages is a separate
test that skips when the PDF is absent.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.services.stamp_detector import find_stamp_marks  # noqa: E402

CARD_H, CARD_W = 220, 560


def _blank_card() -> np.ndarray:
    """A card with the furniture every card has: a border and a photo box."""
    card = np.full((CARD_H, CARD_W), 255, dtype=np.uint8)
    cv2.rectangle(card, (3, 3), (CARD_W - 4, CARD_H - 4), 0, 2)        # border
    cv2.rectangle(card, (430, 40), (530, 180), 0, 2)                    # photo box
    cv2.rectangle(card, (18, 12), (180, 34), 0, 1)                      # serial box
    for i, y in enumerate((60, 85, 110, 135)):                          # field lines
        cv2.putText(card, "field value text", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, 0, 1, cv2.LINE_AA)
    return card


def _with_stamp(card: np.ndarray, angle: float = 62.0) -> np.ndarray:
    """Overlay large, thin-stroked, rotated DELETED text, as the rolls do."""
    layer = np.full((CARD_H * 2, CARD_W * 2), 255, dtype=np.uint8)
    cv2.putText(layer, "DELETED", (60, CARD_H),
                cv2.FONT_HERSHEY_SIMPLEX, 2.6, 0, 2, cv2.LINE_AA)
    centre = (layer.shape[1] / 2, layer.shape[0] / 2)
    rot = cv2.getRotationMatrix2D(centre, angle, 1.0)
    layer = cv2.warpAffine(layer, rot, (layer.shape[1], layer.shape[0]),
                           borderValue=255)
    ys, xs = np.where(layer < 128)
    if len(xs) == 0:
        raise AssertionError("fixture drew no stamp ink")
    crop = layer[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    crop = cv2.resize(crop, (int(CARD_W * 0.55), int(CARD_H * 0.92)))
    out = card.copy()
    region = out[8:8 + crop.shape[0], 20:20 + crop.shape[1]]
    np.minimum(region, crop, out=region)     # darkest-wins, so it overlaps text
    return out


def test_clean_card_has_no_stamp_marks():
    """Border, photo box and serial box must not read as stamp ink."""
    assert find_stamp_marks(_blank_card()) == []


def test_stamped_card_reports_marks():
    assert len(find_stamp_marks(_with_stamp(_blank_card()))) >= 1


def test_marks_carry_geometry_so_stamp_fragments_can_be_dropped():
    """OCR lines landing inside a mark are stamp ink, not field values."""
    marks = find_stamp_marks(_with_stamp(_blank_card()))
    assert marks, "expected at least one mark"
    for mark in marks:
        assert mark.w > 0 and mark.h > 0
        assert 0 <= mark.x < CARD_W and 0 <= mark.y < CARD_H


@pytest.mark.parametrize("angle", [55.0, 62.0, 68.0])
def test_stamp_found_across_the_observed_angle_range(angle):
    """Real stamps measured 55-68 degrees across one page."""
    assert len(find_stamp_marks(_with_stamp(_blank_card(), angle))) >= 1


def test_empty_cell_is_not_a_stamp():
    assert find_stamp_marks(np.full((CARD_H, CARD_W), 255, dtype=np.uint8)) == []


def test_photo_box_alone_is_not_a_stamp():
    """A tall hollow rectangle is furniture, however large."""
    card = np.full((CARD_H, CARD_W), 255, dtype=np.uint8)
    cv2.rectangle(card, (100, 10), (300, CARD_H - 10), 0, 2)
    assert find_stamp_marks(card) == []
