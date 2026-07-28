#!/usr/bin/env python
"""Extraction pipeline benchmark.

Two things this exists to prevent:

1. Optimising the wrong stage. If OCR inference is 95% of wall time, tuning
   the PDF renderer is wasted effort no matter how satisfying the diff looks.
2. Unfalsifiable speed claims. "3-10x faster" means nothing without a
   recorded baseline on the same hardware, same pages, same accuracy.

Accuracy is measured alongside speed on every run, because a configuration
that is twice as fast and reads fewer fields is not an optimisation.

    python bench.py profile              # where does one page's time go?
    python bench.py concurrency          # sequential vs threads vs processes
    python bench.py upscale              # speed AND accuracy at 2.0 vs 3.0
    python bench.py all --pages 4
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PDF_DIR = Path(r"D:\OCR\PDF")


def sample_pdfs(n: int) -> list[Path]:
    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs under {PDF_DIR}")
    # Skip the tiny part-pages; they finish early and flatter the numbers.
    full = [p for p in pdfs if p.stat().st_size > 300_000]
    return (full or pdfs)[:n]


# ---------------------------------------------------------------------------
# Accuracy -- held constant is the whole point
# ---------------------------------------------------------------------------


@dataclass
class Accuracy:
    records: int = 0
    clean: int = 0
    fields_filled: int = 0
    fields_total: int = 0
    errors: int = 0

    @property
    def fill_rate(self) -> float:
        return self.fields_filled / self.fields_total if self.fields_total else 0.0

    def merge(self, other: "Accuracy") -> None:
        self.records += other.records
        self.clean += other.clean
        self.fields_filled += other.fields_filled
        self.fields_total += other.fields_total
        self.errors += other.errors

    def summary(self) -> str:
        return (f"{self.records} rec, {self.clean} clean, "
                f"fill {self.fill_rate:5.1%}, {self.errors} err")


def score(page) -> Accuracy:
    acc = Accuracy(records=len(page.records))
    for record in page.records:
        errs = record.error_count
        acc.errors += errs
        if errs == 0:
            acc.clean += 1
        for f in record.fields.values():
            acc.fields_total += 1
            if (f.edited_value if f.edited_value is not None else f.original_value):
                acc.fields_filled += 1
    return acc


# ---------------------------------------------------------------------------
# Stage profile
# ---------------------------------------------------------------------------


def cmd_profile(args) -> None:
    """Time each stage of one page, repeated, so the split is trustworthy."""
    from app.config import settings
    from app.services import layout_service, ocr_service, pdf_service, preprocess
    from app.templates import registry

    pdf = sample_pdfs(1)[0]
    print(f"\nProfiling {pdf.name}  (upscale={settings.upscale_factor}, "
          f"device={settings.ocr_device})")
    print("Warming models…")
    ocr_service.warmup()

    stages: dict[str, list[float]] = {k: [] for k in
                                      ("render", "preprocess", "ocr", "layout", "parse")}

    for run in range(args.repeat):
        t = time.perf_counter()
        rendered = pdf_service.render_page(str(pdf), 1)
        stages["render"].append(time.perf_counter() - t)

        t = time.perf_counter()
        pre = preprocess.preprocess(rendered.image)
        stages["preprocess"].append(time.perf_counter() - t)

        t = time.perf_counter()
        ocr = ocr_service.run_ocr(pre.image, pre.scale)
        stages["ocr"].append(time.perf_counter() - t)

        h, w = pre.display_image.shape[:2]
        template, _ = registry.detect(ocr.lines, (w, h))
        grid = template.expected_grid() or (10, 3)

        t = time.perf_counter()
        layout = layout_service.detect_layout(pre.display_image, grid[0], grid[1])
        stages["layout"].append(time.perf_counter() - t)

        t = time.perf_counter()
        records = template.parse(ocr.lines, layout, "bench", (w, h))
        template.validate(records)
        stages["parse"].append(time.perf_counter() - t)

        print(f"  run {run + 1}: {len(ocr.lines)} lines, {len(records)} records")

    total = sum(statistics.median(v) for v in stages.values())
    print(f"\n{'STAGE':<14} {'MEDIAN':>9} {'SHARE':>8}   (n={args.repeat})")
    print("-" * 42)
    for name, times in stages.items():
        med = statistics.median(times)
        bar = "#" * round(med / total * 30)
        print(f"{name:<14} {med:>8.2f}s {med / total:>7.1%}   {bar}")
    print("-" * 42)
    print(f"{'TOTAL':<14} {total:>8.2f}s")
    print("\nAnything under ~5% is not worth optimising until the top item is.")


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def _one_page(pdf_path: str) -> tuple[str, float]:
    """Top-level so ProcessPoolExecutor can pickle it."""
    from app.services import pipeline

    t = time.perf_counter()
    page = pipeline.process_page(pdf_path, 1, "bench", save_image=False)
    return page.model_dump_json(), time.perf_counter() - t


@dataclass
class Result:
    label: str
    wall: float
    pages: int
    accuracy: Accuracy = field(default_factory=Accuracy)

    @property
    def pages_per_sec(self) -> float:
        return self.pages / self.wall if self.wall else 0.0

    @property
    def sec_per_page(self) -> float:
        return self.wall / self.pages if self.pages else 0.0


def _run_pool(label: str, pdfs: list[Path], workers: int, kind: str) -> Result:
    from app.schemas.core import Page

    paths = [str(p) for p in pdfs]
    t0 = time.perf_counter()

    if kind == "sequential":
        outputs = [_one_page(p) for p in paths]
    else:
        Pool = ThreadPoolExecutor if kind == "thread" else ProcessPoolExecutor
        kwargs = {}
        if kind == "process":
            from app.services.job_queue import _init_worker

            kwargs["initializer"] = _init_worker
        with Pool(max_workers=workers, **kwargs) as pool:
            outputs = list(pool.map(_one_page, paths))

    wall = time.perf_counter() - t0
    result = Result(label=label, wall=wall, pages=len(paths))
    for payload, _ in outputs:
        result.accuracy.merge(score(Page.model_validate_json(payload)))
    return result


def cmd_concurrency(args) -> None:
    from app.services import ocr_service

    pdfs = sample_pdfs(args.pages)
    print(f"\nConcurrency benchmark — {len(pdfs)} pages, one page per PDF")
    print("Warming models in the parent process…")
    ocr_service.warmup()

    plans = [
        ("sequential",      "sequential", 1),
        ("threads x2",      "thread",     2),
        ("threads x4",      "thread",     4),
        ("threads x8",      "thread",     8),
        ("processes x2",    "process",    2),
        ("processes x4",    "process",    4),
    ]
    if args.quick:
        plans = [p for p in plans if p[0] in
                 ("sequential", "threads x4", "processes x4")]

    results: list[Result] = []
    for label, kind, workers in plans:
        print(f"\n-> {label} ...", flush=True)

        try:
            res = _run_pool(label, pdfs, workers, kind)
        except Exception as exc:  # noqa: BLE001
            print(f"   FAILED: {type(exc).__name__}: {exc}")
            continue
        results.append(res)
        print(f"   {res.wall:6.1f}s  {res.sec_per_page:5.1f}s/page  "
              f"{res.pages_per_sec:5.2f} pages/s   {res.accuracy.summary()}")

    _report(results, args.out)


def cmd_upscale(args) -> None:
    """Speed is only half the question -- does accuracy survive?"""
    from app.config import settings
    from app.services import ocr_service

    pdfs = sample_pdfs(args.pages)
    results: list[Result] = []
    original = settings.upscale_factor

    print(f"\nUpscale benchmark — {len(pdfs)} pages, sequential (isolates the variable)")
    try:
        # The engine itself is unaffected by upscale -- the factor changes the
        # image handed to it -- so the warm model is reused across factors and
        # only the work being measured differs.
        ocr_service.warmup()
        for factor in (1.5, 2.0, 3.0):
            settings.upscale_factor = factor
            print(f"\n→ upscale {factor} …", flush=True)
            res = _run_pool(f"upscale {factor}", pdfs, 1, "sequential")
            results.append(res)
            print(f"   {res.wall:6.1f}s  {res.sec_per_page:5.1f}s/page   "
                  f"{res.accuracy.summary()}")
    finally:
        settings.upscale_factor = original

    _report(results, args.out)
    print("\nPick the smallest factor whose fill-rate and clean-count match the best.")


def cmd_models(args) -> None:
    """Compare detection models.

    The detection model is 84 MB against the Tamil recogniser's 7.7 MB, and
    OCR is ~94% of page time, so this is the largest single CPU-side lever.
    Worth taking only if accuracy holds -- these are clean printed forms, so
    finding the text is the easy half; reading Tamil is the hard half.
    """
    from app.config import settings
    from app.services import ocr_service

    pdfs = sample_pdfs(args.pages)
    results: list[Result] = []
    original = settings.ocr_det_model

    print(f"\nDetection-model benchmark — {len(pdfs)} pages, sequential")
    try:
        for model in ("", "PP-OCRv5_mobile_det"):
            settings.ocr_det_model = model
            ocr_service.reset()  # the model is baked into the instance
            label = model or "server_det (default)"
            print(f"\n-> {label} ...", flush=True)

            try:
                ocr_service.warmup()
                res = _run_pool(label, pdfs, 1, "sequential")
            except Exception as exc:  # noqa: BLE001
                print(f"   FAILED: {type(exc).__name__}: {exc}")
                continue
            results.append(res)
            print(f"   {res.wall:6.1f}s  {res.sec_per_page:5.1f}s/page   "
                  f"{res.accuracy.summary()}")
    finally:
        settings.ocr_det_model = original
        ocr_service.reset()

    _report(results, args.out)
    print("\nTake the faster model only if clean-count and fill-rate match.")


def _report(results: list[Result], out: str | None) -> None:
    if not results:
        print("\nNo results.")
        return
    best = max(results, key=lambda r: r.pages_per_sec)
    slowest = min(results, key=lambda r: r.pages_per_sec)

    print(f"\n{'CONFIGURATION':<18} {'WALL':>8} {'S/PAGE':>8} {'PAGES/S':>9} "
          f"{'SPEEDUP':>8}  ACCURACY")
    print("-" * 86)
    for r in results:
        speedup = r.pages_per_sec / slowest.pages_per_sec if slowest.pages_per_sec else 1
        marker = "  <= best" if r is best else ""
        print(f"{r.label:<18} {r.wall:>7.1f}s {r.sec_per_page:>7.1f}s "
              f"{r.pages_per_sec:>9.2f} {speedup:>7.2f}x  {r.accuracy.summary()}{marker}")
    print("-" * 86)
    print(f"Best: {best.label} at {best.pages_per_sec:.2f} pages/s "
          f"({best.pages_per_sec / slowest.pages_per_sec:.2f}x over {slowest.label})")

    if out:
        Path(out).write_text(json.dumps(
            [{**asdict(r), "pages_per_sec": r.pages_per_sec,
              "sec_per_page": r.sec_per_page} for r in results],
            indent=2), encoding="utf-8")
        print(f"Written to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profile", help="Where does one page's time go?")
    p.add_argument("--repeat", type=int, default=3)
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("concurrency", help="sequential vs threads vs processes")
    p.add_argument("--pages", type=int, default=4)
    p.add_argument("--quick", action="store_true")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_concurrency)

    p = sub.add_parser("upscale", help="speed and accuracy across upscale factors")
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_upscale)

    p = sub.add_parser("models", help="server vs mobile detection model")
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_models)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
