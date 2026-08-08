import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path("d:/OCR/apps/api")))

from app.services import pipeline

pdf_path = Path(r"D:\OCR\PDF\Penn PDF\2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-8-WI.pdf")

print("Processing Part 8 Page 16...")
t0 = time.time()
page = pipeline.process_page(pdf_path, 16, "TAM-8", "electoral_roll_ta")
t1 = time.time()

print(f"Done in {t1 - t0:.2f}s")
print(f"Status: {page.status}")
print(f"Error: {page.error}")
print(f"Records: {len(page.records) if hasattr(page, 'records') else 'None'}")
