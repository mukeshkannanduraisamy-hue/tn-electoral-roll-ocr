import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path("apps/api").resolve()))

from app.db import session_scope, RecordRow, PageRow, FileRow, VoterRow, row_to_record
from app.schemas.voters import normalise_epic

with session_scope() as session:
    records = session.query(RecordRow).all()
    voters = session.query(VoterRow).all()
    file_map = {f.id: f.name for f in session.query(FileRow).all()}
    
    existing_voters_map = {v.epic: v for v in voters}
    seen_in_batch = set()

    no_epic_list = []
    dup_epic_list = []

    for row in records:
        rec = row_to_record(row)
        fields = rec.fields or {}
        epic_val = fields.get("epic", {}).value if fields.get("epic") else ""
        name_val = fields.get("name", {}).value if fields.get("name") else ""
        epic = normalise_epic(epic_val)

        file_name = file_map.get(row.file_id, row.file_id)

        if not epic:
            no_epic_list.append({
                "id": row.id,
                "file": file_name,
                "page": row.page_number,
                "name": name_val,
                "reason": "Missing EPIC Number (e.g. Header, Footer, Cover page, or unread EPIC cell)"
            })
        elif epic in seen_in_batch or epic in existing_voters_map:
            dup_epic_list.append({
                "id": row.id,
                "file": file_name,
                "page": row.page_number,
                "epic": epic,
                "name": name_val,
                "reason": "Duplicate EPIC Number (already promoted or repeated across rolls)"
            })
        else:
            seen_in_batch.add(epic)

    print(f"=== SKIPPED RECORDS ANALYSIS ===")
    print(f"Total Raw Extracted Records: {len(records)}")
    print(f"1. Missing EPIC (Non-voter cells/Headers/Summaries): {len(no_epic_list)}")
    print(f"2. Duplicate EPIC (Repeated voter cards across documents): {len(dup_epic_list)}")

    print("\n--- Sample 10 Missing EPIC Records ---")
    for item in no_epic_list[:10]:
        print(f"  Page {item['page']} in {item['file']} | Name: '{item['name']}' | Reason: {item['reason']}")

    print("\n--- Sample 10 Duplicate EPIC Records ---")
    for item in dup_epic_list[:10]:
        print(f"  EPIC: {item['epic']} | Name: '{item['name']}' | Page {item['page']} in {item['file']}")
