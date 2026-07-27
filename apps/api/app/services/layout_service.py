"""Layout analysis: find the record cells on a form page.

Strategy
--------
These forms are *printed rule* documents -- every record sits inside a drawn
rectangle. That is a much stronger signal than clustering text positions, so
we recover the grid from the ink itself:

1.  Binarise, then isolate long horizontal and vertical runs with
    morphological opening. Whatever survives is a printed rule, not text.
2.  Union those into a grid mask; the enclosed white regions are cell
    interiors. Connected components over the *inverse* mask gives candidate
    cells, filtered by area and aspect ratio.
3.  Score the result against the expected rows x cols grid. If the detected
    cells deviate too far (or we found the wrong number), fall back to a
    proportional grid and flag the page for review.

Both the detected and the fallback grid are always returned, so the UI can
offer a toggle and a human can pick whichever is right.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from ..config import settings
from ..schemas.core import BBox, GridSource, LayoutInfo
from .preprocess import binarize, to_gray

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule extraction
# ---------------------------------------------------------------------------


def _extract_rules(binary: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Isolate long horizontal and vertical printed rules."""
    h, w = binary.shape[:2]

    # Kernel lengths are a fraction of the page so this is resolution-agnostic.
    h_len = max(20, w // 30)
    v_len = max(20, h // 45)

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))

    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=1)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=1)

    # Bridge small breaks where a rule is interrupted by a scan artefact.
    horizontal = cv2.dilate(horizontal, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)))
    vertical = cv2.dilate(vertical, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 9)))

    return horizontal, vertical


