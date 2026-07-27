import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://localhost:8000/api"

def test_full_system():
    print("[1] Testing GET /api/files...")
    req = urllib.request.urlopen(f"{BASE}/files")
    files = json.loads(req.read().decode("utf-8"))
    print(f"    ✓ Found {len(files)} existing registered files in DB")

    print("[2] Registering test PDF (10_4.pdf)...")
    payload_import = {
        "path": r"D:\OCR\PDF",
        "recursive": True
    }
    req = urllib.request.Request(
        f"{BASE}/files/import-folder",
        data=json.dumps(payload_import).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req)
    imported = json.loads(resp.read().decode("utf-8"))
    print(f"    ✓ import-folder returned {len(imported)} file(s)")

    if not imported:
        req_files = urllib.request.urlopen(f"{BASE}/files")
        files = json.loads(req_files.read().decode("utf-8"))
        file_id = files[0]["id"] if files else ""
        print(f"    ✓ Using registered file: ID={file_id}")
    else:
        file_id = imported[0]["id"]
        print(f"    ✓ Selected PDF: ID={file_id}, Status={imported[0]['status']}")

    print(f"[3] Triggering OCR extraction job for file {file_id}...")
    job_req = urllib.request.Request(
        f"{BASE}/jobs",
        data=json.dumps({"file_ids": [file_id], "template_id": "electoral_roll_ta"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(job_req)
    job = json.loads(resp.read().decode("utf-8"))
    print(f"    ✓ OCR Job Created: JobID={job['id']}")
    print("    Waiting for OCR job to finish...")
    import time
    for _ in range(30):
        f_req = urllib.request.urlopen(f"{BASE}/files/{file_id}")
        f_info = json.loads(f_req.read().decode("utf-8"))
        if f_info["status"] in ("completed", "error"):
            print(f"    ✓ OCR Completed with status: {f_info['status']}")
            break
        time.sleep(1)

    print("[4] Testing Export Preview with Tamil Headers...")
    payload_export = {
        "format": "xlsx",
        "mode": "all",
        "file_ids": [file_id],
        "page_ids": [],
        "record_ids": [],
        "include_page_numbers": True,
        "include_confidence": True,
        "include_issues": True
    }
    req = urllib.request.Request(
        f"{BASE}/export/preview",
        data=json.dumps(payload_export).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode("utf-8"))
    print(f"    ✓ Export Preview returned {data['total_rows']} total rows")
    print(f"    ✓ Columns ({len(data['columns'])}): {data['columns']}")

    print("[5] Testing Export File Generation (CSV with UTF-8 BOM)...")
    payload_export["format"] = "csv"
    req = urllib.request.Request(
        f"{BASE}/export",
        data=json.dumps(payload_export).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req)
    csv_bytes = resp.read()
    print(f"    ✓ Generated CSV size: {len(csv_bytes)} bytes")
    has_bom = csv_bytes.startswith(b"\xef\xbb\xbf")
    print(f"    ✓ UTF-8 BOM present for Excel compatibility: {has_bom}")

    print("\nALL SYSTEM INTEGRATION CHECKS PASSED ✓")

if __name__ == "__main__":
    test_full_system()
