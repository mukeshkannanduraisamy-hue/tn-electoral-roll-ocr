"""How many pages the job runner puts through OCR at once.

On a GPU machine the runner used a single worker, on the reasoning that one GPU
serialises compute and that concurrent access to an engine risks a crash on a
4 GB card. Measured on this project's GTX 1650, both halves turn out to be
weaker than they sound:

* Only about 69% of a page is GPU inference. The rest -- rendering, deskew,
  preprocessing, template parsing -- is CPU work, and with one worker the card
  sits idle through all of it. Twelve pages took 56.4 s at one worker, 47.5 s at
  two and 44.4 s at three, with identical output (360 records every time).
* Nothing shares an engine. `ocr_service` caches per thread precisely so two
  threads never touch one predictor, which is what the segfault guard in
  `test_ocr_thread_safety` exists to protect. One engine occupies 591 MiB, and
  three workers peaked at 2177 MiB of 4096.

So the GPU is capped rather than pinned to one, low enough to leave the card
half free.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.services.job_queue import resolve_worker_count  # noqa: E402


def test_a_gpu_runs_more_than_one_page_at_a_time():
    """The measured gain is 19% at two workers, 27% at three."""
    assert resolve_worker_count("gpu:0", configured=8) > 1


def test_a_gpu_is_capped_well_below_the_cpu_limit():
    """Each worker holds its own engine on a card with finite memory."""
    assert resolve_worker_count("gpu:0", configured=8) <= 3


def test_a_gpu_never_exceeds_what_was_configured():
    """Asking for one worker means one, whatever the device."""
    assert resolve_worker_count("gpu:0", configured=1) == 1
    assert resolve_worker_count("gpu:0", configured=2) == 2


def test_cpu_keeps_its_existing_ceiling():
    assert resolve_worker_count("cpu", configured=16) == 8
    assert resolve_worker_count("cpu", configured=4) == 4


@pytest.mark.parametrize("configured", [0, -1])
def test_a_nonsense_setting_still_yields_a_usable_pool(configured):
    assert resolve_worker_count("cpu", configured=configured) == 1
    assert resolve_worker_count("gpu:0", configured=configured) == 1


def test_the_device_string_only_has_to_start_with_gpu():
    assert resolve_worker_count("gpu", configured=8) == resolve_worker_count(
        "gpu:0", configured=8
    )
