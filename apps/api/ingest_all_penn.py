"""Ingest every Penn PDF into the database, with format diagnostics.

Reuses the proven extraction path (`pipeline.process_pdf` +
`electoral_roll_ta`) but differs from `extract_all_penn.py` in three ways the
current task needs:

* it processes **all** parts, not "resume from 18";
* it writes the deletion verdict into the real ``is_deleted`` /
  ``deletion_reason`` columns rather than folding it into a notes string, so
  the app's deletion badge, filter, export and assistant actually populate;
* it records a per-page diagnostic (type, record count, errors) and flags
  format anomalies — a voter-bearing page that yielded nothing, an unexpected
  page classification, an outright error — so a new layout shows up as data
  rather than as silently missing voters.

Run (GPU is auto-detected):
    .venv/Scripts/python.exe ingest_all_penn.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from app.db import Base, SessionLocal, VoterRow, engine  # noqa: E402
from app.services import consensus, ocr_service, pipeline  # noqa: E402

PDF_DIR = Path(r"D:/OCR/PDF/Penn PDF")
CONSTITUENCY = "58-பென்னாகரம்"
DISTRICT = "தர்மபுரி (Dharmapuri)"

#: Page types that are supposed to carry voter records. A page classified as
#: one of these but yielding nothing is the signal of a layout the parser did
#: not understand — the "new format" to look at.
VOTER_BEARING = {"voter_list_page", "voter_grid", "supplement_page", "supplement_grid"}


def part_of(filename: str) -> str:
    m = re.search(r"-TAM-(\d+)-", filename)
    return m.group(1) if m else "0"


def _v(fields, key: str, default: str = "") -> str:
    fv = fields.get(key)
    return (fv.value if fv is not None else default) or default


def process_pdf_with_diag(pdf_path: Path, part: str) -> tuple[list[dict], list[dict]]:
    """Extract one PDF into voter rows plus a per-page diagnostic list."""
    file_id = f"TAM-{part}"
    pages, diag = [], []
    t0 = time.perf_counter()

    for page in pipeline.process_pdf(pdf_path, file_id=file_id, template_id="electoral_roll_ta"):
        d = {
            "part": part, "page": page.page_number, "type": page.page_type,
            "records": len(page.records), "error": (page.error or "")[:120],
            "ocr_ms": page.ocr_ms, "class_conf": round(page.classification_confidence, 2),
        }
        # Anomaly: a page that should hold voters but produced none, or an error.
        if page.error:
            d["anomaly"] = "error"
        elif page.page_type in VOTER_BEARING and not page.records:
            d["anomaly"] = "voter_page_no_records"
        diag.append(d)
        if page.records:
            pages.append(page)

    if pages:
        consensus.apply_consensus(pages)

    rows = []
    for page in pages:
        for rec in page.records:
            f = rec.fields
            rows.append({
                "serial": _v(f, "serial"),
                "epic": _v(f, "epic"),
                "name": _v(f, "name"),
                "relation_type": _v(f, "relation_type"),
                "relation_name": _v(f, "relation_name"),
                "house_number": _v(f, "house_number"),
                "age": _v(f, "age"),
                "gender": _v(f, "gender"),
                "is_deleted": _v(f, "is_deleted", "No") == "Yes",
                "deletion_reason": _v(f, "deletion_reason"),
                "part_number": _v(f, "part_number") or part,
                "page_number": page.page_number,
                "source_file_name": pdf_path.name,
                "confidence": round(rec.mean_confidence, 3),
            })

    dt = time.perf_counter() - t0
    voters = len(rows)
    deleted = sum(1 for r in rows if r["is_deleted"])
    anomalies = [d for d in diag if d.get("anomaly")]
    print(f"  Part {part:>3}: {voters:>4} voters, {deleted:>3} deleted, "
          f"{len(anomalies):>2} anomalies, {dt:5.1f}s  ({dt/max(1,len(diag)):.2f}s/pg)")
    return rows, diag


def save_to_db(rows: list[dict]) -> int:
    """Replace the affected parts' voters. Deletion goes to real columns."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        parts = {r["part_number"] for r in rows}
        if parts:
            session.query(VoterRow).filter(
                VoterRow.part_number.in_(parts)
            ).delete(synchronize_session=False)

        seen: set[str] = set()
        built = []
        for idx, r in enumerate(rows):
            part = r["part_number"] or "0"
            vid = f"VOTER_P{part}_{idx + 1:05d}"
            epic = (r["epic"] or "").strip() or f"TEMP_P{part}_{idx + 1:05d}"
            if epic in seen:  # the voters table enforces EPIC uniqueness
                epic = f"{epic}_{vid}"
            seen.add(epic)

            ser = r["serial"].strip() if isinstance(r["serial"], str) else str(r["serial"])
            age = r["age"].strip() if isinstance(r["age"], str) else str(r["age"])
            search = (
                f"{epic} {r['name']} {r['relation_name']} {r['house_number']} "
                f"{ser} Part {part} {r['source_file_name']}"
            ).lower()

            built.append(VoterRow(
                id=vid, epic=epic,
                serial=int(ser) if ser.isdigit() else None,
                name=r["name"], relation_type=r["relation_type"],
                relation_name=r["relation_name"], house_number=r["house_number"],
                age=int(age) if age.isdigit() else None,
                gender=r["gender"], part_number=part, constituency=CONSTITUENCY,
                is_deleted=r["is_deleted"], deletion_reason=r["deletion_reason"],
                page_number=r["page_number"], source_file_name=r["source_file_name"],
                notes=f"District: {DISTRICT}", search_text=search,
            ))

        session.add_all(built)
        session.commit()
        return len(built)
    finally:
        session.close()


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    pdfs = sorted(
        [p for p in PDF_DIR.iterdir() if p.suffix.lower() == ".pdf"],
        key=lambda p: int(part_of(p.name) or "0"),
    )
    if only:
        pdfs = [p for p in pdfs if part_of(p.name) == only]

    print("=" * 70)
    print(f"  INGEST {len(pdfs)} PENN PDFs  ->  device: {ocr_service.resolve_device()}")
    print("=" * 70)

    all_rows, all_diag, stats = [], [], {}
    t0 = time.perf_counter()
    for pdf in pdfs:
        part = part_of(pdf.name)
        try:
            rows, diag = process_pdf_with_diag(pdf, part)
        except Exception as exc:  # one bad PDF must not sink the batch
            print(f"  Part {part:>3}: FAILED — {type(exc).__name__}: {exc}")
            stats[part] = {"voters": 0, "error": f"{type(exc).__name__}: {exc}"}
            continue
        all_rows.extend(rows)
        all_diag.extend(diag)
        stats[part] = {
            "voters": len(rows),
            "deleted": sum(1 for r in rows if r["is_deleted"]),
            "anomalies": sum(1 for d in diag if d.get("anomaly")),
            "pages": len(diag),
        }

    stored = save_to_db(all_rows)
    dt = time.perf_counter() - t0

    # Diagnostics for the format analysis that follows.
    page_types: dict[str, int] = {}
    for d in all_diag:
        page_types[d["type"]] = page_types.get(d["type"], 0) + 1
    anomalies = [d for d in all_diag if d.get("anomaly")]

    report = {
        "device": ocr_service.resolve_device(),
        "pdfs": len(pdfs),
        "voters_extracted": len(all_rows),
        "voters_stored": stored,
        "deleted": sum(1 for r in all_rows if r["is_deleted"]),
        "elapsed_sec": round(dt, 1),
        "page_type_distribution": page_types,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "per_part": stats,
    }
    Path("ingest_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 70)
    print(f"  {len(all_rows):,} voters extracted, {stored:,} stored, "
          f"{report['deleted']:,} deleted, {len(anomalies)} anomalies in {dt/60:.1f}min")
    print(f"  page types: {page_types}")
    print(f"  report -> ingest_report.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
