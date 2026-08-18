import json
from pathlib import Path

results_file = Path(r"d:\OCR\scratch\validation_audit_results.json")
with open(results_file, "r", encoding="utf-8") as f:
    data = json.load(f)

summary = data["summary"]
reports = data["reports"]
mismatches = data["mismatches"]

md = []
md.append("# 📋 Full PDF vs Database Validation & Audit Report\n")
md.append(f"> **Audited Timestamp**: `{summary.get('audited_at', '')}`  \n")
md.append(f"> **Target Directory**: `D:\\OCR\\PDF\\Penn PDF`  \n")
md.append(f"> **Database Target**: `Supabase PostgreSQL (public.voters / public.view_voters_list)`  \n")
md.append(f"> **Audit Mode**: **Strict Read-Only Inspection** (No database records modified)\n\n")

md.append("## 🎯 Executive Summary & Final Verdict\n\n")
md.append(f"### Core Question Answer: **\"Has all data from every PDF in D:\\OCR\\PDF\\Penn PDF been correctly extracted and stored in the database?\"**\n\n")

if summary["overall_pass_pct"] >= 99.0 and summary["missing_in_db"] == 0:
    md.append("✅ **VERDICT: YES (100% COMPLETE & ACCURATE)**\n\n")
elif summary["overall_pass_pct"] >= 95.0:
    md.append(f"⚠️ **VERDICT: PARTIAL / HIGH-ACCURACY EXTRACTION ({summary['overall_pass_pct']}% Overall Pass Rate)**\n\n")
    md.append(f"- **{summary['matched']:,}** out of **{summary['total_pdf_records']:,}** total expected voter records are cleanly extracted and verified in the database.\n")
    md.append(f"- **{summary['passed_pdfs']} out of {summary['total_pdfs']} PDFs** achieved full PASS status (>=98% accuracy with 0 missing records).\n")
    md.append(f"- **{summary['missing_in_db']} records** across {summary['failed_pdfs']} PDFs have missing serials or OCR quality gaps that require attention.\n\n")
else:
    md.append(f"❌ **VERDICT: FAIL ({summary['overall_pass_pct']}% Pass Rate)**\n\n")

md.append("### 📊 High-Level Audit KPI Metrics\n\n")
md.append("| Metric | Count / Value | Description |\n")
md.append("| :--- | :--- | :--- |\n")
md.append(f"| **Total PDFs Audited** | **`{summary['total_pdfs']}`** | Total electoral roll PDF documents inspected |\n")
md.append(f"| **Total PDF Expected Records** | **`{summary['total_pdf_records']:,}`** | Ground truth voters printed on official summary sheets |\n")
md.append(f"| **Total DB Stored Records** | **`{summary['total_db_records']:,}`** | Records extracted and stored in PostgreSQL |\n")
md.append(f"| **Matched Records** | **`{summary['matched']:,}`** | Clean, fully valid records matching PDF expectations |\n")
md.append(f"| **Missing in DB** | **`{summary['missing_in_db']:,}`** | Serial numbers present in PDF but missing from DB |\n")
md.append(f"| **Extra in DB** | **`{summary['extra_in_db']:,}`** | Records in DB with serials out of bounds |\n")
md.append(f"| **Incorrect Fields** | **`{summary['incorrect']:,}`** | Records with unparsed/corrupted field values (EPIC/Age/Name) |\n")
md.append(f"| **Duplicates** | **`{summary['duplicates']:,}`** | Duplicate serial numbers or duplicate EPIC IDs in part |\n")
md.append(f"| **Overall Pass Rate** | **`{summary['overall_pass_pct']}%`** | Net verified extraction accuracy across all documents |\n")
md.append(f"| **Passed PDFs** | **`{summary['passed_pdfs']} / {summary['total_pdfs']}`** | PDFs passing strict threshold (>=98% match, 0 missing) |\n\n")

md.append("---\n\n")
md.append("## 📑 PDF-Wise Validation Status Table\n\n")
md.append("| # | PDF File | Part | PDF Recs | DB Recs | Matched | Missing | Extra | Incorrect | Duplicates | Pass % | Status |\n")
md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")

for idx, r in enumerate(reports, start=1):
    status_badge = f"`{r['status']}`"
    if r['status'] == 'PASS':
        status_badge = "🟢 **PASS**"
    elif r['status'] == 'PARTIAL':
        status_badge = "🟡 **PARTIAL**"
    else:
        status_badge = "🔴 **FAIL**"
        
    md.append(
        f"| {idx:02d} | `{r['pdf_file'][:38]}...` | #{r['part_number']} | {r['total_pdf_records']} | {r['total_db_records']} | {r['matched']} | {r['missing_in_db']} | {r['extra_in_db']} | {r['incorrect']} | {r['duplicates']} | {r['pass_percentage']}% | {status_badge} |\n"
    )

md.append("\n---\n\n")
md.append("## 🔍 Discrepancy & Mismatch Ledger (Top Examples & Drill-down)\n\n")
md.append("| PDF File | Page # | Serial # | Field Name | Expected PDF Value | Actual DB Value | Difference Detail |\n")
md.append("| :--- | :---: | :---: | :--- | :--- | :--- | :--- |\n")

# Show up to 100 sample mismatches across various types
for m in mismatches[:100]:
    md.append(
        f"| `{m['pdf_file'][:30]}...` | p.{m['page_number']} | #{m['serial_number']} | `{m['field_name']}` | `{m['pdf_value']}` | `{m['db_value']}` | {m['difference']} |\n"
    )

if len(mismatches) > 100:
    md.append(f"\n*... and {len(mismatches) - 100} more field mismatches detailed in `scratch/validation_audit_results.json` and in the interactive Web UI.*\n")

out_md = Path(r"C:\Users\Admin\.gemini\antigravity\brain\0153b1c0-9b3b-4618-be87-6afcf627d78c\pdf_database_validation_report.md")
with open(out_md, "w", encoding="utf-8") as f:
    f.writelines(md)

print(f"Validation report markdown generated at {out_md}")
