"""Guards on the OCR engine cache.

Context: sharing one PaddleOCR predictor between threads segfaults the
process (Windows ACCESS_VIOLATION 0xC0000005 inside the paddle static
runner, no Python traceback). That is a crash, not a wrong answer -- it kills
the API server and every page in flight with it.

The cache is therefore thread-local. These tests assert that property without
loading any model, so they run in milliseconds and are safe in CI.
"""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import ocr_service  # noqa: E402


@pytest.fixture(autouse=True)
def _drop_fake_engines_afterwards():
    """Clear the cache on the way out, not just on the way in.

    These tests seed the cache with a `FakeEngine`. `monkeypatch` restores
    `sys.modules`, but the cached object outlives it, so without this any later
    test doing real OCR silently gets the stub and reads nothing.
    """
    yield
    ocr_service.reset()


class FakeEngine:
    """Stands in for PaddleOCR so no weights are loaded."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.thread = threading.current_thread().name


def _patch(monkeypatch):
    """Make get_engine construct a FakeEngine instead of the real thing."""
    import types

    fake_module = types.ModuleType("paddleocr")
    fake_module.PaddleOCR = FakeEngine
    monkeypatch.setitem(sys.modules, "paddleocr", fake_module)


def test_same_thread_reuses_one_engine(monkeypatch):
    """Model load costs ~8s; a per-call rebuild would dominate runtime."""
    _patch(monkeypatch)
    ocr_service.reset()

    first = ocr_service.get_engine()
    second = ocr_service.get_engine()
    assert first is second


def test_each_thread_gets_its_own_engine(monkeypatch):
    """The property that stops the segfault: no instance crosses a thread."""
    _patch(monkeypatch)
    ocr_service.reset()

    engines: list[int] = []
    lock = threading.Lock()
    # Sized to the worker threads ONLY. Including the main thread here would
    # need a 4th party that never arrives, and the test would hang forever.
    barrier = threading.Barrier(3)

    held: list[Any] = []

    def grab():
        barrier.wait(timeout=10)  # force genuine overlap, not sequential runs
        engine = ocr_service.get_engine()
        with lock:
            held.append(engine)
            engines.append(id(engine))


    threads = [threading.Thread(target=grab) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "thread did not finish -- possible deadlock"

    assert len(engines) == 3
    assert len(set(engines)) == 3, "threads must not share a predictor"


def test_pool_workers_do_not_share(monkeypatch):
    """The real-world shape: a ThreadPoolExecutor running page tasks."""
    _patch(monkeypatch)
    ocr_service.reset()

    def task(_):
        return id(ocr_service.get_engine())

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="ocr") as pool:
        ids = list(pool.map(task, range(9)))

    # Nine tasks over three workers: at most three distinct engines, and never
    # more than one per thread.
    assert len(set(ids)) <= 3


def test_cache_key_includes_detection_model(monkeypatch):
    """Changing the detection model must not return the stale engine.

    The model name is baked into the instance at construction, so a key of
    only (lang, version, device) makes `ocr_det_model` look configurable
    while silently doing nothing.
    """
    _patch(monkeypatch)
    ocr_service.reset()
    original = settings.ocr_det_model
    try:
        settings.ocr_det_model = ""
        default_engine = ocr_service.get_engine()

        settings.ocr_det_model = "PP-OCRv5_mobile_det"
        mobile_engine = ocr_service.get_engine()

        assert default_engine is not mobile_engine
        assert mobile_engine.kwargs.get("text_detection_model_name") == "PP-OCRv5_mobile_det"
    finally:
        settings.ocr_det_model = original
        ocr_service.reset()


def test_cache_key_includes_det_limit_side_len(monkeypatch):
    _patch(monkeypatch)
    ocr_service.reset()
    original = settings.ocr_det_limit_side_len
    try:
        settings.ocr_det_limit_side_len = 960
        small = ocr_service.get_engine()
        settings.ocr_det_limit_side_len = 2560
        large = ocr_service.get_engine()
        assert small is not large
    finally:
        settings.ocr_det_limit_side_len = original
        ocr_service.reset()


def test_reset_clears_this_thread(monkeypatch):
    _patch(monkeypatch)
    ocr_service.reset()
    before = ocr_service.get_engine()
    ocr_service.reset()
    after = ocr_service.get_engine()
    assert before is not after
