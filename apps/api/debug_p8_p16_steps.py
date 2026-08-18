import sys
import time
from pathlib import Path
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.insert(0, str(Path("d:/OCR/apps/api")))

from app.services import pipeline, pdf_service, preprocess, ocr_service, page_classifier, layout_service, photo_service
from app.templates import registry
from app.schemas.core import GridSource, LayoutInfo

pdf_path = Path(r"D:\OCR\PDF\Penn PDF\2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-8-WI.pdf")

print("DEBUGGING Part 8 Page 16...")
page_number = 16
file_id = "TAM-8"

print("1. Render page")
rendered = pdf_service.render_page(pdf_path, page_number)
print("2. Preprocess")
pre = preprocess.preprocess(rendered.image)
display = pre.display_image

print("3. OCR")
t0 = time.time()
ocr_result = ocr_service.run_ocr(pre.image, scale=pre.scale, lang="ta")
print(f"OCR finished in {time.time() - t0:.2f}s")
lines = ocr_result.lines

print("4. Classify")
classification = page_classifier.classify_page(lines, None, display.shape[1], display.shape[0])
print(f"Classification: {classification.page_type}")

print("5. Choose template")
template, confidence = registry.detect(lines, (display.shape[1], display.shape[0]))
print(f"Template: {template.id}")

print("6. Detect layout")
grid = template.expected_grid()
layout = layout_service.detect_layout(display, rows=grid[0], cols=grid[1])
print(f"Layout cells: {len(layout.cells)}")

print("7. Parse")
records = template.parse(lines, layout, "page_16", (display.shape[1], display.shape[0]), image=display)
print(f"Parsed records: {len(records)}")

print("8. Validate")
template.validate(records)

print("9. DONE")
