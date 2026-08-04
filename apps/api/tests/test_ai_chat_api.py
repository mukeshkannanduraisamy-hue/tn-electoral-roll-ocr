"""The chat endpoints.

Thread isolation is the security property worth pinning down: the assistant
reads the database on an operator's behalf, so one operator's conversation must
never be readable by another.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sse_starlette.sse import AppStatus  # noqa: E402

from app.auth import require_user  # noqa: E402
from app.db import ChatThreadRow, UserRow, session_scope  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    """`sse-starlette`'s shutdown signal is a process-global `anyio.Event`,
    created lazily and bound to whichever event loop first touches it.
    Starlette's `TestClient` spins up a fresh loop per request, so the
    *second* SSE stream in a process raises "bound to a different event
    loop" unless this is cleared first. Real deployments never hit this --
    one process, one loop for the app's whole life -- so this is purely a
    test-harness reset, not an application-behaviour concern."""
    AppStatus.should_exit_event = None
    AppStatus.should_exit = False
    yield


@pytest.fixture(scope="module")
def users():
    """Two real user rows. Foreign keys are enforced, so these must exist."""
    ids = {"owner": uuid.uuid4().hex[:32], "other": uuid.uuid4().hex[:32]}
    with session_scope() as s:
        for role, uid in ids.items():
            s.add(UserRow(id=uid, username=f"{role}-{uid[:8]}", password_hash="x"))
    yield ids
    with session_scope() as s:
        for uid in ids.values():
            row = s.get(UserRow, uid)
            if row is not None:
                s.delete(row)


@pytest.fixture()
def client_as(users):
    """A client authenticated as one of the fixture users."""

    def _make(role: str):
        uid = users[role]
        with session_scope() as s:
            user = s.get(UserRow, uid)
            s.expunge(user)
        app.dependency_overrides[require_user] = lambda: user
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture()
def owned_thread(users):
    tid = uuid.uuid4().hex[:32]
    with session_scope() as s:
        s.add(ChatThreadRow(id=tid, user_id=users["owner"], title="Mine"))
    yield tid
    with session_scope() as s:
        row = s.get(ChatThreadRow, tid)
        if row is not None:
            s.delete(row)


def test_threads_list_only_the_callers_own(client_as, owned_thread):
    mine = client_as("owner").get("/api/ai/threads").json()
    assert any(t["id"] == owned_thread for t in mine["threads"])

    theirs = client_as("other").get("/api/ai/threads").json()
    assert all(t["id"] != owned_thread for t in theirs["threads"])


def test_another_users_thread_is_not_readable(client_as, owned_thread):
    response = client_as("other").get(f"/api/ai/threads/{owned_thread}")
    assert response.status_code == 404


def test_another_users_thread_cannot_be_deleted(client_as, owned_thread):
    assert client_as("other").delete(f"/api/ai/threads/{owned_thread}").status_code == 404
    with session_scope() as s:
        assert s.get(ChatThreadRow, owned_thread) is not None


def test_owner_can_delete_their_thread(client_as, owned_thread):
    assert client_as("owner").delete(f"/api/ai/threads/{owned_thread}").status_code == 204
    with session_scope() as s:
        assert s.get(ChatThreadRow, owned_thread) is None


def test_an_empty_message_is_rejected(client_as):
    assert client_as("owner").post("/api/ai/chat", json={"message": "  "}).status_code == 422


def test_chat_streams_sse_frames_and_persists_the_turn(client_as, monkeypatch):
    from app.services.ai_agent import loop as agent_loop
    from app.routers import ai_chat

    monkeypatch.setattr(ai_chat, "classify", lambda *a, **k: "data")
    monkeypatch.setattr(
        ai_chat,
        "run_agent",
        lambda *a, **k: iter(
            [
                agent_loop.AgentEvent("token", {"text": "Six files."}),
                agent_loop.AgentEvent("done", {"content": "Six files.", "blocks": [],
                                               "citations": [], "tool_trace": []}),
            ]
        ),
    )

    client = client_as("owner")
    with client.stream("POST", "/api/ai/chat", json={"message": "how many files"}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: token" in body
    assert "event: done" in body

    threads = client.get("/api/ai/threads").json()["threads"]
    newest = threads[0]
    replay = client.get(f"/api/ai/threads/{newest['id']}").json()
    assert [m["role"] for m in replay["messages"]] == ["user", "assistant"]
    assert replay["messages"][1]["content"] == "Six files."

    client.delete(f"/api/ai/threads/{newest['id']}")


def test_a_turn_that_errors_before_done_persists_only_the_user_message(
    client_as, monkeypatch,
):
    """A transport failure mid-turn must not silently invent an assistant
    reply, and must not lose the question the operator already asked."""
    from app.services.ai_agent import loop as agent_loop
    from app.routers import ai_chat

    monkeypatch.setattr(ai_chat, "classify", lambda *a, **k: "data")

    def boom(*a, **k):
        yield agent_loop.AgentEvent("status", {"message": "starting"})
        raise RuntimeError("transport blew up")

    monkeypatch.setattr(ai_chat, "run_agent", boom)

    client = client_as("owner")
    with client.stream("POST", "/api/ai/chat", json={"message": "explode please"}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: error" in body
    assert "event: done" not in body

    threads = client.get("/api/ai/threads").json()["threads"]
    newest = threads[0]
    replay = client.get(f"/api/ai/threads/{newest['id']}").json()
    assert [m["role"] for m in replay["messages"]] == ["user"]

    client.delete(f"/api/ai/threads/{newest['id']}")


def test_budget_exhausted_and_provider_notice_are_streamed_and_persisted(
    client_as, monkeypatch,
):
    """Task 11's review flagged these as the one guard-enforced signal that a
    turn was cut short. They must survive both the SSE frame and the replay,
    not just the live stream."""
    from app.services.ai_agent import loop as agent_loop
    from app.routers import ai_chat

    monkeypatch.setattr(ai_chat, "classify", lambda *a, **k: "data")
    monkeypatch.setattr(
        ai_chat,
        "run_agent",
        lambda *a, **k: iter(
            [
                agent_loop.AgentEvent("token", {"text": "Cut short."}),
                agent_loop.AgentEvent(
                    "done",
                    {
                        "content": "Cut short.", "blocks": [], "citations": [],
                        "tool_trace": [], "budget_exhausted": True,
                        "provider_notice": "The provider stopped early: 429",
                    },
                ),
            ]
        ),
    )

    client = client_as("owner")
    with client.stream("POST", "/api/ai/chat", json={"message": "budget please"}) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert '"budget_exhausted": true' in body
    assert '"provider_notice": "The provider stopped early: 429"' in body

    threads = client.get("/api/ai/threads").json()["threads"]
    newest = threads[0]
    replay = client.get(f"/api/ai/threads/{newest['id']}").json()
    assistant = replay["messages"][1]
    assert assistant["budget_exhausted"] is True
    assert assistant["provider_notice"] == "The provider stopped early: 429"

    client.delete(f"/api/ai/threads/{newest['id']}")


def test_a_client_disconnecting_right_after_done_does_not_lose_the_reply(client_as, monkeypatch):
    """Regression: persistence used to happen *after* the `done` frame was
    handed to Starlette for sending. A well-behaved client is entitled to
    close its `EventSource` the instant it sees a terminal event -- that is
    what "done is terminal" means -- so persisting after the frame raced a
    disconnect that could win.

    Drive the ASGI app directly (Starlette's `TestClient` runs the whole
    response to completion before the test ever sees it, so it cannot
    simulate a disconnect at all -- see `_reset_sse_app_status` above for why
    this needs the raw app callable rather than the usual `client_as`
    fixture). `receive()` is gated on `send()` having actually transmitted
    the `done` chunk, so the disconnect is delivered at the earliest possible
    instant a real client could have caused it -- not before, which would
    prove nothing, since a reply that was never sent is not a reply that was
    lost.
    """
    import asyncio
    import json as json_mod

    from app.services.ai_agent import loop as agent_loop
    from app.routers import ai_chat

    monkeypatch.setattr(ai_chat, "classify", lambda *a, **k: "data")
    monkeypatch.setattr(
        ai_chat,
        "run_agent",
        lambda *a, **k: iter(
            [
                agent_loop.AgentEvent("token", {"text": "ok"}),
                agent_loop.AgentEvent(
                    "done", {"content": "ok", "blocks": [], "citations": [], "tool_trace": []},
                ),
            ]
        ),
    )

    client_as("owner")  # sets app.dependency_overrides[require_user]

    body = json_mod.dumps({"message": "hello"}).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "path": "/api/ai/chat", "raw_path": b"/api/ai/chat",
        "root_path": "", "scheme": "http", "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("testclient", 123), "server": ("testserver", 80), "state": {},
    }
    request_body_sent = False
    done_seen: "asyncio.Event | None" = None

    async def receive():
        nonlocal request_body_sent
        if not request_body_sent:
            request_body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await done_seen.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and b"event: done" in message.get(
            "body", b""
        ):
            done_seen.set()

    async def run():
        nonlocal done_seen
        done_seen = asyncio.Event()
        await app(scope, receive, send)

    asyncio.run(run())

    threads = client_as("owner").get("/api/ai/threads").json()["threads"]
    newest = threads[0]
    replay = client_as("owner").get(f"/api/ai/threads/{newest['id']}").json()
    assert [m["role"] for m in replay["messages"]] == ["user", "assistant"], (
        "the assistant reply must be committed before the `done` frame is "
        "sendable, not after -- a disconnect the instant it is sendable "
        "must not lose it"
    )

    client_as("owner").delete(f"/api/ai/threads/{newest['id']}")
