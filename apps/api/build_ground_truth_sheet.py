"""Ground-truth accuracy harness — sheet generator.

The existing eval (`eval_penn_accuracy.py`) measures *completeness*: how many
records are non-empty and pass validation. That is not accuracy. A name OCR'd
as முருகள் instead of முருகன் is still "clean". Real OCR accuracy needs a
human to compare the extracted text against the actual pixels, and this builds
the tool for exactly that.

It samples records spread across the Penn PDFs, crops each field's own image
region (every `FieldValue` carries a `bbox` in rendered-page pixel space), and
writes a self-contained HTML sheet: crop + OCR value + confidence + an editable
"correct value" box pre-filled with the OCR value. A reviewer fixes only the
wrong ones and clicks "Download corrections" — the resulting JSON is scored by
`score_ground_truth.py` and seeds the phase-2 correction dictionary.

Usage:
    .venv/Scripts/python.exe build_ground_truth_sheet.py --records 40 --out gt_batch1
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from io import BytesIO
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import pipeline  # noqa: E402

PENN_DIR = Path(r"D:/OCR/PDF/Penn PDF")

#: The fields worth scoring. name and relation_name are the free-text Tamil
#: fields where OCR errors both matter most and hide from validation; the rest
#: are numeric/enumerated and mostly self-checking, but included so the sheet
#: gives a complete per-field accuracy picture.
FIELD_ORDER = [
    "name",
    "relation_name",
    "relation_type",
    "house_number",
    "age",
    "gender",
    "serial",
    "epic",
]

#: Pages to try per file. The roll's voter grids sit mid-document; 4 and 5 are
#: reliably voter-bearing (the same pages `eval_penn_accuracy.py` samples).
DEFAULT_PAGES = [4, 5]

#: A little context around each crop so the reviewer can see the whole glyph
#: run, not a tight box that clips ascenders/descenders.
CROP_PAD = 6


def _crop_b64(page_img: np.ndarray, bbox, pad: int = CROP_PAD) -> str | None:
    """PNG data-URI for a field's image region, or None if the box is unusable."""
    if bbox is None:
        return None
    h, w = page_img.shape[:2]
    x0 = max(0, int(bbox.x) - pad)
    y0 = max(0, int(bbox.y) - pad)
    x1 = min(w, int(bbox.x + bbox.w) + pad)
    y1 = min(h, int(bbox.y + bbox.h) + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = page_img[y0:y1, x0:x1]
    ok, buf = cv2.imencode(".png", crop[:, :, ::-1] if crop.ndim == 3 else crop)
    if not ok:
        return None
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _load_page_image(page) -> np.ndarray | None:
    """The exact display image the field bboxes are measured against."""
    if not page.image_path:
        return None
    p = settings.pages_dir / page.image_path
    if not p.exists():
        return None
    img = cv2.imread(str(p))  # BGR
    return None if img is None else img[:, :, ::-1]  # -> RGB


def collect(records_target: int, pages: list[int]) -> list[dict]:
    """Sample records across the parts until the target count is reached.

    Round-robin across files so the sample spans scan qualities rather than
    piling onto whichever part happens to sort first.
    """
    pdfs = sorted(PENN_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs under {PENN_DIR}")

    rows: list[dict] = []
    # (pdf_index, page) work queue, interleaved so we spread across parts.
    queue = [(pi, pg) for pg in pages for pi in range(len(pdfs))]

    for pi, pg in queue:
        if len(rows) >= records_target:
            break
        pdf = pdfs[pi]
        try:
            page = pipeline.process_page(str(pdf), pg, file_id=pdf.stem)
        except Exception as exc:  # a bad page must not sink the batch
            print(f"  ! {pdf.name} p{pg}: {type(exc).__name__}: {exc}")
            continue
        if not page.records:
            continue
        img = _load_page_image(page)
        if img is None:
            print(f"  ! {pdf.name} p{pg}: no saved page image, skipping crops")
            continue

        take = min(3, len(page.records))  # a few per page keeps the spread wide
        for rec in page.records[:take]:
            if len(rows) >= records_target:
                break
            fields = {}
            for key in FIELD_ORDER:
                fv = rec.fields.get(key)
                if fv is None or not fv.original_value.strip():
                    continue
                fields[key] = {
                    "ocr": fv.original_value,
                    "confidence": round(float(fv.confidence), 3),
                    "crop": _crop_b64(img, fv.bbox),
                }
            if not fields:
                continue
            rows.append(
                {
                    "part": pdf.stem,
                    "page": pg,
                    "record_id": rec.id,
                    "index": rec.index,
                    "fields": fields,
                }
            )
        print(f"  {pdf.name} p{pg}: +{take} records ({len(rows)} total)")

    return rows


def render_html(rows: list[dict]) -> str:
    """A self-contained review sheet. No server, no external assets."""
    n_fields = sum(len(r["fields"]) for r in rows)
    cards = []
    for r in rows:
        field_rows = []
        for key in FIELD_ORDER:
            f = r["fields"].get(key)
            if not f:
                continue
            conf = f["confidence"]
            conf_cls = "hi" if conf >= 0.85 else "mid" if conf >= 0.6 else "lo"
            crop = (
                f'<img src="{f["crop"]}" alt="crop">'
                if f["crop"]
                else '<span class="nocrop">no crop</span>'
            )
            fid = f'{r["record_id"]}::{key}'
            field_rows.append(
                f"""
        <tr>
          <td class="fkey">{key}</td>
          <td class="crop">{crop}</td>
          <td class="ocr">{_esc(f["ocr"])}</td>
          <td class="conf {conf_cls}">{conf:.2f}</td>
          <td class="fix"><input data-id="{_esc(fid)}" value="{_esc(f["ocr"])}"></td>
        </tr>"""
            )
        cards.append(
            f"""
    <div class="card">
      <div class="chead">{_esc(r["part"])} &middot; page {r["page"]} &middot; record #{r["index"]}</div>
      <table>
        <thead><tr><th>field</th><th>crop</th><th>OCR read</th><th>conf</th><th>correct value (edit if wrong)</th></tr></thead>
        <tbody>{''.join(field_rows)}</tbody>
      </table>
    </div>"""
        )

    return _TEMPLATE.format(
        n_records=len(rows),
        n_fields=n_fields,
        cards="".join(cards),
    )


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_TEMPLATE = """<!doctype html>
<html lang="ta"><head><meta charset="utf-8">
<title>OCR ground-truth review</title>
<style>
  body {{ font-family: 'Noto Sans Tamil', system-ui, sans-serif; margin: 0; background:#0f172a; color:#e2e8f0; }}
  header {{ position:sticky; top:0; background:#1e293b; padding:14px 20px; border-bottom:1px solid #334155; z-index:10; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
  header h1 {{ font-size:15px; margin:0; font-weight:800; }}
  header .stat {{ font-size:12px; color:#94a3b8; }}
  button {{ background:#4f46e5; color:#fff; border:0; padding:9px 16px; border-radius:8px; font-weight:700; cursor:pointer; }}
  button:hover {{ background:#6366f1; }}
  main {{ padding:16px; max-width:1100px; margin:0 auto; }}
  .card {{ background:#1e293b; border:1px solid #334155; border-radius:12px; margin-bottom:14px; overflow:hidden; }}
  .chead {{ padding:8px 14px; font-size:11px; font-weight:700; color:#a5b4fc; background:#0f172a; border-bottom:1px solid #334155; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:#64748b; padding:6px 10px; border-bottom:1px solid #334155; }}
  td {{ padding:7px 10px; border-bottom:1px solid #26314a; vertical-align:middle; }}
  td.fkey {{ font-size:11px; color:#94a3b8; white-space:nowrap; }}
  td.crop img {{ display:block; max-height:40px; background:#fff; border-radius:3px; padding:2px; }}
  td.ocr {{ font-size:15px; }}
  td.conf {{ font-variant-numeric:tabular-nums; font-weight:700; text-align:center; }}
  td.conf.hi {{ color:#34d399; }} td.conf.mid {{ color:#fbbf24; }} td.conf.lo {{ color:#f87171; }}
  td.fix input {{ width:100%; background:#0f172a; border:1px solid #334155; color:#fff; border-radius:6px; padding:6px 9px; font-size:15px; font-family:inherit; }}
  td.fix input:focus {{ outline:none; border-color:#6366f1; }}
  .nocrop {{ font-size:10px; color:#64748b; }}
  .done {{ background:#059669 !important; }}
</style></head>
<body>
<header>
  <h1>OCR ground-truth review</h1>
  <span class="stat">{n_records} records &middot; {n_fields} fields</span>
  <span class="stat">Fix any box whose text does not match the crop. Leave correct ones as they are.</span>
  <button id="dl">Download corrections JSON</button>
</header>
<main>{cards}</main>
<script>
  document.getElementById('dl').addEventListener('click', () => {{
    const out = {{}};
    document.querySelectorAll('input[data-id]').forEach(i => out[i.dataset.id] = i.value);
    const blob = new Blob([JSON.stringify(out, null, 2)], {{type:'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'gt_corrections.json';
    a.click();
    document.getElementById('dl').textContent = 'Downloaded \u2713';
    document.getElementById('dl').classList.add('done');
  }});
</script>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=int, default=40, help="target record count")
    ap.add_argument("--pages", type=int, nargs="+", default=DEFAULT_PAGES)
    ap.add_argument("--out", default="gt_batch1", help="output basename (no extension)")
    args = ap.parse_args()

    print(f"Sampling ~{args.records} records from {PENN_DIR.name}, pages {args.pages}")
    rows = collect(args.records, args.pages)
    if not rows:
        raise SystemExit("No records collected — check the PDF directory and page numbers.")

    html_path = Path(f"{args.out}.html")
    json_path = Path(f"{args.out}_manifest.json")
    html_path.write_text(render_html(rows), encoding="utf-8")
    # Manifest keeps the OCR value + confidence so scoring can join corrections
    # back without re-running OCR. Crops are dropped here to keep it small.
    manifest = [
        {**r, "fields": {k: {kk: vv for kk, vv in v.items() if kk != "crop"}
                         for k, v in r["fields"].items()}}
        for r in rows
    ]
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    n_fields = sum(len(r["fields"]) for r in rows)
    print(f"\nWrote {html_path} ({len(rows)} records, {n_fields} fields)")
    print(f"Wrote {json_path} (manifest for scoring)")
    print("\nOpen the HTML, correct any wrong boxes, click Download, then run:")
    print(f"  .venv/Scripts/python.exe score_ground_truth.py {json_path} gt_corrections.json")


if __name__ == "__main__":
    main()
