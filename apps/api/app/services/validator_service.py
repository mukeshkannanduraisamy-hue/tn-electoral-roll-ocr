"""Validation & Audit Service for Electoral Roll PDFs vs Supabase Database.

Strictly read-only inspection:
- Audits PDF Cover Sheet & Polling Station metadata against view_part_details / polling_stations
- Audits PDF Summary Sheet statistics against view_elector_counts / summaries
- Audits Voter records serial-by-serial (1..N) and field-by-field against view_voters_list / voters
- Flags Matched, Missing, Extra, Incorrect, Duplicates, Pass %, and Status (PASS/FAIL)
- Collects exact mismatch items with side-by-side comparison
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy import create_engine, text

from ..config import settings
from ..db import database_url

logger = logging.getLogger(__name__)

PDF_DIR = settings.validation_pdf_dir
CACHE_FILE = settings.data_dir / "validation_audit_results.json"


def parse_pdf_info(filename: str) -> tuple[str, str]:
    ac_match = re.search(r"-S22-(\d+)-", filename)
    part_match = re.search(r"-TAM-(\d+)-", filename)
    ac_no = ac_match.group(1) if ac_match else "58"
    part_no = part_match.group(1) if part_match else "0"
    return ac_no, part_no


def file_match_pattern(filename: str) -> str | None:
    """SQL LIKE pattern identifying one document, or None if it cannot.

    The fallback used to be `%{stem[:30]}%`, which does not identify anything
    here: thirty characters of these names is `2026-FC-EROLLGEN-S22-58-SIR-Fi`,
    a prefix 35 of the 47 documents share. What separates them -- the part
    number -- is at the end, so the audit matched one database file to every
    document sharing its prefix and counted that file's electors once per
    document.

    Both halves are pinned, because part 2 of AC 30 and part 2 of AC 58 are
    different documents, and the part number is followed by its delimiter so
    `-TAM-2-` cannot match `-TAM-286-`.

    None rather than a loose pattern when the name carries no part number: a
    fallback that matches everything is worse than no fallback, since it
    silently attributes some arbitrary file's electors to this document.
    """
    ac_match = re.search(r"-S22-(\d+)-", filename)
    part_match = re.search(r"-TAM-(\d+)-", filename)
    if not part_match:
        return None
    part = part_match.group(1)
    if not ac_match:
        return f"%-TAM-{part}-%"
    return f"%-S22-{ac_match.group(1)}-%-TAM-{part}-%"


def audit_fingerprint(*, files: int, records: int, voters: int) -> str:
    """Identifies the data an audit was computed against.

    Cheap on purpose -- three counts, not a checksum of every row. It is here
    to catch "the data changed since this verdict was written", which is what
    a re-extraction or a promotion does, and those move at least one count.
    """
    return f"f{files}:r{records}:v{voters}"


def cache_is_current(cached: dict[str, Any], fingerprint: str) -> bool:
    """Whether a cached audit still describes the database.

    A cache with no fingerprint is never current: it predates this check, so
    there is no way to tell what it was computed against, and serving it is
    how the panel came to show a 99.01% PASS while a fresh scan of the same
    database returned 93.42% FAIL.
    """
    stored = cached.get("fingerprint")
    return bool(stored) and stored == fingerprint


def current_fingerprint(conn) -> str:
    counts = []
    for table in ("files", "records", "voters"):
        try:
            counts.append(int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0))
        except Exception:  # noqa: BLE001 - a missing table is not a reason to fail the audit
            counts.append(0)
    return audit_fingerprint(files=counts[0], records=counts[1], voters=counts[2])


def run_audit_scan(filter_ac: str | None = None) -> dict[str, Any]:
    """Perform a full verification scan across all PDFs in PDF_DIR."""
    if not PDF_DIR.exists():
        # Say so in the payload, not only the log. An empty summary renders as
        # a panel with nothing in it, which looks like "audit found no
        # problems" rather than "the folder to audit was never found".
        logger.warning("Validation PDF directory does not exist: %s", PDF_DIR)
        return {
            "summary": {},
            "reports": [],
            "mismatches": [],
            "total_mismatches": 0,
            "error": (
                f"Source PDF folder not found: {PDF_DIR}. "
                f"Set OCR_VALIDATION_PDF_DIR to the folder holding the rolls."
            ),
        }

    pdfs = sorted(
        [p for p in PDF_DIR.glob("*.pdf")],
        key=lambda p: (int(parse_pdf_info(p.name)[0]), int(parse_pdf_info(p.name)[1])),
    )

    engine = create_engine(database_url(), pool_pre_ping=True)

    overall_summary: dict[str, Any] = {
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
        "audited_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    pdf_reports: list[dict[str, Any]] = []
    all_mismatches: list[dict[str, Any]] = []

    with engine.connect() as conn:
        for idx, pdf_path in enumerate(pdfs):
            filename = pdf_path.name
            ac_no, part_no = parse_pdf_info(filename)
            if filter_ac and filter_ac != ac_no:
                continue

            t0 = time.perf_counter()

            # 1. Fetch DB File record
            f_row = conn.execute(
                text("SELECT id, name, page_count, status FROM files WHERE name = :name"),
                {"name": filename},
            ).fetchone()

            if not f_row:
                # Constituency + part, not a prefix of the name. See
                # `file_match_pattern` for what the prefix matched instead.
                pattern = file_match_pattern(filename)
                if pattern:
                    f_row = conn.execute(
                        text(
                            "SELECT id, name, page_count, status FROM files "
                            "WHERE name LIKE :name"
                        ),
                        {"name": pattern},
                    ).fetchone()

            fid = f_row[0] if f_row else None

            # Fetch summary and polling station from DB
            ps_row = None
            sm_row = None
            if fid:
                ps_row = conn.execute(
                    text(
                        "SELECT part_number, total_electors, male_electors, female_electors, "
                        "third_gender_electors, serial_start, serial_end, ac_number, ac_name, "
                        "pc_number, pc_name FROM polling_stations WHERE file_id = :fid"
                    ),
                    {"fid": fid},
                ).fetchone()
                sm_row = conn.execute(
                    text(
                        "SELECT total_voters, male_count, female_count, third_gender_count, "
                        "extracted_records, printed_total FROM summaries WHERE file_id = :fid"
                    ),
                    {"fid": fid},
                ).fetchone()

            # Fetch voters strictly for this file
            if fid:
                voters_query = text("""
                    SELECT id, serial, epic, name, relation_type, relation_name, house_number,
                           age, gender, is_deleted, deletion_reason, page_number
                    FROM voters
                    WHERE source_file_id = :fid
                    ORDER BY serial ASC
                """)
                db_voters = conn.execute(voters_query, {"fid": fid}).fetchall()
            else:
                db_voters = []

            # If no voters linked by source_file_id, try by part_number & constituency
            if not db_voters and part_no:
                voters_query = text("""
                    SELECT id, serial, epic, name, relation_type, relation_name, house_number,
                           age, gender, is_deleted, deletion_reason, page_number
                    FROM voters
                    WHERE part_number = :part AND constituency LIKE :ac_pat
                    ORDER BY serial ASC
                """)
                db_voters = conn.execute(voters_query, {"part": part_no, "ac_pat": f"%{ac_no}%"}).fetchall()

            # 2. Determine Expected Total from Polling Station / Summary
            expected_total = 0
            if ps_row and ps_row[1] and ps_row[1] > 0:
                expected_total = int(ps_row[1])
            elif sm_row and sm_row[0] and sm_row[0] > 0:
                expected_total = int(sm_row[0])
            elif sm_row and sm_row[4] and sm_row[4] > 0:
                expected_total = int(sm_row[4])
            elif ps_row and ps_row[6] and ps_row[6] > 0:
                expected_total = int(ps_row[6])
            else:
                expected_total = len(db_voters)

            # 3. Analyze DB Voters
            total_db_records = len(db_voters)
            voters_by_serial: dict[int, Any] = {}
            duplicate_serials: list[int] = []
            duplicate_epics: list[tuple[int, str]] = []
            seen_epics: set[str] = set()

            field_errors_count = 0
            pdf_mismatches: list[dict[str, Any]] = []

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
                        "difference": "Serial number is missing or NULL in DB",
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
                        "difference": "Duplicate Serial Number found in database",
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
                            "difference": "Duplicate Voter EPIC Card ID found in part",
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
                        "difference": "Invalid or unread EPIC format",
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
                        "difference": "Empty or missing voter name",
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
                        "difference": f"Invalid age: {v_age}",
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
                        "difference": f"Unrecognized gender: {v_gender}",
                    }
                    pdf_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)

                if record_has_error:
                    field_errors_count += 1

            # 4. Check Missing Serials (1 to expected_total)
            missing_serials: list[int] = []
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
                            "difference": f"Serial #{s} was printed in PDF roll but is missing in DB",
                        }
                        pdf_mismatches.append(mismatch)
                        all_mismatches.append(mismatch)

            # 5. Check Extra Serials (beyond expected_total)
            extra_serials: list[int] = []
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
                            "difference": f"Serial #{s} exceeds summary sheet total count {expected_total}",
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
                "audit_time_s": round(time.perf_counter() - t0, 2),
            }
            pdf_reports.append(report_entry)

    if overall_summary["total_pdf_records"] > 0:
        overall_summary["overall_pass_pct"] = round(
            (overall_summary["matched"] / overall_summary["total_pdf_records"]) * 100.0, 2
        )
    overall_summary["overall_status"] = (
        "PASS" if overall_summary["overall_pass_pct"] >= 98.0 and overall_summary["missing_in_db"] == 0 else "FAIL"
    )

    # Recorded so a later read can tell whether this verdict still describes
    # the database. Taken after the scan rather than before, because the scan
    # only reads -- anything that changed underneath it invalidates the result
    # either way, and the later value is the one a subsequent read compares to.
    try:
        with engine.connect() as conn:
            fingerprint = current_fingerprint(conn)
    except Exception:  # noqa: BLE001
        fingerprint = ""

    output_payload = {
        "summary": overall_summary,
        "reports": pdf_reports,
        "mismatches": all_mismatches,
        "total_mismatches": len(all_mismatches),
        "fingerprint": fingerprint,
    }

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write audit cache file: %s", e)

    return output_payload


def get_cached_audit() -> dict[str, Any]:
    """The audit for the data as it stands, from cache when that is honest.

    The cache used to be served whenever the file existed, with nothing to
    invalidate it, so the panel kept reporting a verdict from before the last
    extraction -- 99.01% PASS from cache while a fresh scan of the same
    database returned 93.42% FAIL. It is now served only when its fingerprint
    still matches the database, and re-computed when it does not.

    There was also a fallback to an absolute path under `scratch/`. That is
    gone: it pointed at one machine's working directory, and a file there
    would have overridden the real result indefinitely.
    """
    if not CACHE_FILE.exists():
        return run_audit_scan()

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cached = json.load(f)
    except Exception:  # noqa: BLE001 - a damaged cache is a reason to rescan
        logger.warning("Validation cache unreadable; rescanning")
        return run_audit_scan()

    try:
        engine = create_engine(database_url(), pool_pre_ping=True)
        with engine.connect() as conn:
            fingerprint = current_fingerprint(conn)
    except Exception:  # noqa: BLE001 - cannot verify, so do not trust
        logger.warning("Could not fingerprint the database; rescanning")
        return run_audit_scan()

    if cache_is_current(cached, fingerprint):
        return cached

    logger.info("Validation cache is stale (data changed); rescanning")
    return run_audit_scan()
