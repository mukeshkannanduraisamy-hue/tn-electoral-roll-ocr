import sys
from pathlib import Path

sys.path.insert(0, str(Path("apps/api").resolve()))

from app.db import session_scope, UserRow, VoterRow
from app.routers.voters import promote_records
from app.schemas.voters import PromotionRequest

with session_scope() as s:
    u = s.query(UserRow).first()
    req = PromotionRequest(all_documents=True, only_clean=False, on_conflict="skip")
    res = promote_records(req, s, u)
    print(f"Speed Insert Summary: Created={res.created}, Updated={res.updated}, Skipped={res.skipped}")
    voter_count = s.query(VoterRow).count()
    print(f"Total Promoted Voters in Database: {voter_count}")
