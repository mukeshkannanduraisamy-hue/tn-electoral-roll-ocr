"""Complete 3-Table Extraction & Export Pipeline matching User's Exact Format"""
import sys
import re
import json
import csv
from pathlib import Path

# Add apps/api to path
repo_root = Path(r"d:\OCR")
sys.path.insert(0, str(repo_root / "apps" / "api"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.services import pdf_service, preprocess, ocr_service, roll_metadata, pipeline

def translate_gender(gender_str: str) -> str:
    g = (gender_str or "").strip().lower()
    if g in ("male", "m", "ஆண்"):
        return "ஆண்"
    elif g in ("female", "f", "பெண்"):
        return "பெண்"
    elif g in ("third_gender", "third gender", "transgender", "மூன்றாம் பாலினம்", "மூன்றாம்"):
        return "மூன்றாம் பாலினம்"
    return gender_str

def extract_pdf_new_format(pdf_path: Path, output_dir: Path | None = None):
    print(f"\n=======================================================")
    print(f"EXTRACTING: {pdf_path.name}")
    print(f"=======================================================")
    
    # 1. Render Cover Page (Page 1)
    rendered_cover = pdf_service.render_page(pdf_path, 1)
    pre_cover = preprocess.preprocess(rendered_cover.image)
    ocr_cover = ocr_service.run_ocr(pre_cover.image, scale=pre_cover.scale, lang="ta")
    cover = roll_metadata.parse_cover(ocr_cover.lines, pdf_path.stem)
    
    ac_num = cover.ac_number or ""
    ac_name = cover.ac_name or ""
    ac_res = cover.ac_reservation or "பொது"
    pc_num = cover.pc_number or ""
    pc_name = cover.pc_name or ""
    pc_res = cover.pc_reservation or "பொது"

    # --- TABLE 1: 1. திருத்தத்தின் விவரங்கள் , 2. பாகத்தின் விவரங்கள் மற்றும் வாக்குச்சாவடிக்கான பரப்பளவு ---
    table_1 = {
        "சட்டமன்றத் தொகுதியின் எண்": ac_num,
        "சட்டமன்றத் தொகுதியின் பெயர்": ac_name,
        "ஒதுக்கீட்டுத்தகுதி நிலை (சட்டமன்றம்)": ac_res,
        "பாகம் எண்": cover.part_number,
        "நாடாளுமன்றத் தொகுதியின் எண்": pc_num,
        "நாடாளுமன்றத் தொகுதியின் பெயர்": pc_name,
        "ஒதுக்கீட்டுத்தகுதி நிலை (நாடாளுமன்றம்)": pc_res,
        "திருத்தப்படும் ஆண்டு": cover.revision_year or "2026",
        "இந்த பாகத்தில், பாகத்தின் கீழ் வரும் பிரிவின் எண் மற்றும் பெயர்": cover.section_details,
        "முக்கிய நகரம்/கிராமம்": cover.main_town,
        "வார்டு": cover.ward,
        "பஞ்சாயத்து": cover.panchayat,
        "வட்டம்": cover.taluk,
        "மாவட்டம்": cover.district,
        "அஞ்சல் குறியீட்டு எண்": cover.pincode,
    }
    
    print("\n--- TABLE 1 (1. திருத்தத்தின் விவரங்கள் , 2. பாகத்தின் விவரங்கள் மற்றும் வாக்குச்சாவடிக்கான பரப்பளவு) ---")
    for k, v in table_1.items():
        print(f"  {k:<55}: {v}")

    # --- TABLE 2: 4. வாக்காளர்களின் எண்ணிக்கை ---
    table_2 = {
        "தொடங்கும் வரிசை எண்": cover.serial_start if cover.serial_start else 1,
        "முடியும் வரிசை எண்.": cover.serial_end if cover.serial_end else cover.counts.total,
        "ஆண்": cover.counts.male,
        "பெண்": cover.counts.female,
        "மூன்றாம் பாலினம்": cover.counts.third_gender,
        "மொத்தம்": cover.counts.total,
    }

    print("\n--- TABLE 2 (4. வாக்காளர்களின் எண்ணிக்கை) ---")
    for k, v in table_2.items():
        print(f"  {k:<30}: {v}")

    # --- TABLE 3: VOTERS LIST WITH OTHER DETAILS ---
    pages = []
    for page in pipeline.process_pdf(pdf_path, file_id="TEST", template_id="electoral_roll_ta"):
        pages.append(page)
    
    table_3_records = []
    for page in pages:
        if page.page_type not in ("voter_list_page", "supplement_page", "supplement_grid"):
            continue
        
        # Header string for this page: e.g. "58-பென்னாகரம் பிரிவு எண் மற்றும் பெயர் 1-வட்டுவனஅள்ளி (வ.கி) மற்றும் (ஊ), வார்டு 4 அலகட்டு"
        sec_name = (page.payload or {}).get("section_name", "") if hasattr(page, "payload") else ""
        header_text = f"{ac_num}-{ac_name}\nபிரிவு எண் மற்றும் பெயர் {sec_name}".strip()
        
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
            
            # Relation label: தந்தை பெயர் / கணவர் பெயர் / தாய் பெயர்
            rel_key = "தந்தை பெயர்"
            if "husband" in rel_type.lower() or "கணவர்" in rel_type:
                rel_key = "கணவர் பெயர்"
            elif "mother" in rel_type.lower() or "தாய்" in rel_type:
                rel_key = "தாய் பெயர்"
            elif "other" in rel_type.lower() or "இதர" in rel_type:
                rel_key = "காப்பாளர் பெயர்"

            rec_entry = {
                "சட்டமன்றத் தொகுதியின் எண் மற்றும் பெயர்": header_text,
                "வாக்காளர் SNO": serial_val,
                "EPIC ID": epic_val,
                "பெயர்": name_val,
                "தந்தை பெயர்": rel_name,
                "வீட்டு எண்": house_val,
                "வயது": age_val,
                "பாலினம்": gender_val,
            }
            table_3_records.append(rec_entry)

    print(f"\n--- TABLE 3 (VOTERS LIST WITH OTHER DETAILS: {len(table_3_records)} RECORDS) ---")
    print(f"{'வாக்காளர் SNO':<12} | {'EPIC ID':<12} | {'பெயர்':<18} | {'தந்தை பெயர்':<18} | {'வீட்டு எண்':<10} | {'வயது':<5} | {'பாலினம்':<8}")
    print("-" * 95)
    for r in table_3_records[:10]:
        print(f"{r['வாக்காளர் SNO']:<12} | {r['EPIC ID']:<12} | {r['பெயர்']:<18} | {r['தந்தை பெயர்']:<18} | {r['வீட்டு எண்']:<10} | {r['வயது']:<5} | {r['பாலினம்']:<8}")
    if len(table_3_records) > 10:
        print(f"... and {len(table_3_records) - 10} more rows.")

    # Save to JSON
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        res_json = {
            "TABLE_1": table_1,
            "TABLE_2": table_2,
            "TABLE_3": table_3_records,
        }
        json_path = output_dir / f"{pdf_path.stem}_new_format.json"
        json_path.write_text(json.dumps(res_json, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved complete JSON to: {json_path}")

    return table_1, table_2, table_3_records

if __name__ == "__main__":
    penn_part2 = Path(r"D:\OCR\PDF\Penn PDF\2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-2-WI.pdf")
    if penn_part2.exists():
        extract_pdf_new_format(penn_part2, output_dir=Path(r"d:\OCR\scratch"))
