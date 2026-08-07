"""Batch Voter Extraction for ALL Penn PDF Parts (1-38).

Extracts voter records from all 32 PDFs in D:\\OCR\\PDF\\Penn PDF,
applies cross-corpus spelling consensus per part, and persists
everything into the SQLite database + JSON/CSV exports.

Assembly Constituency: 58-பென்னாகரம் (Pennagaram)
District: தர்மபுரி (Dharmapuri)

Usage:
    apps/api/.venv/Scripts/python.exe apps/api/extract_all_penn.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

import cv2
import fitz
import numpy as np

from app.services import consensus, pipeline
from app.services.preprocess import is_blank_page
from app.db import Base, engine, SessionLocal, VoterRow


PDF_DIR = Path(r"D:\OCR\PDF\Penn PDF")
CONSTITUENCY = "58-பென்னாகரம்"
DISTRICT = "தர்மபுரி (Dharmapuri)"

HEADERS = [
    "SNo", "EPIC_ID", "Name", "Relation_Type", "Relation_Name",
    "House_No", "Age", "Gender", "Is_Deleted", "Deletion_Reason",
    "Section_Name", "Part_No", "List_Type", "Page_No", "Source_File",
    "Confidence"
]


def extract_part_number(filename: str) -> str:
    """Extract part number from Penn PDF filename like -TAM-15-WI."""
    m = re.search(r"-TAM-(\d+)-", filename)
    return m.group(1) if m else "0"


def process_single_pdf(pdf_path: Path, part_number: str) -> list[dict]:
    """Process a single PDF and return extracted voter rows."""
    filename = pdf_path.name
    file_id = f"TAM-{part_number}"

    print(f"\n{'='*80}")
    print(f"  EXTRACTING Part {part_number}: {filename}")
    print(f"{'='*80}")

    try:
        doc = fitz.open(str(pdf_path))
        total_pages = doc.page_count
        doc.close()
    except Exception as e:
        print(f"  ⚠ Cannot open PDF: {e}")
        return []

    all_pages = []
    blank_pages = 0
    error_pages = 0
    t0 = time.perf_counter()

    for page in pipeline.process_pdf(pdf_path, file_id=file_id, template_id="electoral_roll_ta"):
        if page.error:
            error_pages += 1
            print(f"  Page {page.page_number:>3}: ERROR - {page.error[:60]}")
            continue

        if not page.records and page.page_type not in ("voter_grid", "supplement_grid"):
            blank_pages += 1
            continue

        all_pages.append(page)
        deleted_count = sum(
            1 for r in page.records
            if r.fields.get("is_deleted") and r.fields["is_deleted"].value == "Yes"
        )
        print(f"  Page {page.page_number:>3}: type={page.page_type:<18} "
              f"records={len(page.records):<2} deleted={deleted_count:<2} "
              f"ocr={page.ocr_ms}ms")

    elapsed = time.perf_counter() - t0

    # Apply cross-corpus spelling consensus for this part
    if all_pages:
        report = consensus.apply_consensus(all_pages)
        print(f"\n  Consensus: {report.groups_examined} groups, "
              f"{report.groups_with_conflict} conflicts, "
              f"{report.auto_applied} auto-applied")

    # Compile export rows
    export_rows = []
    total_deleted = 0

    for page in all_pages:
        for rec in page.records:
            f = rec.fields
            s_no = f.get("serial", {}).value if "serial" in f else ""
            epic = f.get("epic", {}).value if "epic" in f else ""
            name = f.get("name", {}).value if "name" in f else ""
            rel_type = f.get("relation_type", {}).value if "relation_type" in f else ""
            rel_name = f.get("relation_name", {}).value if "relation_name" in f else ""
            house = f.get("house_number", {}).value if "house_number" in f else ""
            age = f.get("age", {}).value if "age" in f else ""
            gender = f.get("gender", {}).value if "gender" in f else ""
            is_del = f.get("is_deleted", {}).value if "is_deleted" in f else "No"
            del_reason = f.get("deletion_reason", {}).value if "deletion_reason" in f else ""
            sec_name = f.get("section_name", {}).value if "section_name" in f else ""
            part_no = f.get("part_number", {}).value if "part_number" in f else part_number
            l_type = f.get("list_type", {}).value if "list_type" in f else ""

            if not part_no:
                part_no = part_number

            if is_del == "Yes":
                total_deleted += 1

            export_rows.append({
                "SNo": s_no,
                "EPIC_ID": epic,
                "Name": name,
                "Relation_Type": rel_type,
                "Relation_Name": rel_name,
                "House_No": house,
                "Age": age,
                "Gender": gender,
                "Is_Deleted": is_del,
                "Deletion_Reason": del_reason,
                "Section_Name": sec_name,
                "Part_No": part_no,
                "List_Type": l_type,
                "Page_No": page.page_number,
                "Source_File": filename,
                "Confidence": f"{rec.mean_confidence:.2f}",
            })

    print(f"\n  Part {part_number} Summary:")
    print(f"    Pages: {total_pages} total, {len(all_pages)} voter pages, "
          f"{blank_pages} blank, {error_pages} errors")
    print(f"    Voters: {len(export_rows)} extracted, {total_deleted} DELETED")
    print(f"    Time: {elapsed:.1f}s ({elapsed/max(1, total_pages):.1f}s/page)")

    return export_rows


def save_to_db(all_rows: list[dict]):
    """Persist all extracted voter rows into SQLite."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        # Extract all unique part numbers in this batch
        parts_to_delete = list({str(r.get("Part_No") or "") for r in all_rows})
        
        # Delete only records for the parts we are updating
        if parts_to_delete:
            session.query(VoterRow).filter(VoterRow.part_number.in_(parts_to_delete)).delete(synchronize_session=False)

        db_rows = []
        for idx, r in enumerate(all_rows):
            part = str(r.get("Part_No") or "0")
            v_id = f"VOTER_P{part}_{idx+1:05d}"
            raw_epic = (r.get("EPIC_ID") or "").strip()
            epic_val = raw_epic if raw_epic else f"TEMP_P{part}_{idx+1:05d}"

            ser_str = str(r.get("SNo") or "")
            ser_num = int(ser_str) if ser_str.isdigit() else None

            age_str = str(r.get("Age") or "")
            age_num = int(age_str) if age_str.isdigit() else None

            search_str = (
                f"{epic_val} {r.get('Name','')} {r.get('Relation_Name','')} "
                f"{r.get('House_No','')} {ser_str} {r.get('Section_Name','')} "
                f"Part {r.get('Part_No','')} {r.get('Source_File','')}"
            ).lower()

            v_row = VoterRow(
                id=v_id,
                epic=epic_val,
                serial=ser_num,
                name=r.get("Name", ""),
                relation_type=r.get("Relation_Type", ""),
                relation_name=r.get("Relation_Name", ""),
                house_number=r.get("House_No", ""),
                age=age_num,
                gender=r.get("Gender", ""),
                part_number=str(r.get("Part_No") or ""),
                constituency=CONSTITUENCY,
                page_number=r.get("Page_No"),
                source_file_name=r.get("Source_File", ""),
                section_name=r.get("Section_Name", ""),
                notes=f"Is_Deleted: {r.get('Is_Deleted','No')} | Deletion_Reason: {r.get('Deletion_Reason','')} | District: {DISTRICT}",
                search_text=search_str,
            )
            db_rows.append(v_row)

        # Deduplicate EPIC values
        seen_epics = set()
        dedup_rows = []
        for row in db_rows:
            if row.epic in seen_epics:
                row.epic = f"{row.epic}_{row.id}"
            seen_epics.add(row.epic)
            dedup_rows.append(row)

        session.add_all(dedup_rows)
        session.commit()
        print(f"\n  ✓ Database updated with {len(dedup_rows)} voter rows (replaced parts: {parts_to_delete})!")
    finally:
        session.close()


