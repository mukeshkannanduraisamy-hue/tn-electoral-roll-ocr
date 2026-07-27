import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = "http://localhost:8000/api"

def test_reocr():
    print("[1] Fetching registered files...")
    req = urllib.request.urlopen(f"{BASE}/files")
    files = json.loads(req.read().decode("utf-8"))
    if not files:
        print("    No files in DB")
        return
    completed_files = [f for f in files if f["status"] == "completed"]
    if not completed_files:
        print("    Running OCR job first...")
        file_id = files[0]["id"]
        job_req = urllib.request.Request(
            f"{BASE}/jobs",
            data=json.dumps({"file_ids": [file_id], "template_id": "auto"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(job_req)
        import time
        for _ in range(30):
            f_req = urllib.request.urlopen(f"{BASE}/files/{file_id}")
            f_info = json.loads(f_req.read().decode("utf-8"))
            if f_info["status"] == "completed":
                break
            time.sleep(1)
    else:
        file_id = completed_files[0]["id"]
    print(f"    ✓ Selected File ID: {file_id}")

    print("[2] Fetching pages for file...")
    req_pages = urllib.request.urlopen(f"{BASE}/files/{file_id}/pages")
    pages = json.loads(req_pages.read().decode("utf-8"))
    if not pages:
        print("    No pages extracted for file yet")
        return
    page_id = pages[0]["id"]
    print(f"    ✓ Selected Page ID: {page_id}")

    print(f"[3] Triggering single-page re-OCR on page {page_id}...")
    req_reocr = urllib.request.Request(
        f"{BASE}/pages/{page_id}/reocr?template_id=auto&upscale=2.5",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req_reocr)
    page_res = json.loads(resp.read().decode("utf-8"))
    print(f"    ✓ Single Page Re-OCR Success! Records={len(page_res['records'])}, OCR ms={page_res['ocr_ms']}")

if __name__ == "__main__":
    test_reocr()
