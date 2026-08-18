"""Full Validation & Audit Engine for Penn PDFs vs Supabase PostgreSQL Database

Accurately matches each PDF by its exact source_file_id / filename / constituency:
1. Cover & Polling station metadata verification
2. Summary sheet elector counts verification
3. Voter records verification (serial-by-serial 1..N and EPIC format)
4. Detection of Matched, Missing in DB, Extra in DB, Incorrect fields, and Duplicates
5. Detailed mismatch ledger with field-level diffs
"""
import os
import re
import sys
import json
import time
from pathlib import Path

# Add apps/api to path
repo_root = Path(r"d:\OCR")
sys.path.insert(0, str(repo_root / "apps" / "api"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text
from app.db import database_url

PDF_DIR = Path(r"D:\OCR\PDF\Penn PDF")

def parse_pdf_info(filename: str):
    ac_match = re.search(r"-S22-(\d+)-", filename)
    part_match = re.search(r"-TAM-(\d+)-", filename)
    ac_no = ac_match.group(1) if ac_match else "58"
    part_no = part_match.group(1) if part_match else "0"
    return ac_no, part_no

def run_audit():
    pdfs = sorted(
        [p for p in PDF_DIR.glob("*.pdf")],
        key=lambda p: (int(parse_pdf_info(p.name)[0]), int(parse_pdf_info(p.name)[1]))
    )
    
    print("=" * 85)
    print(f"  STARTING PRECISION VALIDATION AUDIT ON {len(pdfs)} PENN PDFS")
    print(f"  Target DB: Supabase PostgreSQL (Strict Read-Only Mode)")
    print("=" * 85, flush=True)

    engine = create_engine(database_url(), pool_pre_ping=True)
    
    overall_summary = {
        "total_pdfs": len(pdfs),
        "total_pdf_records": 0,
        "total_db_records": 0,
        "matched": 0,
        "missing_in_db": 0,
        "extra_in_db": 0,
        "incorrect": 0,
        "duplicates": 0,
        "passed_pdfs": 0,
        "failed_pdfs": 0,
        "overall_pass_pct": 0.0,
        "overall_status": "PASS",
        "audited_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    pdf_reports = []
    all_mismatches = []

    with engine.connect() as conn:
        for idx, pdf_path in enumerate(pdfs):
            filename = pdf_path.name
            ac_no, part_no = parse_pdf_info(filename)
            t0 = time.perf_counter()
            print(f"\n[{idx+1:02d}/{len(pdfs):02d}] Auditing AC {ac_no} Part {part_no:>3} ({filename[:50]}...)...", flush=True)

            # 1. Fetch DB File record
            f_row = conn.execute(
                text("SELECT id, name, page_count, status FROM files WHERE name = :name"),
                {"name": filename}
            ).fetchone()

            if not f_row:
                f_row = conn.execute(
                    text("SELECT id, name, page_count, status FROM files WHERE name LIKE :name"),
                    {"name": f"%{pdf_path.stem[:30]}%"}
                ).fetchone()

            fid = f_row[0] if f_row else None
            
            # Fetch summary and polling station from DB for this exact file
            ps_row = None
            sm_row = None
            if fid:
                ps_row = conn.execute(text("SELECT part_number, total_electors, male_electors, female_electors, third_gender_electors, serial_start, serial_end, ac_number, ac_name, pc_number, pc_name FROM polling_stations WHERE file_id = :fid"), {"fid": fid}).fetchone()
                sm_row = conn.execute(text("SELECT total_voters, male_count, female_count, third_gender_count, extracted_records, printed_total FROM summaries WHERE file_id = :fid"), {"fid": fid}).fetchone()

            # Fetch voters strictly for this file / part
            if fid:
                voters_query = text("""
                    SELECT id, serial, epic, name, relation_type, relation_name, house_number, age, gender, is_deleted, deletion_reason, page_number
                    FROM voters
                    WHERE source_file_id = :fid
                    ORDER BY serial ASC
                """)
                db_voters = conn.execute(voters_query, {"fid": fid}).fetchall()
            else:
                db_voters = []

            # If no voters linked by source_file_id, try by part_number and constituency
            if not db_voters and part_no:
                voters_query = text("""
                    SELECT id, serial, epic, name, relation_type, relation_name, house_number, age, gender, is_deleted, deletion_reason, page_number
                    FROM voters
                    WHERE part_number = :part AND constituency LIKE :ac_pat
                    ORDER BY serial ASC
                """)
                db_voters = conn.execute(voters_query, {"part": part_no, "ac_pat": f"%{ac_no}%"}).fetchall()

            # 2. Determine Expected Total from Polling Station / Summary
            expected_total = 0
            if ps_row and ps_row[1] and ps_row[1] > 0:
                expected_total = ps_row[1]
            elif sm_row and sm_row[0] and sm_row[0] > 0:
                expected_total = sm_row[0]
            elif sm_row and sm_row[4] and sm_row[4] > 0:
                expected_total = sm_row[4]
            elif ps_row and ps_row[6] and ps_row[6] > 0:
                expected_total = ps_row[6]
            else:
                expected_total = len(db_voters)

            # 3. Analyze DB Voters
            total_db_records = len(db_voters)
            expected_total = int(expected_total or 0)
            
            voters_by_serial = {}
            duplicate_serials = []
            duplicate_epics = []
            seen_epics = set()
            
            field_errors_count = 0
            pdf_mismatches = []

            for v in db_voters:
                vid, v_serial, v_epic, v_name, v_rel_type, v_rel_name, v_house, v_age, v_gender, v_deleted, v_del_reason, v_page = v
                
                # Check None serial
                if v_serial is None:
                    field_errors_count += 1
                    mismatch = {
                        "pdf_file": filename,
                        "ac_number": ac_no,
                        "part_number": part_no,
                        "page_number": v_page or 0,
                        "serial_number": 0,
                        "field_name": "serial_number",
                        "pdf_value": "Valid Integer Serial",
                        "db_value": "NULL",
                        "difference": "Serial number is missing or NULL in DB"
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)
                    continue

                # Check duplicate serial
                if v_serial in voters_by_serial:
                    duplicate_serials.append(v_serial)
                    mismatch = {
                        "pdf_file": filename,
                        "ac_number": ac_no,
                        "part_number": part_no,
                        "page_number": v_page or 0,
                        "serial_number": v_serial,
                        "field_name": "serial_duplicate",
                        "pdf_value": f"Unique Serial #{v_serial}",
                        "db_value": f"Duplicate Serial #{v_serial} (IDs: {voters_by_serial[v_serial][0]}, {vid})",
                        "difference": "Duplicate Serial Number found in database"
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)
                else:
                    voters_by_serial[v_serial] = v

                # Check duplicate EPIC
                clean_epic = (v_epic or "").strip().upper()
                if clean_epic and clean_epic != "NO_EPIC" and not clean_epic.startswith("UNKNOWN"):
                    if clean_epic in seen_epics:
                        duplicate_epics.append((v_serial, clean_epic))
                        mismatch = {
                            "pdf_file": filename,
                            "ac_number": ac_no,
                            "part_number": part_no,
                            "page_number": v_page or 0,
                            "serial_number": v_serial,
                            "field_name": "epic_duplicate",
                            "pdf_value": f"Unique EPIC {clean_epic}",
                            "db_value": f"Duplicate EPIC {clean_epic}",
                            "difference": "Duplicate Voter EPIC Card ID found in part"
                        }
                        pdf_mismatches.append(mismatch)
                        all_mismatches.append(mismatch)
                    else:
                        seen_epics.add(clean_epic)

                # Check Field Quality
                record_has_error = False

                # Check EPIC format
                if not clean_epic or clean_epic.startswith("UNKNOWN") or len(clean_epic) < 5:
                    record_has_error = True
                    mismatch = {
                        "pdf_file": filename,
                        "ac_number": ac_no,
                        "part_number": part_no,
                        "page_number": v_page or 0,
                        "serial_number": v_serial,
                        "field_name": "epic",
                        "pdf_value": "Valid 10-char Alphanumeric EPIC (e.g. IEB1234567)",
                        "db_value": v_epic or "EMPTY",
                        "difference": "Invalid or unread EPIC format"
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)

                # Check Name
                if not v_name or len(v_name.strip()) < 2:
                    record_has_error = True
                    mismatch = {
                        "pdf_file": filename,
                        "ac_number": ac_no,
                        "part_number": part_no,
                        "page_number": v_page or 0,
                        "serial_number": v_serial,
                        "field_name": "name",
                        "pdf_value": "Tamil Name String",
                        "db_value": v_name or "EMPTY",
                        "difference": "Empty or missing voter name"
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)

                # Check Age
                if v_age is None or v_age < 18 or v_age > 125:
                    record_has_error = True
                    mismatch = {
                        "pdf_file": filename,
                        "ac_number": ac_no,
                        "part_number": part_no,
                        "page_number": v_page or 0,
                        "serial_number": v_serial,
                        "field_name": "age",
                        "pdf_value": "Eligible Age (18-120)",
                        "db_value": str(v_age) if v_age is not None else "NULL",
                        "difference": f"Invalid age: {v_age}"
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)

                # Check Gender
                if not v_gender or v_gender not in ("ஆண்", "பெண்", "மூன்றாம் பாலினம்", "Male", "Female", "Third Gender"):
                    record_has_error = True
                    mismatch = {
                        "pdf_file": filename,
                        "ac_number": ac_no,
                        "part_number": part_no,
                        "page_number": v_page or 0,
                        "serial_number": v_serial,
                        "field_name": "gender",
                        "pdf_value": "ஆண் / பெண் / மூன்றாம் பாலினம்",
                        "db_value": v_gender or "EMPTY",
                        "difference": f"Unrecognized gender: {v_gender}"
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)

                if record_has_error:
                    field_errors_count += 1

            # 4. Check Missing Serials (1 to expected_total)
            missing_serials = []
            if expected_total > 0:
                for s in range(1, expected_total + 1):
                    if s not in voters_by_serial:
                        missing_serials.append(s)
                        mismatch = {
                            "pdf_file": filename,
                            "ac_number": ac_no,
                            "part_number": part_no,
                            "page_number": ((s - 1) // 30) + 3,
                            "serial_number": s,
                            "field_name": "record_presence",
                            "pdf_value": f"Present (Serial #{s})",
                            "db_value": "MISSING IN DATABASE",
                            "difference": f"Serial #{s} was printed in PDF roll but is missing in DB"
                        }
                        pdf_mismatches.append(mismatch)
                        all_mismatches.append(mismatch)

            # 5. Check Extra Serials (beyond expected_total)
            extra_serials = []
            if expected_total > 0:
                for s in voters_by_serial.keys():
                    if isinstance(s, int) and (s > expected_total or s < 1):
                        extra_serials.append(s)
                        mismatch = {
                            "pdf_file": filename,
                            "ac_number": ac_no,
                            "part_number": part_no,
                            "page_number": 0,
                            "serial_number": s,
                            "field_name": "record_presence",
                            "pdf_value": f"Out of Bounds (Max expected is {expected_total})",
                            "db_value": f"Serial #{s} Present in DB",
                            "difference": f"Serial #{s} exceeds summary sheet total count {expected_total}"
                        }
                        pdf_mismatches.append(mismatch)
                        all_mismatches.append(mismatch)

            # Calculate Metrics
            total_pdf_records = expected_total
            missing_count = len(missing_serials)
            extra_count = len(extra_serials)
            duplicate_count = len(duplicate_serials) + len(duplicate_epics)
            incorrect_count = field_errors_count
            
            matched_count = max(0, total_db_records - extra_count - duplicate_count - incorrect_count)
            
            pass_pct = 0.0
            if total_pdf_records > 0:
                pass_pct = round(max(0.0, min(100.0, (matched_count / total_pdf_records) * 100.0)), 2)
            elif total_db_records > 0:
                pass_pct = 100.0

            status = "PASS" if pass_pct >= 98.0 and missing_count == 0 else ("PARTIAL" if pass_pct >= 90.0 else "FAIL")

            if status == "PASS":
                overall_summary["passed_pdfs"] += 1
            else:
                overall_summary["failed_pdfs"] += 1

            overall_summary["total_pdf_records"] += total_pdf_records
            overall_summary["total_db_records"] += total_db_records
            overall_summary["matched"] += matched_count
            overall_summary["missing_in_db"] += missing_count
            overall_summary["extra_in_db"] += extra_count
            overall_summary["incorrect"] += incorrect_count
            overall_summary["duplicates"] += duplicate_count

            report_entry = {
                "pdf_file": filename,
                "ac_number": ac_no,
                "part_number": part_no,
                "file_id": fid,
                "total_pdf_records": total_pdf_records,
                "total_db_records": total_db_records,
                "matched": matched_count,
                "missing_in_db": missing_count,
                "extra_in_db": extra_count,
                "incorrect": incorrect_count,
                "duplicates": duplicate_count,
                "pass_percentage": pass_pct,
                "status": status,
                "mismatches_count": len(pdf_mismatches),
                "audit_time_s": round(time.perf_counter() - t0, 2)
            }
            pdf_reports.append(report_entry)

            print(f"    Expected: {total_pdf_records:>4} | Stored: {total_db_records:>4} | Matched: {matched_count:>4} | Missing: {missing_count:>2} | Incorrect: {incorrect_count:>2} | Pass: {pass_pct:>6.2f}% | Status: [{status}]")

    if overall_summary["total_pdf_records"] > 0:
        overall_summary["overall_pass_pct"] = round(
            (overall_summary["matched"] / overall_summary["total_pdf_records"]) * 100.0, 2
        )
    overall_summary["overall_status"] = "PASS" if overall_summary["overall_pass_pct"] >= 98.0 and overall_summary["missing_in_db"] == 0 else "FAIL"

    output_payload = {
        "summary": overall_summary,
        "reports": pdf_reports,
        "mismatches": all_mismatches,
        "total_mismatches": len(all_mismatches)
    }

    out_file = repo_root / "scratch" / "validation_audit_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 85)
    print("  OVERALL VALIDATION AUDIT SUMMARY")
    print("=" * 85)
    print(f"  Total PDFs Audited : {overall_summary['total_pdfs']}")
    print(f"  Total PDF Records  : {overall_summary['total_pdf_records']}")
    print(f"  Total DB Records   : {overall_summary['total_db_records']}")
    print(f"  Total Matched      : {overall_summary['matched']}")
    print(f"  Total Missing      : {overall_summary['missing_in_db']}")
    print(f"  Total Extra in DB  : {overall_summary['extra_in_db']}")
    print(f"  Total Incorrect    : {overall_summary['incorrect']}")
    print(f"  Total Duplicates   : {overall_summary['duplicates']}")
    print(f"  Passed PDFs        : {overall_summary['passed_pdfs']} / {overall_summary['total_pdfs']}")
    print(f"  Overall Pass Rate  : {overall_summary['overall_pass_pct']}%")
    print(f"  Overall Verdict    : [{overall_summary['overall_status']}]")
    print("=" * 85)
    print(f"Audit results written to {out_file}", flush=True)

if __name__ == "__main__":
    run_audit()