def main():
    print("=" * 80)
    print("  BATCH VOTER EXTRACTION: ALL PENN PDF PARTS")
    print(f"  Directory: {PDF_DIR}")
    print(f"  Constituency: {CONSTITUENCY}")
    print(f"  District: {DISTRICT}")
    print("=" * 80)

    # Find all PDFs
    pdf_files = sorted(
        [f for f in PDF_DIR.iterdir() if f.suffix.lower() == ".pdf"],
        key=lambda p: int(extract_part_number(p.name) or "0")
    )
    
    # Check if a specific part was requested via command line
    if len(sys.argv) > 1:
        target_part = sys.argv[1]
        pdf_files = [f for f in pdf_files if extract_part_number(f.name) == target_part]
        if not pdf_files:
            print(f"Error: Part {target_part} not found in {PDF_DIR}")
            return
    else:
        # Resume from Part 18 by default if no arg provided (since 1-17 are mostly done)
        pdf_files = [f for f in pdf_files if int(extract_part_number(f.name) or "0") >= 18]

    print(f"\n  Found {len(pdf_files)} PDF files to process:")
    for f in pdf_files:
        part = extract_part_number(f.name)
        print(f"    Part {part:>3s}: {f.name} ({f.stat().st_size / 1024 / 1024:.1f}MB)")

    # Process each PDF
    all_export_rows = []
    part_stats = {}
    t_total = time.perf_counter()

    for pdf_path in pdf_files:
        part_number = extract_part_number(pdf_path.name)
        try:
            rows = process_single_pdf(pdf_path, part_number)
            all_export_rows.extend(rows)
            part_stats[part_number] = {
                "voters": len(rows),
                "deleted": sum(1 for r in rows if r.get("Is_Deleted") == "Yes"),
                "file": pdf_path.name,
            }
        except Exception as e:
            print(f"\n  ⚠ FAILED Part {part_number}: {e}")
            part_stats[part_number] = {"voters": 0, "deleted": 0, "file": pdf_path.name, "error": str(e)}

    total_elapsed = time.perf_counter() - t_total

    # Final summary
    total_voters = len(all_export_rows)
    total_deleted = sum(1 for r in all_export_rows if r.get("Is_Deleted") == "Yes")

    print("\n" + "=" * 80)
    print("  BATCH EXTRACTION COMPLETE")
    print("=" * 80)
    print(f"  Total PDFs Processed : {len(pdf_files)}")
    print(f"  Total Voters         : {total_voters:,}")
    print(f"  Total DELETED        : {total_deleted:,}")
    print(f"  Total Time           : {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")

    print(f"\n  Per-Part Breakdown:")
    print(f"  {'Part':>6s}  {'Voters':>8s}  {'Deleted':>8s}  {'File'}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*40}")
    for part_no in sorted(part_stats.keys(), key=int):
        s = part_stats[part_no]
        err = f" ⚠ {s.get('error','')[:30]}" if s.get("error") else ""
        print(f"  {part_no:>6s}  {s['voters']:>8,}  {s['deleted']:>8,}  {s['file'][:40]}{err}")

    # Export JSON
    out_json = Path(f"penn_voter_records_part_{target_part}.json" if len(sys.argv) > 1 else "penn_all_voter_records.json")
    out_json.write_text(json.dumps(all_export_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ JSON exported to {out_json.absolute()}")

    # Export CSV
    out_csv = Path(f"penn_voter_records_part_{target_part}.csv" if len(sys.argv) > 1 else "penn_all_voter_records.csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(all_export_rows)
    print(f"  ✓ CSV exported to {out_csv.absolute()}")

    # Save to DB
    save_to_db(all_export_rows)

    print(f"\n  ✓ ALL DONE! {total_voters:,} voters from {len(pdf_files)} PDFs "
          f"in {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
