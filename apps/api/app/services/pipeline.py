"""End-to-end page processing: PDF -> structured, validated records.

This is the single place the stages are composed, so the API layer, the CLI
and the tests all exercise exactly the same path.

    render -> preprocess -> OCR -> classify page -> detect template
           -> detect cells -> parse -> validate -> Page

    Pages that hold no voter records stop after classification.
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
from . import (
    layout_service,
    ocr_service,
    page_classifier,
    pdf_service,
    photo_service,
    preprocess,
)

logger = logging.getLogger(__name__)


def process_page(
    pdf_path: str | Path,
    page_number: int,
    file_id: str,
    template_id: str = "auto",
    lang: str | None = None,
    save_image: bool = False,
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
        import threading
        out_path = settings.pages_dir / f"{page_id}.png"
        page.image_path = out_path.name
        # cv2 writes BGR; our arrays are RGB. Defer disk I/O to a background thread
        threading.Thread(
            target=cv2.imwrite,
            args=(str(out_path), display[:, :, ::-1]),
            daemon=True
        ).start()

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

    # ------------------------------------------------ 4. classify the page
    # A roll PDF is not a stack of voter grids: the reference document is a
    # cover, a signature sheet, a map sheet, six grids, a supplement, a
    # summary and a legend. Running the record parser over the nine-tenths
    # of a page that is prose or a photo produces confident nonsense -- 139
    # phantom records out of 331 on that document -- so pages that hold no
    # voters are classified, kept for their text and images, and skipped.
    classification = page_classifier.classify_page(
        page.lines, None, page.width, page.height
    )
    page.page_type = classification.page_type.value
    page.classification_confidence = classification.confidence

    if classification.page_type not in page_classifier.VOTER_BEARING:
        logger.info(
            "Page %s p%d classified %s (%.2f): %s -- skipping record extraction",
            file_id, page_number, page.page_type,
            classification.confidence, classification.reason,
        )
        # The map sheet holds no records but is the only visual record of
        # where an elector votes, so its panels are still worth cropping.
        if classification.page_type is page_classifier.PageType.MAP_PHOTO_PAGE:
            try:
                page.photos = photo_service.extract_station_photos(
                    page.lines, display, page.id, settings.photos_dir
                )
            except Exception:  # noqa: BLE001 - imagery is not worth failing a page over
                logger.exception("Station photo extraction failed on page %s", page_id)

        page.layout = LayoutInfo(source=GridSource.NONE, confidence=0.0, cells=[])
        page.header_text = " ".join(ln.text for ln in page.lines[:2])
        page.status = PageStatus.COMPLETED
        return page

    # ------------------------------------------------- 5. choose template
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

    # --------------------------------------------------- 6. detect layout
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

    # ------------------------------------------------------------ 7. parse
    try:
        records = template.parse(page.lines, layout, page.id, page_size, image=display)
    except Exception as exc:  # noqa: BLE001 - never let one page kill a batch
        logger.exception("Template %s failed to parse page %s", template.id, page_id)
        page.status = PageStatus.ERROR
        page.error = f"Parsing failed: {exc}"
        return page

    # --------------------------------------------------------- 8. validate
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
    page.photos = []

    if grid:
        # The number of slots this page actually has, which for a part-full
        # page is fewer than the template's nominal full-page grid.
        expected = len(layout.cells) or grid[0] * grid[1]
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

    # ------------------------------------------------ 9. header and footer
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


def process_page_with_retry(
    pdf_path: str | Path,
    page_number: int,
    file_id: str,
    template_id: str = "auto",
    lang: str | None = None,
    save_image: bool = False,
    page_id: str | None = None,
    max_retries: int | None = None,
) -> Page:
    """Process one page with automatic retry logic on transient errors."""
    retries = max_retries if max_retries is not None else settings.max_retries
    attempts = 0
    last_page = None
    while attempts <= retries:
        attempts += 1
        last_page = process_page(
            pdf_path=pdf_path,
            page_number=page_number,
            file_id=file_id,
            template_id=template_id,
            lang=lang,
            save_image=save_image,
            page_id=page_id,
        )
        if last_page.status == PageStatus.COMPLETED:
            return last_page
        if attempts <= retries:
            logger.warning(
                "Retrying page %d (attempt %d/%d) due to error: %s",
                page_number, attempts, retries, last_page.error,
            )
    return last_page if last_page is not None else Page(
        id=page_id or uuid.uuid4().hex[:12],
        file_id=file_id,
        page_number=page_number,
        status=PageStatus.ERROR,
        error="Processing failed after retries",
    )


def process_pdf(
    pdf_path: str | Path,
    file_id: str,
    template_id: str = "auto",
    lang: str | None = None,
    save_image: bool = False,
):
    """Process every page of a PDF, yielding pages as they complete."""
    info = pdf_service.inspect(pdf_path)
    for n in range(1, info.page_count + 1):
        yield process_page_with_retry(
            pdf_path,
            n,
            file_id,
            template_id=template_id,
            lang=lang,
            save_image=save_image,
        )

