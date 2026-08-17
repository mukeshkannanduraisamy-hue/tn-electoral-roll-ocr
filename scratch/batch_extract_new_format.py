"""Resumable Batch Extraction Pipeline for the New 3-Table Format (Voter POV Order)

Processes all PDFs in D:\OCR\PDF\Penn PDF:
- Skips already completed parts in database
- Exports all 31 parts into Table 1, Table 2, Table 3, and Unified Master CSV/JSON with Voter POV Order
- Syncs database tables & voter_master_view
"""
import os
import re
import sys
import time
import json
import csv
import uuid
from pathlib import Path

# Add apps/api to path
repo_root = Path(r"d:\OCR")
sys.path.insert(0, str(repo_root / "apps" / "api"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import pdf_service, preprocess, ocr_service, roll_metadata, pipeline, consensus
from app.db import (
    session_scope, FileRow, PollingStationRow, SummaryRow, VoterRow, save_page
)
from sqlalchemy import select

PDF_DIR = Path(r"D:\OCR\PDF\Penn PDF")
OUTPUT_DIR = Path(r"D:\OCR\output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def part_number_from_name(filename: str) -> str:
    m = re.search(r"-TAM-(\d+)-", filename)
    return m.group(1) if m else "0"

def translate_gender(gender_str: str) -> str:
    g = (gender_str or "").strip().lower()
    if g in ("male", "m", "ஆண்"):
        return "ஆண்"
    elif g in ("female", "f", "பெண்"):
        return "பெண்"
    elif g in ("third_gender", "third gender", "transgender", "மூன்றாம் பாலினம்", "மூன்றாம்"):
        return "மூன்றாம் பாலினம்"
    return gender_str

def run_batch():
    pdfs = sorted(
        [p for p in PDF_DIR.glob("*.pdf")],
        key=lambda p: int(part_number_from_name(p.name) or "0")
    )
    
    print("=" * 80)
    print(f"  RESUMING BATCH EXTRACTION FOR {len(pdfs)} PENN PDFS (VOTER POV FORMAT)")
    print(f"  OCR Device: {ocr_service.resolve_device()}")
    print("=" * 80, flush=True)

    with session_scope() as session:
        completed_parts = set(session.execute(select(VoterRow.part_number)).scalars().all())
        global_seen_epics = set(session.execute(select(VoterRow.epic)).scalars().all())
    
    print(f"Found {len(completed_parts)} already completed parts in database.")

    for idx, pdf_path in enumerate(pdfs):
        part = part_number_from_name(pdf_path.name)
        if part in completed_parts:
            print(f"[{idx+1}/{len(pdfs)}] Part {part:>2} ({pdf_path.name}) already completed. Skipping to next.")
            continue

        file_id = f"PENN_P{part}_{uuid.uuid4().hex[:6]}"
        t0 = time.perf_counter()

        print(f"\n[{idx+1}/{len(pdfs)}] Processing Part {part:>2} ({pdf_path.name})...", flush=True)

        # 1. Render Cover Page (Page 1)
        rendered_cover = pdf_service.render_page(pdf_path, 1)
        pre_cover = preprocess.preprocess(rendered_cover.image)
        ocr_cover = ocr_service.run_ocr(pre_cover.image, scale=pre_cover.scale, lang="ta")
        cover = roll_metadata.parse_cover(ocr_cover.lines, pdf_path.stem)

        ac_num = cover.ac_number or "58"
        ac_name = cover.ac_name or "பென்னாகரம்"
        ac_res = cover.ac_reservation or "பொது"
        pc_num = cover.pc_number or "10"
        pc_name = cover.pc_name or "தர்மபுரி"
        pc_res = cover.pc_reservation or "பொது"

        # 2. Extract pages via pipeline
        pages = []
        try:
            for page in pipeline.process_pdf(pdf_path, file_id=file_id, template_id="electoral_roll_ta"):
                pages.append(page)
        except Exception as e:
            print(f"  [ERROR] Pipeline failed on {pdf_path.name}: {e}", flush=True)
            continue

        # 3. Apply consensus
        voter_pages = [p for p in pages if p.records]
        if voter_pages:
            consensus.apply_consensus(voter_pages)

        # 4. Save to DB
        station_id = f"PS_{file_id}"
        part_voters_count = 0
        part_deleted_count = 0
        db_voter_rows = []

        with session_scope() as session:
            session.add(FileRow(
                id=file_id,
                name=pdf_path.name,
                size_bytes=pdf_path.stat().st_size,
                stored_path=str(pdf_path),
                page_count=len(pages),
                pages_done=len(pages),
                status="completed",
            ))

            session.add(PollingStationRow(
                id=station_id,
                file_id=file_id,
                part_number=part,
                name=cover.name,
                building_name=cover.name,
                station_number=cover.station_number,
                station_type=cover.station_type,
                address=cover.address,
                ac_number=ac_num,
                ac_name=ac_name,
                pc_number=pc_num,
                pc_name=pc_name,
                district=cover.district or "தர்மபுரி",
                taluk=cover.taluk or "பென்னாகரம்",
                pincode=cover.pincode or "",
                total_electors=cover.counts.total,
                male_electors=cover.counts.male,
                female_electors=cover.counts.female,
                third_gender_electors=cover.counts.third_gender,
                serial_start=cover.serial_start,
                serial_end=cover.serial_end,
                section_details=cover.section_details,
                payload=cover.model_dump(),
            ))

            for page in pages:
                save_page(session, page, file_id)

            for page in pages:
                if page.page_type not in ("voter_list_page", "supplement_page", "supplement_grid"):
                    continue

                sec_name = (page.payload or {}).get("section_name", "") if hasattr(page, "payload") else ""

                for rec in page.records:
                    f = rec.fields
                    serial_val = (f.get("serial").value if f.get("serial") else "").strip()
                    epic_val = (f.get("epic").value if f.get("epic") else "").strip()
                    name_val = (f.get("name").value if f.get("name") else "").strip()
                    rel_type = (f.get("relation_type").value if f.get("relation_type") else "").strip()
                    rel_name = (f.get("relation_name").value if f.get("relation_name") else "").strip()
                    house_val = (f.get("house_number").value if f.get("house_number") else "").strip()
                    age_val = (f.get("age").value if f.get("age") else "").strip()
                    raw_gender = (f.get("gender").value if f.get("gender") else "").strip()
                    gender_val = translate_gender(raw_gender)

                    is_del = False
                    del_reason = ""
                    if f.get("is_deleted") and f.get("is_deleted").value in ("True", "true", "Yes", "yes", True):
                        is_del = True
                        del_reason = (f.get("deletion_reason").value if f.get("deletion_reason") else "").strip()
                        part_deleted_count += 1

                    db_epic = epic_val or f"TEMP_P{part}_{page.page_number}_{rec.index:02d}"
                    if db_epic in global_seen_epics:
                        db_epic = f"{db_epic}_{part}_{uuid.uuid4().hex[:4]}"
                    global_seen_epics.add(db_epic)

                    v_id = f"V_{file_id}_{page.page_number}_{rec.index:02d}"
                    search_str = f"{db_epic} {name_val} {rel_name} {house_val} {serial_val} Part {part} {sec_name} {pdf_path.name}".lower()

                    v_row = VoterRow(
                        id=v_id,
                        epic=db_epic,
                        serial=int(serial_val) if serial_val.isdigit() else None,
                        name=name_val,
                        relation_type=rel_type,
                        relation_name=rel_name,
                        house_number=house_val,
                        age=int(age_val) if age_val.isdigit() else None,
                        gender="Male" if gender_val == "ஆண்" else "Female" if gender_val == "பெண்" else gender_val,
                        part_number=part,
                        constituency=f"{ac_num}-{ac_name}",
                        section_name=sec_name,
                        source_record_id=rec.id,
                        source_page_id=page.id,
                        source_file_id=file_id,
                        source_file_name=pdf_path.name,
                        page_number=page.page_number,
                        page_id=page.id,
                        polling_station_id=station_id,
                        is_supplement=page.page_type in ("supplement_page", "supplement_grid"),
                        is_deleted=is_del,
                        deletion_reason=del_reason,
                        verified=True,
                        search_text=search_str,
                    )
                    db_voter_rows.append(v_row)
                    part_voters_count += 1

            session.add_all(db_voter_rows)

        dt = time.perf_counter() - t0
        print(f"  Part {part:>2} DONE: {part_voters_count} voters ({part_deleted_count} deleted) stored in {dt:.1f}s", flush=True)

    print("\n--- EXPORTING ALL PARTS TO CSV & JSON (VOTER POV) ---", flush=True)
    export_all_tables_from_db()

def export_all_tables_from_db():
    with session_scope() as session:
        stations = session.execute(select(PollingStationRow).order_by(PollingStationRow.part_number)).scalars().all()
        voters = session.execute(select(VoterRow).order_by(VoterRow.part_number, VoterRow.serial)).scalars().all()
        files = {f.id: f.name for f in session.execute(select(FileRow)).scalars().all()}

    # --- TABLE 1 & 2 Map ---
    t1_list = []
    t2_list = []
    stations_map = {}
    counts_map = {}

    for ps in stations:
        p = ps.payload or {}
        part = ps.part_number or ""
        fname = files.get(ps.file_id, f"Part-{part}.pdf")

        ac_res = p.get("ac_reservation") or "பொது"
        pc_res = p.get("pc_reservation") or "பொது"

        t1_row = {
            "கோப்பு பெயர் (File Name)": fname,
            "பாகம் எண்": part,
            "சட்டமன்றத் தொகுதியின் எண்": ps.ac_number or "58",
            "சட்டமன்றத் தொகுதியின் பெயர்": ps.ac_name or "பென்னாகரம்",
            "ஒதுக்கீட்டுத்தகுதி நிலை (சட்டமன்றம்)": ac_res,
            "நாடாளுமன்றத் தொகுதியின் எண்": ps.pc_number or "10",
            "நாடாளுமன்றத் தொகுதியின் பெயர்": ps.pc_name or "தர்மபுரி",
            "ஒதுக்கீட்டுத்தகுதி நிலை (நாடாளுமன்றம்)": pc_res,
            "திருத்தப்படும் ஆண்டு": p.get("revision_year") or "2026",
            "இந்த பாகத்தில், பாகத்தின் கீழ் வரும் பிரிவின் எண் மற்றும் பெயர்": ps.section_details or "",
            "முக்கிய நகரம்/கிராமம்": p.get("main_town") or "",
            "வார்டு": p.get("ward") or "",
            "பஞ்சாயத்து": p.get("panchayat") or "",
            "வட்டம்": ps.taluk or "பென்னாகரம்",
            "மாவட்டம்": ps.district or "தர்மபுரி",
            "அஞ்சல் குறியீட்டு எண்": ps.pincode or "",
        }
        t1_list.append(t1_row)
        stations_map[part] = t1_row

        counts = p.get("counts") or {}
        t2_row = {
            "கோப்பு பெயர் (File Name)": fname,
            "பாகம் எண்": part,
            "தொடங்கும் வரிசை எண்": ps.serial_start or 1,
            "முடியும் வரிசை எண்.": ps.serial_end or (ps.total_electors or len(voters)),
            "ஆண்": ps.male_electors or counts.get("male", 0),
            "பெண்": ps.female_electors or counts.get("female", 0),
            "மூன்றாம் பாலினம்": ps.third_gender_electors or counts.get("third_gender", 0),
            "மொத்தம்": ps.total_electors or counts.get("total", 0),
        }
        t2_list.append(t2_row)
        counts_map[part] = t2_row

    # --- TABLE 3 & MASTER (Voter POV Order) ---
    t3_list = []
    master_list = []

    for v in voters:
        part = v.part_number or ""
        t1_meta = stations_map.get(part, {})
        t2_meta = counts_map.get(part, {})
        sec_name = v.section_name or t1_meta.get("இந்த பாகத்தில், பாகத்தின் கீழ் வரும் பிரிவின் எண் மற்றும் பெயர்", "")
        header_text = f"{t1_meta.get('சட்டமன்றத் தொகுதியின் எண்', '58')}-{t1_meta.get('சட்டமன்றத் தொகுதியின் பெயர்', 'பென்னாகரம்')}\nபிரிவு எண் மற்றும் பெயர் {sec_name}".strip()

        gender_val = "ஆண்" if v.gender in ("Male", "male", "ஆண்") else "பெண்" if v.gender in ("Female", "female", "பெண்") else "மூன்றாம் பாலினம்"

        # Table 3
        t3_row = {
            "வாக்காளர் SNO": v.serial or "",
            "EPIC ID": v.epic,
            "பெயர்": v.name,
            "தந்தை பெயர் / கணவர் பெயர்": v.relation_name,
            "வீட்டு எண்": v.house_number,
            "வயது": v.age or "",
            "பாலினம்": gender_val,
            "சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர்": header_text,
            "பாகம் எண்": part,
            "நீக்கப்பட்டது (is_deleted)": "ஆம்" if v.is_deleted else "இல்லை",
            "நீக்கக் காரணம் (Reason)": v.deletion_reason or "",
            "கோப்பு பெயர் (File Name)": v.source_file_name,
        }
        t3_list.append(t3_row)

        # Master Unified Row (Voter POV: Voter Details -> Location Details -> Constituency Details -> Counts)
        master_row = {
            # 1. Voter personal details
            "வாக்காளர் SNO": v.serial or "",
            "EPIC ID": v.epic,
            "பெயர்": v.name,
            "தந்தை பெயர் / கணவர் பெயர்": v.relation_name,
            "வீட்டு எண்": v.house_number,
            "வயது": v.age or "",
            "பாலினம்": gender_val,

            # 2. Location & Section details
            "சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர்": header_text,
            "பிரிவு விவரம்": sec_name,
            "முக்கிய நகரம்/கிராமம்": t1_meta.get("முக்கிய நகரம்/கிராமம்", ""),
            "வார்டு": t1_meta.get("வார்டு", ""),
            "பஞ்சாயத்து": t1_meta.get("பஞ்சாயத்து", ""),
            "வட்டம்": t1_meta.get("வட்டம்", ""),
            "மாவட்டம்": t1_meta.get("மாவட்டம்", ""),
            "அஞ்சல் குறியீட்டு எண்": t1_meta.get("அஞ்சல் குறியீட்டு எண்", ""),

            # 3. Constituency & Part details
            "பாகம் எண்": part,
            "சட்டமன்றத் தொகுதியின் எண்": t1_meta.get("சட்டமன்றத் தொகுதியின் எண்", ""),
            "சட்டமன்றத் தொகுதியின் பெயர்": t1_meta.get("சட்டமன்றத் தொகுதியின் பெயர்", ""),
            "ஒதுக்கீட்டுத்தகுதி நிலை (சட்டமன்றம்)": t1_meta.get("ஒதுக்கீட்டுத்தகுதி நிலை (சட்டமன்றம்)", ""),
            "நாடாளுமன்றத் தொகுதியின் எண்": t1_meta.get("நாடாளுமன்றத் தொகுதியின் எண்", ""),
            "நாடாளுமன்றத் தொகுதியின் பெயர்": t1_meta.get("நாடாளுமன்றத் தொகுதியின் பெயர்", ""),
            "ஒதுக்கீட்டுத்தகுதி நிலை (நாடாளுமன்றம்)": t1_meta.get("ஒதுக்கீட்டுத்தகுதி நிலை (நாடாளுமன்றம்)", ""),
            "திருத்தப்படும் ஆண்டு": t1_meta.get("திருத்தப்படும் ஆண்டு", ""),

            # 4. Summary counts
            "தொடங்கும் வரிசை எண்": t2_meta.get("தொடங்கும் வரிசை எண்", ""),
            "முடியும் வரிசை எண்.": t2_meta.get("முடியும் வரிசை எண்.", ""),
            "ஆண் (மொத்தம்)": t2_meta.get("ஆண்", ""),
            "பெண் (மொத்தம்)": t2_meta.get("பெண்", ""),
            "மூன்றாம் பாலினம் (மொத்தம்)": t2_meta.get("மூன்றாம் பாலினம்", ""),
            "மொத்தம் (வாக்காளர்கள்)": t2_meta.get("மொத்தம்", ""),

            # 5. Provenance
            "நீக்கப்பட்டது": "ஆம்" if v.is_deleted else "இல்லை",
            "நீக்கக் காரணம்": v.deletion_reason or "",
            "கோப்பு பெயர்": v.source_file_name,
        }
        master_list.append(master_row)

    # Write files
    t1_csv = OUTPUT_DIR / "Table1_Part_Details.csv"
    with open(t1_csv, "w", encoding="utf-8-sig", newline="") as f:
        if t1_list:
            writer = csv.DictWriter(f, fieldnames=list(t1_list[0].keys()))
            writer.writeheader()
            writer.writerows(t1_list)
    print(f"  [OK] Table 1 exported: {t1_csv} ({len(t1_list)} parts)")

    t2_csv = OUTPUT_DIR / "Table2_Counts_Summary.csv"
    with open(t2_csv, "w", encoding="utf-8-sig", newline="") as f:
        if t2_list:
            writer = csv.DictWriter(f, fieldnames=list(t2_list[0].keys()))
            writer.writeheader()
            writer.writerows(t2_list)
    print(f"  [OK] Table 2 exported: {t2_csv} ({len(t2_list)} summaries)")

    t3_csv = OUTPUT_DIR / "Table3_Voters_List.csv"
    with open(t3_csv, "w", encoding="utf-8-sig", newline="") as f:
        if t3_list:
            writer = csv.DictWriter(f, fieldnames=list(t3_list[0].keys()))
            writer.writeheader()
            writer.writerows(t3_list)
    print(f"  [OK] Table 3 exported: {t3_csv} ({len(t3_list):,} voters)")

    master_csv = OUTPUT_DIR / "Master_Voters_Unified.csv"
    with open(master_csv, "w", encoding="utf-8-sig", newline="") as f:
        if master_list:
            writer = csv.DictWriter(f, fieldnames=list(master_list[0].keys()))
            writer.writeheader()
            writer.writerows(master_list)
    print(f"  [OK] Master Unified exported: {master_csv} ({len(master_list):,} records)")

    full_json = OUTPUT_DIR / "Electoral_Roll_Extraction_Full.json"
    with open(full_json, "w", encoding="utf-8") as f:
        json.dump({
            "TABLE_1_PART_DETAILS": t1_list,
            "TABLE_2_COUNTS_SUMMARY": t2_list,
            "TABLE_3_VOTERS_LIST": t3_list,
        }, f, ensure_ascii=False, indent=2)
    print(f"  [OK] Full JSON exported: {full_json}")

if __name__ == "__main__":
    run_batch()
