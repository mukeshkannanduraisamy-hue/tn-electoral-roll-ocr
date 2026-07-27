"""Command-line entry point for the OCR pipeline.

Useful for batch runs, debugging and CI without going through the web app::

    python cli.py extract "path/to/page.pdf"
    python cli.py extract "path/to/page.pdf" --json out.json --overlay debug.png
    python cli.py batch "folder/of/pdfs" --out results.json
    python cli.py warmup
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Force UTF-8 stdout so Tamil output survives the Windows console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings  # noqa: E402
from app.schemas.core import IssueSeverity, Page  # noqa: E402
from app.services import pipeline  # noqa: E402
from app.templates import registry  # noqa: E402


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _cell(text: str, width: int) -> str:
    """Pad/truncate to `width` display columns.

    Tamil combining marks occupy no width, so a plain len() over-pads.
    Counting only spacing characters keeps columns aligned.
    """
    import unicodedata

    text = (text or "").replace("\n", " ")
    visible = [c for c in text if not unicodedata.combining(c)]
    if len(visible) > width:
        kept, count = [], 0
        for ch in text:
            if not unicodedata.combining(ch):
                if count >= width - 1:
                    break
                count += 1
            kept.append(ch)
        text = "".join(kept) + "…"
        visible = [c for c in text if not unicodedata.combining(c)]
    return text + " " * max(0, width - len(visible))


def print_page_report(page: Page, show_all: bool = True) -> None:
    template = registry.get_or_generic(page.template_id)
    columns = template.columns()

    print()
    print("=" * 118)
    print(f"  PAGE {page.page_number}   status={page.status}   "
          f"template={page.template_id} ({page.template_confidence:.0%})   "
          f"ocr={page.ocr_ms}ms")
    print(f"  image {page.width}x{page.height}px   lines={len(page.lines)}   "
          f"records={len(page.records)}")
    if page.layout:
        print(f"  layout: source={page.layout.source} confidence="
              f"{page.layout.confidence:.2f} deviation={page.layout.deviation:.3f} "
              f"cells={len(page.layout.cells)}")
    print("=" * 118)

    if page.error:
        print(f"  ERROR: {page.error}")
        return

    if page.header_text:
        print(f"  HEADER: {page.header_text}")
    if page.footer_text:
        print(f"  FOOTER: {page.footer_text}")
    print()

    widths = {
        "serial": 6, "epic": 12, "name": 22, "relation_type": 10,
        "relation_name": 22, "house_number": 12, "age": 5, "gender": 8,
        "line": 5, "text": 70,
    }

    header = "  " + " ".join(
        _cell(c.label, widths.get(c.key, 16)) for c in columns
    ) + "  conf  issues"
    print(header)
    print("  " + "-" * (len(header) + 6))

    for record in page.records:
        cells = []
        for col in columns:
            field = record.fields.get(col.key)
            cells.append(_cell(field.value if field else "", widths.get(col.key, 16)))
        errors = record.error_count
        warns = sum(
            1 for f in record.fields.values() for i in f.issues
            if i.severity == IssueSeverity.WARNING.value
        )
        flag = ""
        if errors:
            flag += f"E{errors}"
        if warns:
            flag += f" W{warns}"
        print(f"  {' '.join(cells)}  {record.mean_confidence:.2f}  {flag}")

    # Issue summary
    print()
    counts: dict[str, int] = {}
    for record in page.records:
        for issue in record.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        for field in record.fields.values():
            for issue in field.issues:
                counts[issue.code] = counts.get(issue.code, 0) + 1
    for issue in page.issues:
        counts[issue.code] = counts.get(issue.code, 0) + 1

    if counts:
        print("  ISSUES: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    else:
        print("  ISSUES: none")

    filled = sum(
        1 for r in page.records for f in r.fields.values() if f.original_value.strip()
    )
    total = sum(len(r.fields) for r in page.records) or 1
    print(f"  FIELD FILL RATE: {filled}/{total} ({filled / total:.0%})")

    clean = sum(1 for r in page.records if r.error_count == 0)
    print(f"  CLEAN RECORDS:   {clean}/{len(page.records)}")


def save_overlay(page: Page, path: Path) -> None:
    """Render detected cells + OCR boxes over the page image for debugging."""
    import cv2

    img_path = settings.pages_dir / (page.image_path or "")
    if not img_path.exists():
        print(f"  (overlay skipped: {img_path} not found)")
        return
    img = cv2.imread(str(img_path))
    if img is None:
        return

    if page.layout:
        for i, cell in enumerate(page.layout.cells):
            cv2.rectangle(
                img, (int(cell.x), int(cell.y)),
                (int(cell.x2), int(cell.y2)), (0, 140, 255), 2,
            )
            cv2.putText(img, str(i), (int(cell.x) + 4, int(cell.y) + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)

    for line in page.lines:
        colour = (0, 190, 0) if line.confidence >= 0.6 else (0, 0, 230)
        cv2.rectangle(
            img, (int(line.bbox.x), int(line.bbox.y)),
            (int(line.bbox.x2), int(line.bbox.y2)), colour, 1,
        )

    cv2.imwrite(str(path), img)
    print(f"  overlay written to {path}")


def page_to_dict(page: Page) -> dict:
    return json.loads(page.model_dump_json())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_extract(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"No such file: {pdf}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    pages = []
    for page in pipeline.process_pdf(
        pdf, file_id="cli", template_id=args.template, lang=args.lang
    ):
        print_page_report(page)
        pages.append(page)
        if args.overlay:
            save_overlay(page, Path(args.overlay))

    elapsed = time.perf_counter() - started
    print(f"\n  TOTAL: {len(pages)} page(s) in {elapsed:.1f}s")

    if args.json:
        Path(args.json).write_text(
            json.dumps([page_to_dict(p) for p in pages], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  JSON written to {args.json}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    pdfs = sorted(folder.rglob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    print(f"Processing {len(pdfs)} PDFs from {folder}")

    all_pages = []
    started = time.perf_counter()
    for i, pdf in enumerate(pdfs, 1):
        try:
            for page in pipeline.process_pdf(
                pdf, file_id=pdf.stem, template_id=args.template, lang=args.lang
            ):
                all_pages.append(page)
                clean = sum(1 for r in page.records if r.error_count == 0)
                print(f"  [{i}/{len(pdfs)}] {pdf.name}: {len(page.records)} records, "
                      f"{clean} clean, {page.ocr_ms}ms")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(pdfs)}] {pdf.name}: FAILED - {exc}")

    elapsed = time.perf_counter() - started
    total_records = sum(len(p.records) for p in all_pages)
    print(f"\n  {len(all_pages)} pages, {total_records} records in {elapsed:.1f}s "
          f"({elapsed / max(1, len(all_pages)):.1f}s/page)")

    # Spelling consensus needs the whole batch, so it runs once at the end.
    if not args.no_consensus:
        from app.services import consensus

        report = consensus.apply_consensus(all_pages)
        print(f"\n  CONSENSUS: {report.groups_examined} name groups, "
              f"{report.groups_with_conflict} with conflicting spellings, "
              f"{report.suggestions} corrected ({report.auto_applied} auto-applied)")
        for line in report.details[:20]:
            print(f"    {line}")
        if len(report.details) > 20:
            print(f"    ... and {len(report.details) - 20} more")

        clean_after = sum(
            1 for p in all_pages for r in p.records if r.error_count == 0
        )
        print(f"  CLEAN RECORDS: {clean_after}/{total_records}")

    if args.out:
        Path(args.out).write_text(
            json.dumps([page_to_dict(p) for p in all_pages], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  JSON written to {args.out}")
    return 0


def cmd_warmup(args: argparse.Namespace) -> int:
    from app.services import ocr_service

    print(f"Warming up PaddleOCR (lang={args.lang or settings.ocr_lang}) ...")
    elapsed = ocr_service.warmup(lang=args.lang)
    print(f"Ready in {elapsed:.1f}s")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="cli", description="PaddleOCR pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract", help="Process a single PDF")
    p.add_argument("pdf")
    p.add_argument("--template", default="auto")
    p.add_argument("--lang", default=None)
    p.add_argument("--json", default=None, help="Write full results as JSON")
    p.add_argument("--overlay", default=None, help="Write a debug overlay PNG")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("batch", help="Process a folder of PDFs")
    p.add_argument("folder")
    p.add_argument("--template", default="auto")
    p.add_argument("--lang", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--no-consensus", action="store_true",
                   help="Skip cross-corpus spelling harmonisation")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("warmup", help="Download and load models")
    p.add_argument("--lang", default=None)
    p.set_defaults(func=cmd_warmup)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
