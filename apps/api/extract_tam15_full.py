"""Full 42-page Voter Extraction & Deletion Analysis Script for TAM-15.

Extracts all voter records from PDF TAM-15-WI (1).pdf, including:
- Assembly Constituency (58-பென்னாகரம்)
- Part Number (15)
- Section Number & Name (பிரிவு எண் மற்றும் பெயர்)
- List Type (Main Roll / Additions / Deletions / Modifications)
- DELETED voter status and reason codes (S - Shifted, E - Expired, R - Repeated, etc.)
- Cross-corpus spelling consensus for Tamil names
- Direct SQLite DB Persistence
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from app.services import consensus, pipeline
from app.db import Base, engine, SessionLocal, VoterRow


def save_to_db(export_rows: list[dict]):
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        session.query(VoterRow).delete()
        
        db_rows = []
        for idx, r in enumerate(export_rows):
            v_id = f"VOTER_{idx+1:05d}"
            raw_epic = (r.get("EPIC_ID") or "").strip()
            epic_val = raw_epic if raw_epic else f"TEMP_{idx+1:05d}"
            
            # Prevent duplicate primary keys/uniques
            ser_str = str(r.get("SNo") or "")
            ser_num = int(ser_str) if ser_str.isdigit() else None
            
            age_str = str(r.get("Age") or "")
            age_num = int(age_str) if age_str.isdigit() else None

            search_str = f"{epic_val} {r.get('Name','')} {r.get('Relation_Name','')} {r.get('House_No','')} {ser_str} {r.get('Section_Name','')}".lower()

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
                part_number=str(r.get("Part_No") or "15"),
                constituency="58-பென்னாகரம்",
                page_number=r.get("Page_No"),
                source_file_name="2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-15-WI (1).pdf",
                notes=f"Is_Deleted: {r.get('Is_Deleted','No')} | Deletion_Reason: {r.get('Deletion_Reason','')}",
                search_text=search_str,
            )
            db_rows.append(v_row)
        
        # Deduplicate EPIC values if any misread occurred
        seen_epics = set()
        dedup_rows = []
        for row in db_rows:
            if row.epic in seen_epics:
                row.epic = f"{row.epic}_{row.id}"
            seen_epics.add(row.epic)
            dedup_rows.append(row)

        session.add_all(dedup_rows)
        session.commit()
        print(f"  ✓ Database populated with {len(dedup_rows)} voter rows in SQLite app.db!")
    finally:
        session.close()


def extract_tam15_full():
    pdf_path = Path(r"D:\OCR\PDF\Penn PDF\2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-15-WI (1).pdf")
    if not pdf_path.exists():
        print(f"Error: File not found at {pdf_path}")
        return

    print("==========================================================================")
    print(f"  FULL VOTER EXTRACTION: {pdf_path.name}")
    print("==========================================================================")

    all_pages = []
    t0 = time.perf_counter()

    # Process all pages of TAM-15-WI (1).pdf
    for page in pipeline.process_pdf(pdf_path, file_id="TAM-15", template_id="electoral_roll_ta"):
        all_pages.append(page)
        deleted_count = sum(
            1 for r in page.records
            if r.fields.get("is_deleted") and r.fields["is_deleted"].value == "Yes"
        )
        print(f"  Page {page.page_number:>2}: type={page.page_type:<18} "
              f"records={len(page.records):<2} deleted={deleted_count:<2} "
              f"ocr={page.ocr_ms}ms")

    elapsed = time.perf_counter() - t0

    # Apply cross-corpus spelling consensus across all extracted pages
    report = consensus.apply_consensus(all_pages)
    print("\n--------------------------------------------------------------------------")
    print("  CROSS-CORPUS SPELLING CONSENSUS SUMMARY")
    print("--------------------------------------------------------------------------")
    print(f"  Groups Examined : {report.groups_examined}")
    print(f"  Conflicts Found : {report.groups_with_conflict}")
    print(f"  Auto-applied    : {report.auto_applied}")

    # Compile structured voter records table
    headers = [
        "SNo", "EPIC_ID", "Name", "Relation_Type", "Relation_Name",
        "House_No", "Age", "Gender", "Is_Deleted", "Deletion_Reason",
        "Section_Name", "Part_No", "List_Type", "Page_No", "Confidence"
    ]

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
            part_no = f.get("part_number", {}).value if "part_number" in f else "15"
            l_type = f.get("list_type", {}).value if "list_type" in f else ""

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
                "Confidence": f"{rec.mean_confidence:.2f}",
            })

    total_records = len(export_rows)
    print("\n--------------------------------------------------------------------------")
    print("  EXTRACTION STATS SUMMARY")
    print("--------------------------------------------------------------------------")
    print(f"  Total Pages Processed : {len(all_pages)}")
    print(f"  Total Voters Extracted: {total_records}")
    print(f"  Total DELETED Voters  : {total_deleted}")
    print(f"  Total Elapsed Time    : {elapsed:.1f}s ({elapsed/max(1, len(all_pages)):.1f}s/page)")

    # Save to JSON
    out_json = Path("tam15_voter_records.json")
    out_json.write_text(json.dumps(export_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ JSON exported to {out_json.absolute()}")

    # Save to CSV with UTF-8 BOM for Excel
    out_csv = Path("tam15_voter_records.csv")
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(export_rows)
    print(f"  ✓ CSV exported to {out_csv.absolute()}")

    # Save to SQLite DB
    save_to_db(export_rows)

    # Print sample of extracted records including DELETED voters
    print("\n--------------------------------------------------------------------------")
    print("  SAMPLE EXTRACTED RECORDS (Including DELETED Voters)")
    print("--------------------------------------------------------------------------")
    print(f"  {'SNo':<6} {'EPIC ID':<13} {'Name':<18} {'Rel':<8} {'Rel Name':<18} {'HNo':<10} {'Age':<4} {'Gen':<6} {'Deleted?':<8} {'Reason':<25}")
    print("  " + "-" * 125)
    for row in export_rows[:10] + [r for r in export_rows if r["Is_Deleted"] == "Yes"][:10]:
        print(f"  {row['SNo']:<6} {row['EPIC_ID']:<13} {row['Name']:<18} {row['Relation_Type']:<8} "
              f"{row['Relation_Name']:<18} {row['House_No']:<10} {row['Age']:<4} {row['Gender']:<6} "
              f"{row['Is_Deleted']:<8} {row['Deletion_Reason']:<25}")


if __name__ == "__main__":
    extract_tam15_full()
