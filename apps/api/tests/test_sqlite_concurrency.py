"""Reading must not take a write lock.

A `begin` event listener issued `BEGIN IMMEDIATE` on every transaction, so
every session -- including one that only reads -- acquired SQLite's RESERVED
lock over the whole database. Three things followed.

WAL stopped meaning anything. `_configure_sqlite` sets `journal_mode=WAL` and
says it "keeps readers unblocked while a worker writes results", which is
exactly what the listener prevented: readers took the writer's lock, so they
blocked each other and the extraction workers.

Streaming endpoints deadlocked against themselves. `require_user` is a
router-level dependency, and a dependency holds its session for the whole
request; a streaming response is not finished until the stream ends. So
`GET /api/jobs/{id}/events` held a write lock, then opened a second session
for its own snapshot query, and waited for a lock its own request would not
release until it returned. One call to that endpoint hung the server until it
was restarted -- which is what the extraction progress bar was waiting on
while it showed 0%.

The stack, caught mid-hang, was unambiguous::

    app/db.py in _code_begin_immediate -> exec_driver_sql -> do_execute
      <- session.get  <- jobs.py _snapshot

These tests pin the property that matters: an open read must not stop anyone
else working.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.db import FileRow, session_scope  # noqa: E402


def test_an_open_read_does_not_block_a_write():
    """The deadlock, reduced to two sessions.

    Session A reads and stays open, exactly as a request's auth dependency
    does. Session B then writes. Under `BEGIN IMMEDIATE` this waited for A's
    lock and only failed after the 60-second busy timeout.
    """
    marker = "concurrency-probe-" + str(threading.get_ident())
    done: list[str] = []

    with session_scope() as reader:
        reader.execute(select(func.count()).select_from(FileRow)).scalar()

        def writer():
            started = time.perf_counter()
            try:
                with session_scope() as s:
                    s.add(FileRow(id=marker[:32], name=marker, page_count=1))
                done.append(f"ok in {time.perf_counter() - started:.2f}s")
            except Exception as exc:  # noqa: BLE001
                done.append(f"FAILED after {time.perf_counter() - started:.2f}s: {exc}")

        thread = threading.Thread(target=writer)
        thread.start()
        # Generous enough to be a real signal, far below the 60s lock timeout
        # that the old behaviour would have burned before failing.
        thread.join(timeout=15)

    assert not thread.is_alive(), (
        "a write blocked behind an open read -- reads are taking a write lock"
    )
    assert done and done[0].startswith("ok"), done

    with session_scope() as s:
        s.query(FileRow).filter(FileRow.name == marker).delete(
            synchronize_session=False
        )


def test_two_reads_can_overlap():
    """Plain WAL behaviour, and the thing the listener took away."""
    barrier = threading.Barrier(2, timeout=15)
    errors: list[str] = []

    def reader():
        try:
            with session_scope() as s:
                s.execute(select(func.count()).select_from(FileRow)).scalar()
                # Both sessions are open at this point. If a read holds an
                # exclusive lock, the second never arrives and this times out.
                barrier.wait()
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent reads failed: {errors}"
    assert all(not t.is_alive() for t in threads), "concurrent reads deadlocked"


def test_a_second_session_inside_an_open_one_still_works():
    """The shape of the endpoint that hung.

    A request holds its dependency's session open and then opens another --
    which is ordinary, and must not deadlock.
    """
    with session_scope() as outer:
        outer.execute(select(func.count()).select_from(FileRow)).scalar()

        result: list[int] = []

        def inner():
            with session_scope() as s:
                result.append(
                    s.execute(select(func.count()).select_from(FileRow)).scalar()
                )

        thread = threading.Thread(target=inner)
        thread.start()
        thread.join(timeout=15)

    assert not thread.is_alive(), "a nested session deadlocked against its caller"
    assert result, "the inner session never completed"
