"""End-to-end page processing: PDF -> structured, validated records.

This is the single place the stages are composed, so the API layer, the CLI
and the tests all exercise exactly the same path.

    render -> preprocess -> OCR -> detect template -> detect cells
           -> parse -> validate -> Page
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import cv2

from ..config import settings
from ..schemas.core import (
    GridSource,
    Issue,
    IssueCode,
    IssueSeverity,
    LayoutInfo,
    Page,
    PageStatus,
)
from ..templates import registry
from . import layout_service, ocr_service, pdf_service, preprocess

logger = logging.getLogger(__name__)


def process_page(
    pdf_path: str | Path,
    page_number: int,
    file_id: str,
    template_id: str = "auto",
    lang: str | None = None,
    save_image: bool = True,
    page_id: str | None = None,
) -> Page:
    """Process one page of one PDF into a fully populated `Page`."""
    pdf_path = Path(pdf_path)
    page_id = page_id or uuid.uuid4().hex[:12]

    page = Page(
        id=page_id,
        file_id=file_id,
        page_number=page_number,
        status=PageStatus.PROCESSING,
    )

    # ---------------------------------------------------------- 1. render
    try:
        rendered = pdf_service.render_page(pdf_path, page_number)
    except pdf_service.PdfError as exc:
        page.status = PageStatus.ERROR
        page.error = str(exc)
        return page

    # ------------------------------------------------------ 2. preprocess
    pre = preprocess.preprocess(rendered.image)
    display = pre.display_image
    page.width = display.shape[1]
    page.height = display.shape[0]

    if save_image:
        out_path = settings.pages_dir / f"{page_id}.png"
        # cv2 writes BGR; our arrays are RGB.
        cv2.imwrite(str(out_path), display[:, :, ::-1])
        page.image_path = out_path.name

    # ------------------------------------------------------------- 3. OCR
    try:
        ocr_result = ocr_service.run_ocr(pre.image, scale=pre.scale, lang=lang)
    except ocr_service.OcrError as exc:
        page.status = PageStatus.ERROR
        page.error = str(exc)
        return page

    page.lines = ocr_result.lines
    page.ocr_ms = ocr_result.elapsed_ms

    if not page.lines:
        page.issues.append(
            Issue(
                code=IssueCode.OCR_EMPTY,
                severity=IssueSeverity.ERROR,
                message="No text was recognised on this page",
            )
        )

    # ------------------------------------------------- 4. choose template
    page_size = (page.width, page.height)
    if template_id in ("auto", "", None):
        template, confidence = registry.detect(page.lines, page_size)
    else:
        try:
            template = registry.get(template_id)
            confidence = 1.0
        except KeyError:
            template, confidence = registry.detect(page.lines, page_size)

    page.template_id = template.id
    page.template_confidence = confidence

    # --------------------------------------------------- 5. detect layout
    grid = template.expected_grid()
    if grid:
        rows, cols = grid
        # Cell detection runs on `display` -- the same space the OCR boxes
        # were mapped back into -- so cells and text share one geometry.
        layout = layout_service.detect_layout(display, rows=rows, cols=cols)
        if layout.source == GridSource.FALLBACK.value:
            page.issues.append(
                Issue(
                    code=IssueCode.GRID_FALLBACK_USED,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Cell borders could not be detected reliably "
                        f"(deviation {layout.deviation:.2f}); using a proportional "
                        f"{rows}x{cols} grid. Check the field alignment."
                    ),
                )
            )
    else:
        layout = LayoutInfo(source=GridSource.NONE, confidence=0.0, cells=[])

    page.layout = layout

    # ------------------------------------------------------------ 6. parse
    try:
        records = template.parse(page.lines, layout, page.id, page_size)
    except Exception as exc:  # noqa: BLE001 - never let one page kill a batch
        logger.exception("Template %s failed to parse page %s", template.id, page_id)
        page.status = PageStatus.ERROR
        page.error = f"Parsing failed: {exc}"
        return page

    # --------------------------------------------------------- 7. validate
    try:
        template.validate(records)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Template %s failed to validate page %s", template.id, page_id)
        page.issues.append(
            Issue(
                code=IssueCode.UNPARSED_TEXT,
                severity=IssueSeverity.WARNING,
                message=f"Validation error: {exc}",
            )
        )

    page.records = records

    if grid:
        expected = grid[0] * grid[1]
        if len(records) > expected:
            page.issues.append(
                Issue(
                    code=IssueCode.CELL_COUNT_MISMATCH,
                    severity=IssueSeverity.WARNING,
                    message=f"Produced {len(records)} records but the grid holds "
                            f"only {expected} -- cell detection may have split a cell",
                )
            )
        elif len(records) < expected:
            # Normal, not a fault: the last page of a section is part-full.
            page.issues.append(
                Issue(
                    code=IssueCode.CELL_COUNT_MISMATCH,
                    severity=IssueSeverity.INFO,
                    message=f"Partial page: {len(records)} of {expected} record "
                            f"slots are populated",
                )
            )

    # ------------------------------------------------ 8. header and footer
    page.header_text, page.footer_text = _split_furniture(page, layout)

    page.status = PageStatus.COMPLETED
    return page


def _split_furniture(page: Page, layout: LayoutInfo) -> tuple[str, str]:
    """Text above / below the record grid = page header / footer."""
    if not layout.cells:
        return "", ""

    body_top = min(c.y for c in layout.cells)
    body_bottom = max(c.y + c.h for c in layout.cells)

    header: list[str] = []
    footer: list[str] = []
    for line in page.lines:
        if line.cell_index is not None:
            continue
        if line.bbox.cy < body_top:
            header.append(line.text)
        elif line.bbox.cy > body_bottom:
            footer.append(line.text)

    return " ".join(header).strip(), " ".join(footer).strip()


def process_pdf(
    pdf_path: str | Path,
    file_id: str,
    template_id: str = "auto",
    lang: str | None = None,
    save_image: bool = True,
):
    """Process every page of a PDF, yielding pages as they complete."""
    info = pdf_service.inspect(pdf_path)
    for n in range(1, info.page_count + 1):
        yield process_page(
            pdf_path,
            n,
            file_id,
            template_id=template_id,
            lang=lang,
            save_image=save_image,
        )