def _find_body_region(grid_mask: np.ndarray) -> BBox:
    """Largest enclosing rectangle = the bordered body of the form.

    Falls back to the whole image when no convincing border is present.
    """
    h, w = grid_mask.shape[:2]
    full = BBox(x=0, y=0, w=float(w), h=float(h))

    contours, _ = cv2.findContours(grid_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return full

    best: BBox | None = None
    best_area = 0.0
    page_area = float(w * h)
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = float(cw * ch)
        # A body border covers most of the page but is not the entire canvas.
        if area / page_area < 0.30 or area / page_area > 0.99:
            continue
        if area > best_area:
            best_area = area
            best = BBox(x=float(x), y=float(y), w=float(cw), h=float(ch))

    return best or full


def _candidate_cells(grid_mask: np.ndarray, body: BBox) -> list[BBox]:
    """Connected components of the *inverse* grid = enclosed cell interiors."""
    h, w = grid_mask.shape[:2]
    page_area = float(w * h)

    inverse = cv2.bitwise_not(grid_mask)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(inverse, connectivity=4)

    cells: list[BBox] = []
    for i in range(1, count):  # 0 is background
        x, y, cw, ch, area = (
            stats[i, cv2.CC_STAT_LEFT],
            stats[i, cv2.CC_STAT_TOP],
            stats[i, cv2.CC_STAT_WIDTH],
            stats[i, cv2.CC_STAT_HEIGHT],
            stats[i, cv2.CC_STAT_AREA],
        )
        box_area = float(cw * ch)
        ratio = box_area / page_area
        if ratio < settings.min_cell_area_ratio or ratio > settings.max_cell_area_ratio:
            continue
        # Reject slivers: a record cell is a chunky rectangle.
        if cw < 40 or ch < 25:
            continue
        aspect = cw / ch if ch else 0
        if not 0.8 <= aspect <= 6.0:
            continue
        # The component must be reasonably solid within its bounding box;
        # this drops L-shaped background leakage between boxes.
        if area / box_area < 0.55:
            continue
        # Must sit inside the body.
        cx, cy = x + cw / 2, y + ch / 2
        if not body.contains_point(cx, cy):
            continue
        cells.append(BBox(x=float(x), y=float(y), w=float(cw), h=float(ch)))

    return cells


# ---------------------------------------------------------------------------
# Ordering and grid scoring
# ---------------------------------------------------------------------------


def sort_reading_order(cells: list[BBox], expected_cols: int) -> list[BBox]:
    """Row-major order: group into rows by vertical overlap, then sort by x."""
    if not cells:
        return []

    remaining = sorted(cells, key=lambda b: (b.y, b.x))
    rows: list[list[BBox]] = []

    for cell in remaining:
        placed = False
        for row in rows:
            # Same row if vertical centres are within half a cell height.
            ref = row[0]
            if abs(cell.cy - ref.cy) < max(ref.h, cell.h) * 0.5:
                row.append(cell)
                placed = True
                break
        if not placed:
            rows.append([cell])

    rows.sort(key=lambda r: min(c.y for c in r))
    ordered: list[BBox] = []
    for row in rows:
        row.sort(key=lambda c: c.x)
        ordered.extend(row)
    return ordered


def build_proportional_grid(body: BBox, rows: int, cols: int, inset: float = 0.0) -> list[BBox]:
    """Evenly divide the body into rows x cols cells."""
    cells: list[BBox] = []
    cw = body.w / cols
    ch = body.h / rows
    dx = cw * inset
    dy = ch * inset
    for r in range(rows):
        for c in range(cols):
            cells.append(
                BBox(
                    x=body.x + c * cw + dx,
                    y=body.y + r * ch + dy,
                    w=cw - 2 * dx,
                    h=ch - 2 * dy,
                )
            )
    return cells


def _cluster_1d(values: list[float], tolerance: float) -> list[list[float]]:
    """Group sorted scalars into clusters separated by more than `tolerance`."""
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for v in ordered[1:]:
        if v - clusters[-1][-1] <= tolerance:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def infer_grid_from_detected(
    detected: list[BBox], rows: int, cols: int, body: BBox
) -> list[BBox] | None:
    """Reconstruct a full grid from a partial detection.

    When cell detection finds most-but-not-all cells (a broken rule, a scan
    artefact), the detected cells still pin down the grid's true origin,
    pitch and cell size far better than dividing the page body evenly. This
    recovers the missing cells from that structure.

    Returns None when the detections don't resolve into the expected number
    of rows and columns, in which case the caller should use the plain
    proportional grid.
    """
    if len(detected) < max(4, (rows * cols) // 2):
        return None

    median_w = float(np.median([c.w for c in detected]))
    median_h = float(np.median([c.h for c in detected]))
    if median_w <= 0 or median_h <= 0:
        return None

    col_clusters = _cluster_1d([c.cx for c in detected], median_w * 0.5)
    row_clusters = _cluster_1d([c.cy for c in detected], median_h * 0.5)

    if len(col_clusters) != cols or len(row_clusters) != rows:
        return None

    col_centres = [float(np.median(c)) for c in col_clusters]
    row_centres = [float(np.median(r)) for r in row_clusters]

    cells: list[BBox] = []
    for cy in row_centres:
        for cx in col_centres:
            cells.append(
                BBox(
                    x=cx - median_w / 2,
                    y=cy - median_h / 2,
                    w=median_w,
                    h=median_h,
                )
            )
    return cells


def grid_deviation(detected: list[BBox], expected: list[BBox]) -> float:
    """Mean (1 - IoU) between detected cells and their expected positions.

    0.0 = perfect alignment, 1.0 = no overlap at all. Only meaningful when
    the two lists are the same length and both in reading order.
    """
    if not detected or len(detected) != len(expected):
        return 1.0
    ious = [d.iou(e) for d, e in zip(detected, expected)]
    return 1.0 - (sum(ious) / len(ious))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_layout(
    image: np.ndarray,
    rows: int | None = None,
    cols: int | None = None,
) -> LayoutInfo:
    """Detect record cells on a page image.

    `image` may be RGB or grayscale, in *rendered page* coordinates. The
    returned boxes are in that same coordinate space.
    """
    rows = rows or settings.expected_grid_rows
    cols = cols or settings.expected_grid_cols
    expected_count = rows * cols

    gray = to_gray(image)
    binary = binarize(gray)

    horizontal, vertical = _extract_rules(binary)
    grid_mask = cv2.bitwise_or(horizontal, vertical)

    body = _find_body_region(grid_mask)
    detected = sort_reading_order(_candidate_cells(grid_mask, body), cols)
    fallback = build_proportional_grid(body, rows, cols)

    # Score the detection.
    if len(detected) == expected_count:
        deviation = grid_deviation(detected, fallback)
        confidence = max(0.0, 1.0 - deviation)
    else:
        deviation = 1.0
        # Partial credit so "found 28 of 30" is distinguishable from "found 3".
        confidence = max(0.0, 0.5 * min(len(detected), expected_count) / expected_count)

    use_detected = (
        len(detected) == expected_count and deviation <= settings.grid_deviation_tolerance
    )

    if use_detected:
        source = GridSource.DETECTED
        cells = detected
        alternative = fallback
    else:
        # Before giving up on the ink, try to rebuild the full grid from the
        # cells we *did* find -- they locate the grid far more accurately
        # than dividing the page body into equal parts.
        inferred = infer_grid_from_detected(detected, rows, cols, body)
        if inferred:
            source = GridSource.DETECTED
            cells = inferred
            alternative = fallback
            deviation = grid_deviation(inferred, fallback)
            confidence = round(max(confidence, 0.75), 4)
            logger.info(
                "Reconstructed %dx%d grid from %d detected cells",
                rows, cols, len(detected),
            )
        else:
            source = GridSource.FALLBACK
            cells = fallback
            alternative = detected
            logger.info(
                "Cell detection fell back to proportional grid "
                "(found %d/%d cells, deviation %.3f > %.3f)",
                len(detected),
                expected_count,
                deviation,
                settings.grid_deviation_tolerance,
            )

    return LayoutInfo(
        source=source,
        confidence=round(confidence, 4),
        cells=cells,
        fallback_cells=alternative,
        rows=rows,
        cols=cols,
        deviation=round(deviation, 4),
    )


def assign_lines_to_cells(lines, cells: list[BBox]) -> dict[int, list]:
    """Map each OCR line to the cell containing its centroid.

    Lines that fall outside every cell get bucket -1 (page furniture:
    headers, footers, stray marks).
    """
    buckets: dict[int, list] = {-1: []}
    for i in range(len(cells)):
        buckets[i] = []

    for line in lines:
        cx, cy = line.bbox.cx, line.bbox.cy
        target = -1
        for i, cell in enumerate(cells):
            if cell.contains_point(cx, cy):
                target = i
                break
        else:
            # No containment -- fall back to nearest cell if it's very close,
            # which rescues lines whose box slightly overhangs a rule.
            best_i, best_d = -1, float("inf")
            for i, cell in enumerate(cells):
                dx = max(cell.x - cx, 0, cx - cell.x2)
                dy = max(cell.y - cy, 0, cy - cell.y2)
                d = (dx * dx + dy * dy) ** 0.5
                if d < best_d:
                    best_i, best_d = i, d
            if best_i >= 0 and best_d < 15:
                target = best_i

        line.cell_index = target if target >= 0 else None
        buckets[target].append(line)

    return buckets
