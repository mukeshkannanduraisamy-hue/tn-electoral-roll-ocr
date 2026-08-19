"""Importing paddle must not silence the application's logging.

`import paddle` raises the root logger from INFO to WARNING as a side effect.
Nothing errors when it happens; the log simply stops part-way through boot and
never resumes, so the startup banner loses its OCR line and every
`logger.info` afterwards -- page classifications, consensus corrections,
per-file job progress -- goes nowhere. A service that has gone quiet reads as
a service that has hung, which is the wrong thing to be debugging.

These run in a subprocess because a module is imported once per interpreter.
By the time any other test has touched `ocr_service`, paddle is already in
`sys.modules` and the level has already moved, so an in-process assertion
would pass whether or not the guard exists.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]


def run(body: str) -> str:
    """Execute `body` in a fresh interpreter rooted at the API package.

    Both streams are returned. `logging.basicConfig` installs a StreamHandler
    on stderr, so checking stdout alone would look for the log lines in the
    one place they are guaranteed not to be.
    """
    result = subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        cwd=str(API_ROOT),
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"subprocess failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def test_resolving_the_device_leaves_the_log_level_alone():
    """`resolve_device` imports paddle to probe for CUDA."""
    out = run(
        """
import logging
logging.basicConfig(level=logging.INFO)
before = logging.getLogger().level
from app.services import ocr_service
ocr_service.resolve_device()
print(f"LEVELS {before} {logging.getLogger().level}")
"""
    )
    line = next(ln for ln in out.splitlines() if ln.startswith("LEVELS "))
    before, after = line.split()[1:3]
    INFO = "20"
    assert before == after == INFO, (
        f"root log level moved from {before} to {after} while probing for a GPU"
    )


def test_an_info_line_still_reaches_the_log_after_the_probe():
    """The assertion that matters, stated the way the symptom appears."""
    out = run(
        """
import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("app.main")
from app.services import ocr_service
ocr_service.resolve_device()
log.info("STARTUP-LINE-SURVIVED")
"""
    )
    assert "STARTUP-LINE-SURVIVED" in out


def test_a_deliberately_quiet_deployment_stays_quiet():
    """The guard restores the previous level, it does not force INFO.

    A deployment that asked for WARNING gets WARNING -- otherwise this fix
    would be its own bug, turning the logs back on for someone who had
    turned them off.
    """
    out = run(
        """
import logging
logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("app.main")
from app.services import ocr_service
ocr_service.resolve_device()
log.info("SHOULD-NOT-APPEAR")
log.warning("SHOULD-APPEAR")
print(f"LEVEL {logging.getLogger().level}")
"""
    )
    assert "SHOULD-NOT-APPEAR" not in out
    assert "SHOULD-APPEAR" in out
    assert "LEVEL 30" in out


def test_the_guard_restores_the_level_even_when_the_body_raises():
    """A failed import must not leave the level moved behind it."""
    out = run(
        """
import logging
logging.basicConfig(level=logging.INFO)
from app.services.ocr_service import preserved_root_log_level
try:
    with preserved_root_log_level():
        logging.getLogger().setLevel(logging.ERROR)
        raise RuntimeError("boom")
except RuntimeError:
    pass
print(f"LEVEL {logging.getLogger().level}")
"""
    )
    assert "LEVEL 20" in out
