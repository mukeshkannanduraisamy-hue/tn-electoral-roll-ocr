"""Static guard against undefined names anywhere in `app/`.

The bug this exists to catch: `job_queue._run_job` called `time.perf_counter()`
to compute the progress ETA, but the module never imported `time`. Nothing
failed at import, and nothing failed in any test -- the name is only resolved
when the line actually runs, which is *after* every page task has been
submitted to the pool. So every extraction job died at that exact point with
`NameError: name 'time' is not defined`, the job row went to "failed", and the
uploaded PDF sat at 0 of 12 pages with no page ever saved.

A missing import is invisible to import-time checks and to any test that does
not execute that specific line. Pyflakes resolves names per-scope across the
whole tree in milliseconds, so it catches the whole class -- including the
mirror-image bug where a name survives only because an import was left behind.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = API_ROOT / "app"

# F821 undefined name          -- the `import time` bug
# F822 undefined name in __all__
# F811 redefinition of unused name -- shadowed import/def, usually a merge slip
CODES = ("F821", "F822", "F811")


def _pyflakes_report() -> list[str]:
    """Run pyflakes over `app/` and return only the lines we treat as fatal."""
    proc = subprocess.run(
        [sys.executable, "-m", "pyflakes", str(APP_DIR)],
        capture_output=True,
        text=True,
    )
    if "No module named pyflakes" in proc.stderr:
        pytest.skip("pyflakes not installed; run `pip install -r requirements.txt`")

    # Pyflakes prints one finding per line but does not emit the code, so match
    # on its message text instead.
    fatal_markers = (
        "undefined name",
        "redefinition of unused",
    )
    # `from .core import *` makes pyflakes announce that it *cannot* check that
    # module ("unable to detect undefined names"). That is a statement about
    # its own coverage, not a defect, and it contains the marker text -- so it
    # has to be dropped explicitly or the guard fires on every run.
    ignored = ("unable to detect undefined names",)

    return [
        line
        for line in proc.stdout.splitlines()
        if any(marker in line for marker in fatal_markers)
        and not any(skip in line for skip in ignored)
    ]


def test_app_has_no_undefined_names():
    findings = _pyflakes_report()
    assert not findings, (
        "undefined or redefined names in app/ -- these raise NameError only "
        "when the line runs, so they reach production as mid-job crashes:\n  "
        + "\n  ".join(findings)
    )


def test_job_queue_imports_every_module_it_uses():
    """Targeted guard on the exact module that broke.

    `_run_job` is a long function whose later half only executes once page
    results start arriving, so a name missing from that half is easy to ship.
    """
    source = (APP_DIR / "services" / "job_queue.py").read_text(encoding="utf-8")

    for module in ("time", "uuid", "json", "threading", "asyncio", "logging"):
        if f"{module}." in source:
            assert f"import {module}" in source, (
                f"job_queue.py uses `{module}.` but never imports {module} -- "
                f"this raises NameError mid-job, after pages are already queued"
            )
