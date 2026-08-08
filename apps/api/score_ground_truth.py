"""Ground-truth accuracy harness — scorer.

Joins a reviewer's corrections against the OCR output and reports the numbers
the completeness metric cannot: real per-field exact-match accuracy and
character error rate (CER), and — the question that decides whether
confidence-flagging is worth building — whether low confidence actually
predicts a wrong read.

It also emits `gt_correction_dict.json`: every (wrong OCR value -> correct
value) pair the reviewer fixed, which seeds the phase-2 post-OCR dictionary.

Usage:
    .venv/Scripts/python.exe score_ground_truth.py gt_batch1_manifest.json gt_corrections.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from rapidfuzz.distance import Levenshtein  # noqa: E402


def cer(ocr: str, truth: str) -> float:
    """Character error rate against the truth string. 0.0 is perfect."""
    truth = truth or ""
    if not truth:
        return 0.0 if not ocr else 1.0
    return Levenshtein.distance(ocr or "", truth) / len(truth)


def band(conf: float) -> str:
    return "high (>=0.85)" if conf >= 0.85 else "mid (0.60-0.85)" if conf >= 0.60 else "low (<0.60)"


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: score_ground_truth.py <manifest.json> <corrections.json>")

    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    corrections = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    # id "record_id::field" -> (ocr, confidence)
    ocr_by_id: dict[str, tuple[str, float]] = {}
    for r in manifest:
        for key, f in r["fields"].items():
            ocr_by_id[f"{r['record_id']}::{key}"] = (f["ocr"], float(f["confidence"]))

    per_field = defaultdict(lambda: {"n": 0, "exact": 0, "cer_sum": 0.0})
    per_band = defaultdict(lambda: {"n": 0, "wrong": 0})
    correction_dict: dict[str, str] = {}
    scored = wrong = 0

    for fid, truth in corrections.items():
        if fid not in ocr_by_id:
            continue
        ocr, conf = ocr_by_id[fid]
        field = fid.split("::", 1)[1]
        truth = (truth or "").strip()
        ocr_s = (ocr or "").strip()

        scored += 1
        exact = ocr_s == truth
        c = cer(ocr_s, truth)

        pf = per_field[field]
        pf["n"] += 1
        pf["exact"] += 1 if exact else 0
        pf["cer_sum"] += c

        pb = per_band[band(conf)]
        pb["n"] += 1
        if not exact:
            pb["wrong"] += 1
            wrong += 1
            if ocr_s and truth and ocr_s != truth:
                correction_dict[ocr_s] = truth

    if not scored:
        raise SystemExit("No overlap between manifest and corrections — wrong files?")

    # ---- report ---------------------------------------------------------
    print("=" * 66)
    print(f"  GROUND-TRUTH ACCURACY  —  {scored} fields scored, {wrong} wrong")
    print("=" * 66)
    overall_exact = 1 - wrong / scored
    overall_cer = sum(pf["cer_sum"] for pf in per_field.values()) / scored
    print(f"\n  Exact-match accuracy : {overall_exact:6.2%}")
    print(f"  Character error rate : {overall_cer:6.2%}   (char-level accuracy {1-overall_cer:.2%})")

    print("\n  Per field (worst first):")
    print(f"    {'field':16} {'n':>4} {'exact%':>8} {'CER':>7}")
    for field, pf in sorted(per_field.items(), key=lambda kv: kv[1]["exact"] / max(1, kv[1]["n"])):
        ex = pf["exact"] / pf["n"]
        cr = pf["cer_sum"] / pf["n"]
        print(f"    {field:16} {pf['n']:>4} {ex:>7.1%} {cr:>7.1%}")

    print("\n  Does confidence predict errors?")
    print(f"    {'band':18} {'n':>4} {'wrong':>6} {'error rate':>11}")
    for b in ("high (>=0.85)", "mid (0.60-0.85)", "low (<0.60)"):
        pb = per_band.get(b)
        if not pb or not pb["n"]:
            continue
        print(f"    {b:18} {pb['n']:>4} {pb['wrong']:>6} {pb['wrong']/pb['n']:>10.1%}")
    print("    (if the low band's error rate is much higher, confidence-flagging is worth building)")

    out = Path("gt_correction_dict.json")
    out.write_text(json.dumps(correction_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Wrote {out}: {len(correction_dict)} (wrong -> correct) pairs to seed phase-2 correction.")


if __name__ == "__main__":
    main()
