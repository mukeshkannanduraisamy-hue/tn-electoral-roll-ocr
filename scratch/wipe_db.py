import sys
import shutil
from pathlib import Path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "apps" / "api"))

from app.db import session_scope
from sqlalchemy import text

tables = [
    "chat_messages",
    "chat_threads",
    "audit_logs",
    "ocr_blocks",
    "photos",
    "polling_stations",
    "voters",
    "summaries",
    "records",
    "pages",
    "jobs",
    "files",
]

print("=== Starting Database Truncate & File Reset ===", flush=True)
with session_scope() as s:
    table_list = ", ".join(tables)
    s.execute(text(f"TRUNCATE TABLE {table_list} CASCADE;"))
    print("Truncated PostgreSQL data tables.", flush=True)

data_dir = repo_root / "data"
for folder_name in ["pages", "photos", "uploads"]:
    target_dir = data_dir / folder_name
    if target_dir.exists():
        for child in target_dir.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        print(f"Cleared cache directory: {folder_name}/", flush=True)

print("=== Full Data Reset Complete ===", flush=True)
