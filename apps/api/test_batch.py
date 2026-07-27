import sys
import json
from pathlib import Path

# Force stdout to UTF-8 on Windows
sys.stdout.reconfigure(encoding='utf-8')

from app.services import pipeline

def run_test():
    pdf_dir = Path(r"D:\OCR\PDF")
    test_pdfs = [
        pdf_dir / "2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-10-WI" / "10_4.pdf",
        pdf_dir / "2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-11-WI" / "11_4.pdf",
        pdf_dir / "2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-12-WI" / "12_4.pdf",
        pdf_dir / "2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-13-WI" / "13_4.pdf",
        pdf_dir / "2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-14-WI" / "14_4.pdf",
    ]
    
    headers = [
        "வரிசை எண்", "அடையாள அட்டை எண்", "பெயர்", "உறவு முறை", 
        "உறவினரின் பெயர்", "வீட்டு எண்", "வயது", "பாலினம்", "நம்பகத்தன்மை", "பிழைகள்"
    ]
    
    results = {}
    out_lines = []
    
    for pdf_path in test_pdfs:
        if not pdf_path.exists():
            print(f"Skipping (not found): {pdf_path}")
            continue
            
        header_banner = f"\n========================================================\nPROCESSING: {pdf_path.name}\n========================================================"
        print(header_banner)
        out_lines.append(header_banner)
        
        page = pipeline.process_page(str(pdf_path), 1, pdf_path.stem, template_id="electoral_roll_ta")
        
        rows = []
        clean_count = 0
        total_records = len(page.records)
        
        tbl_header = " | ".join(headers)
        divider = "-" * 130
        print(tbl_header)
        print(divider)
        out_lines.append(tbl_header)
        out_lines.append(divider)
        
        for rec in page.records:
            f = rec.fields
            s_no = f.get("serial", {}).original_value if "serial" in f else ""
            epic = f.get("epic", {}).original_value if "epic" in f else ""
            name = f.get("name", {}).original_value if "name" in f else ""
            rel_type = f.get("relation_type", {}).original_value if "relation_type" in f else ""
            rel_name = f.get("relation_name", {}).original_value if "relation_name" in f else ""
            house = f.get("house_number", {}).original_value if "house_number" in f else ""
            age = f.get("age", {}).original_value if "age" in f else ""
            gender = f.get("gender", {}).original_value if "gender" in f else ""
            conf = f"{rec.mean_confidence:.2f}"
            all_issues = [i.code for i in rec.issues] + [i.code for fi in f.values() for i in fi.issues]
            issues_str = ", ".join(all_issues) if all_issues else "Clean"
            if not all_issues:
                clean_count += 1
                
            row_str = f"{s_no} | {epic} | {name} | {rel_type} | {rel_name} | {house} | {age} | {gender} | {conf} | {issues_str}"
            print(row_str)
            out_lines.append(row_str)
            
            rows.append({
                "serial": s_no, "epic": epic, "name": name, "relation_type": rel_type,
                "relation_name": rel_name, "house": house, "age": age, "gender": gender,
                "confidence": conf, "issues": issues_str
            })
            
        results[pdf_path.name] = {
            "total": total_records,
            "clean": clean_count,
            "accuracy": (clean_count / total_records * 100) if total_records > 0 else 0,
            "rows": rows
        }
        
    out_json = Path("test_batch_results.json")
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    
    out_txt = Path("test_output.txt")
    out_txt.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\nSaved batch results to {out_json.absolute()} and {out_txt.absolute()}")

if __name__ == "__main__":
    run_test()
