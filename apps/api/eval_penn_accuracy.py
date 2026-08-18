"""Penn PDF OCR Accuracy Evaluation Script.

Evaluates OCR extraction quality across PDFs in D:\\OCR\\PDF\\Penn PDF,
measuring total records, clean records, field fill rate, and issue breakdowns.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from app.schemas.core import IssueSeverity
from app.services import consensus, pipeline


def evaluate_penn(
    pdf_dir: Path,
    limit_files: int | None = None,
    pages_per_file: list[int] | None = None,
    apply_consensus_step: bool = True,
) -> dict:
    pdfs = sorted(list(pdf_dir.glob("*.pdf")))
    if limit_files:
        pdfs = pdfs[:limit_files]

    print(f"============================================================")
    print(f"  PENN OCR EVALUATION: {len(pdfs)} PDF(s) from {pdf_dir.name}")
    print(f"============================================================")

    all_pages = []
    file_results = []
    t0 = time.perf_counter()

    for idx, pdf_path in enumerate(pdfs, 1):
        print(f"\n[{idx}/{len(pdfs)}] Processing: {pdf_path.name}")
        
        target_pages = pages_per_file or [4, 5]
        
        pdf_pages = []
        for p_num in target_pages:
            try:
                page = pipeline.process_page(str(pdf_path), p_num, file_id=pdf_path.stem)
                pdf_pages.append(page)
                all_pages.append(page)
                
                clean = sum(1 for r in page.records if r.error_count == 0)
                filled = sum(1 for r in page.records for f in r.fields.values() if f.original_value.strip())
                total_fields = sum(len(r.fields) for r in page.records)
                
                print(f"  Page {p_num}: type={page.page_type:<15} records={len(page.records):<2} "
                      f"clean={clean:<2} fill_rate={filled}/{total_fields} ({filled/max(1,total_fields):.1%})")
            except Exception as exc:
                print(f"  Page {p_num} FAILED: {exc}")

        file_clean = sum(1 for p in pdf_pages for r in p.records if r.error_count == 0)
        file_records = sum(len(p.records) for p in pdf_pages)
        file_results.append({
            "file": pdf_path.name,
            "pages_processed": len(pdf_pages),
            "records": file_records,
            "clean_records": file_clean,
        })

    elapsed = time.perf_counter() - t0

    # Issue breakdown before consensus
    total_records = sum(len(p.records) for p in all_pages)
    clean_before = sum(1 for p in all_pages for r in p.records if r.error_count == 0)
    filled_before = sum(1 for p in all_pages for r in p.records for f in r.fields.values() if f.original_value.strip())
    total_fields = sum(len(r.fields) for p in all_pages for r in p.records) or 1

    issue_counts: dict[str, int] = {}
    for p in all_pages:
        for r in p.records:
            for iss in r.issues:
                issue_counts[iss.code] = issue_counts.get(iss.code, 0) + 1
            for f in r.fields.values():
                for iss in f.issues:
                    issue_counts[iss.code] = issue_counts.get(iss.code, 0) + 1

    print("\n------------------------------------------------------------")
    print("  RAW EXTRACTION SUMMARY (Before Consensus)")
    print("------------------------------------------------------------")
    print(f"  Total Pages Processed : {len(all_pages)}")
    print(f"  Total Records Found   : {total_records}")
    print(f"  Clean Records         : {clean_before}/{total_records} ({clean_before/max(1,total_records):.1%})")
    print(f"  Field Fill Rate       : {filled_before}/{total_fields} ({filled_before/total_fields:.1%})")
    print(f"  Total Issues          : {sum(issue_counts.values())}")
    for code, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"    - {code:<25}: {count}")

    consensus_info = {}
    if apply_consensus_step and all_pages:
        rep = consensus.apply_consensus(all_pages)
        clean_after = sum(1 for p in all_pages for r in p.records if r.error_count == 0)
        consensus_info = {
            "groups_examined": rep.groups_examined,
            "conflicts": rep.groups_with_conflict,
            "suggestions": rep.suggestions,
            "auto_applied": rep.auto_applied,
            "clean_records_after": clean_after,
        }
        print("\n------------------------------------------------------------")
        print("  CONSENSUS SUMMARY")
        print("------------------------------------------------------------")
        print(f"  Groups Examined : {rep.groups_examined}")
        print(f"  Conflicts Found : {rep.groups_with_conflict}")
        print(f"  Auto-applied    : {rep.auto_applied}")
        print(f"  Clean Records   : {clean_after}/{total_records} ({clean_after/max(1,total_records):.1%})")

    results = {
        "elapsed_sec": round(elapsed, 2),
        "total_pages": len(all_pages),
        "total_records": total_records,
        "clean_records_before": clean_before,
        "clean_ratio_before": round(clean_before / max(1, total_records), 4),
        "filled_fields": filled_before,
        "total_fields": total_fields,
        "fill_rate": round(filled_before / total_fields, 4),
        "issues": issue_counts,
        "consensus": consensus_info,
        "files": file_results,
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate OCR accuracy on Penn PDFs")
    parser.add_argument("--pdf-dir", default=r"D:\OCR\PDF\Penn PDF")
    parser.add_argument("--limit", type=int, default=5, help="Number of PDF files to evaluate")
    parser.add_argument("--pages", nargs="+", type=int, default=[4, 5], help="Page numbers to evaluate per PDF")
    parser.add_argument("--out", default="penn_accuracy_report.json")
    args = parser.parse_args()

    results = evaluate_penn(
        pdf_dir=Path(args.pdf_dir),
        limit_files=args.limit,
        pages_per_file=args.pages,
    )

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
