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

    The vertical extent is taken from the ink as-is and never stretched to
    fill the sheet. A part file routinely ends on a part-full page -- the
    supplement sheet on the reference document carries 9 records in 3 rows
    across the top 28% of the paper -- and padding that out to a full-height
    body puts the first row of cells *above* the body, where its text is
    dropped on the floor. A short grid is a short grid.
    """
    h, w = grid_mask.shape[:2]
    default_body = BBox(x=float(w * 0.03), y=float(h * 0.08), w=float(w * 0.94), h=float(h * 0.87))

    pts = cv2.findNonZero(grid_mask)
    if pts is None:
        return default_body

    x, y, bw, bh = cv2.boundingRect(pts)
    # Width is what identifies the printed frame: every grid spans the sheet.
    # Height is measured, not assumed.
    if bw >= w * 0.60 and bh >= h * 0.05:
        return BBox(x=float(x), y=float(y), w=float(bw), h=float(bh))

    return default_body




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


def group_rows(cells: list[BBox]) -> list[list[BBox]]:
    """Cluster cells into rows by vertical overlap, top to bottom."""
    rows: list[list[BBox]] = []
    for cell in sorted(cells, key=lambda b: (b.y, b.x)):
        for row in rows:
            ref = row[0]
            if abs(cell.cy - ref.cy) < max(ref.h, cell.h) * 0.5:
                row.append(cell)
                break
        else:
            rows.append([cell])
    rows.sort(key=lambda r: min(c.y for c in r))
    return rows


def infer_row_count(detected: list[BBox], body: BBox, nominal_rows: int) -> int | None:
    """How many record rows this page actually holds.

    `nominal_rows` is what the template expects of a *full* page (10 here),
    but the last page of a roll and every supplement sheet are part-full. The
    row pitch is constant across the corpus -- it is the printed cell height
    -- so measuring the pitch from whatever cells were detected and dividing
    the body by it recovers the true row count without assuming fullness.

    Returns None when there is too little ink to measure honestly.
    """
    if not detected:
        return None

    rows = group_rows(detected)
    tops = [min(c.y for c in row) for row in rows]

    if len(tops) >= 2:
        pitch = float(np.median(np.diff(tops)))
    else:
        # One row is enough to measure a cell, and the gap between printed
        # cells is small relative to the cell itself.
        pitch = float(np.median([c.h for c in detected])) * 1.08

    if pitch <= 0:
        return None

    count = int(round(body.h / pitch))
    # Never claim more rows than the template's full page, and never zero.
    return max(1, min(nominal_rows, count))





def fit_deviation(detected: list[BBox], grid: list[BBox]) -> float:
    """How badly a reconstructed grid misses the cells actually found.

    Unlike `grid_deviation` this does not require the two lists to be the
    same length, which is the whole point on a part-full page: we have (say)
    6 detected cells and a reconstructed 3x3 grid. Each detected cell is
    scored against its best match in the grid, so the result answers "does
    the lattice we built actually sit on the printed rules?".
    """
    if not detected or not grid:
        return 1.0
    best = [max(d.iou(g) for g in grid) for d in detected]
    return 1.0 - (sum(best) / len(best))


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

    actual_rows = rows

    if use_detected:
        source = GridSource.DETECTED
        cells = detected
        alternative = fallback
    else:
        # Before giving up on the ink, rebuild the grid from the cells we
        # *did* find. They locate the grid -- and, critically, tell us how
        # many rows it has -- far better than assuming a full page.
        inferred_rows = (
            infer_row_count(detected, body, rows)
            if len(detected) >= max(2, cols)
            else None
        )
        if inferred_rows:
            actual_rows = inferred_rows
            cells = build_proportional_grid(body, actual_rows, cols)
            source = GridSource.DETECTED
            alternative = fallback
            # Score the lattice against the ink it was built from, not
            # against the nominal full-page grid -- on a part-full page the
            # latter compares two different shapes and means nothing.
            deviation = fit_deviation(detected, cells)
            confidence = round(max(confidence, 1.0 - deviation), 4)
            logger.info(
                "Reconstructed %dx%d grid from %d detected cells "
                "(template expects %d rows)",
                actual_rows, cols, len(detected), rows,
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
        rows=actual_rows,
        cols=cols,
        deviation=round(deviation, 4),
    )


def assign_lines_to_cells(lines: list, cells: list[BBox], rows: int = 10, cols: int = 3) -> dict[int, list]:
    """Map each OCR line to the cell containing it.

    When `cells` forms a structured grid (e.g. 10x3), lines are assigned by
    row and column band boundaries to guarantee no lines spill over to adjacent
    cells above or below.
    """
    buckets: dict[int, list] = {-1: []}
    for i in range(len(cells)):
        buckets[i] = []

    if not cells or not lines:
        return buckets

    # Structured grid mapping using median step smoothing
    if len(cells) == rows * cols:
        row_centers = [
            float(np.mean([cells[r * cols + c].cy for c in range(cols)]))
            for r in range(rows)
        ]
        row_steps = [row_centers[r + 1] - row_centers[r] for r in range(rows - 1)]
        # With a single row there is no pitch to measure, so the band has to
        # come from the cell itself. A fixed guess would be narrower than a
        # real cell and would drop the lines nearest its top and bottom
        # edges -- which on a one-row supplement sheet is the serial number
        # and the age/gender line.
        row_step = (
            float(np.median(row_steps))
            if row_steps
            else float(np.median([c.h for c in cells]))
        )
        first_row_top = row_centers[0] - row_step * 0.5
        row_bounds = [first_row_top + r * row_step for r in range(rows + 1)]

        col_centers = [
            float(np.mean([cells[r * cols + c].cx for r in range(rows)]))
            for c in range(cols)
        ]
        col_steps = [col_centers[c + 1] - col_centers[c] for c in range(cols - 1)]
        col_step = (
            float(np.median(col_steps))
            if col_steps
            else float(np.median([c.w for c in cells]))
        )
        first_col_left = col_centers[0] - col_step * 0.5
        col_bounds = [first_col_left + c * col_step for c in range(cols + 1)]

        for line in lines:
            cx, cy = line.bbox.cx, line.bbox.cy
            target_r = -1
            for r in range(rows):
                if row_bounds[r] <= cy < row_bounds[r + 1]:
                    target_r = r
                    break
            target_c = -1
            for c in range(cols):
                if col_bounds[c] <= cx < col_bounds[c + 1]:
                    target_c = c
                    break

            if target_r >= 0 and target_c >= 0:
                idx = target_r * cols + target_c
                line.cell_index = idx
                buckets[idx].append(line)
            else:
                line.cell_index = None
                buckets[-1].append(line)

        return buckets




    # Fallback point-in-polygon mapping for irregular layouts
    for line in lines:
        cx, cy = line.bbox.cx, line.bbox.cy
        target = -1
        for i, cell in enumerate(cells):
            if cell.contains_point(cx, cy):
                target = i
                break
        else:
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

