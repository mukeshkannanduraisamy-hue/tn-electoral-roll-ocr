"""The assistant's endpoints.

Streaming exists because the honest answer to "how long will this take" is
"between half a second and twenty", and a panel that shows nothing for twenty
seconds teaches an operator that the assistant is broken.

Threads are per-user and enforced on every read. The assistant queries the
database on an operator's behalf; a conversation is therefore a record of what
that operator asked to see, and belongs to them alone.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

from ..auth import require_user
from ..db import ChatMessageRow, ChatThreadRow, UserRow, get_session
from ..services import app_settings
from ..services.ai_agent.loop import AgentEvent, run_agent
from ..services.ai_agent.router import classify
from ..services.nvidia_ai_service import query_nvidia_copilot

logger = logging.getLogger(__name__)
router = APIRouter()

#: A title is the first thing the operator asked, trimmed to fit a menu row.
TITLE_LENGTH = 60


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


def _new_id() -> str:
    return uuid.uuid4().hex[:32]


def _owned_thread(session: Session, thread_id: str, user: UserRow) -> ChatThreadRow:
    """Fetch a thread, or 404. A thread of another user's does not exist."""
    thread = session.get(ChatThreadRow, thread_id)
    if thread is None or thread.user_id != user.id:
        raise HTTPException(404, "No such conversation.")
    return thread


@router.get("/threads")
def list_threads(
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    rows = (
        session.execute(
            select(ChatThreadRow)
            .where(ChatThreadRow.user_id == user.id)
            .order_by(ChatThreadRow.updated_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return {
        "threads": [
            {
                "id": t.id,
                "title": t.title,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in rows
        ]
    }


@router.get("/threads/{thread_id}")
def get_thread(
    thread_id: str,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    thread = _owned_thread(session, thread_id, user)
    messages = (
        session.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.thread_id == thread.id)
            .order_by(ChatMessageRow.created_at)
        )
        .scalars()
        .all()
    )
    return {
        "id": thread.id,
        "title": thread.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "blocks": m.blocks or [],
                "citations": m.citations or [],
                "tool_trace": m.tool_trace or [],
                "budget_exhausted": m.budget_exhausted,
                "provider_notice": m.provider_notice,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(
    thread_id: str,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
):
    session.delete(_owned_thread(session, thread_id, user))
    session.commit()
    return Response(status_code=204)


def _history(session: Session, thread_id: str) -> List[Dict[str, str]]:
    rows = (
        session.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.thread_id == thread_id)
            .order_by(ChatMessageRow.created_at.desc())
            .limit(24)
        )
        .scalars()
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def _fast_path(message: str, creds, context: Optional[Dict[str, Any]]) -> Iterator[AgentEvent]:
    """Conversational and how-to messages, answered as they always were.

    This is the 0.44s path from commit 1784600. It does not touch the database
    and does not enter the loop, so it never runs out of tool-call budget and
    never emits a provider notice.
    """
    result = query_nvidia_copilot(message, creds, context)
    reply = str(result.get("reply") or "")
    yield AgentEvent("token", {"text": reply})
    yield AgentEvent(
        "done", {"content": reply, "blocks": [], "citations": [], "tool_trace": []}
    )


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(422, "The message is empty.")

    creds = app_settings.resolve_ai_credentials(session)

    thread = (
        _owned_thread(session, payload.thread_id, user) if payload.thread_id else None
    )
    if thread is None:
        thread = ChatThreadRow(
            id=_new_id(), user_id=user.id, title=message[:TITLE_LENGTH]
        )
        session.add(thread)
        session.flush()
    history = _history(session, thread.id)

    session.add(
        ChatMessageRow(
            id=_new_id(), thread_id=thread.id, role="user", content=message
        )
    )
    session.commit()
    thread_id = thread.id

    # `classify` can fall back to a real network call to the model when the
    # heuristics are unsure (see `router.py`). `chat` is `async def`, so a
    # call made directly here would run on the event loop and block every
    # other request the process is serving -- not just this one -- for
    # however long that round trip takes. Off the loop, same as the
    # blocking DB/network work the agent loop itself does inside `produce`.
    intent = await run_in_threadpool(classify, message, creds)

    def produce() -> Iterator[Dict[str, str]]:
        # This generator is driven from a worker thread (see
        # `iterate_in_threadpool` below), one `next()` call at a time, and the
        # request handler above has already finished using `session` by the
        # time this starts running. Nothing else touches `session`
        # concurrently: FastAPI hands each request its own `Session` via
        # `get_session`, so no other request can reach this one, and within
        # this request every use -- the setup above, this generator, and
        # `get_session`'s teardown -- happens strictly one after another, not
        # in parallel.
        yield {"event": "status", "data": json.dumps({"thread_id": thread_id, "intent": intent})}

        events = (
            _fast_path(message, creds, payload.context)
            if intent in ("smalltalk", "howto")
            else run_agent(
                session,
                message,
                creds=creds,
                history=history,
                app_context=payload.context,
            )
        )

        try:
            for event in events:
                if event.type == "done":
                    # Persisted *before* the frame goes out, not after. A
                    # well-behaved client is entitled to close its
                    # `EventSource` the instant it sees the terminal event --
                    # that is what "done is terminal" means -- and once the
                    # frame is on the wire, this generator's next `next()`
                    # call races that disconnect. Losing that race silently
                    # drops the assistant's reply from the thread even though
                    # the operator already read it. Writing first removes the
                    # race instead of hoping to win it: by the time the
                    # client can possibly see `done`, the row is committed.
                    session.add(
                        ChatMessageRow(
                            id=_new_id(),
                            thread_id=thread_id,
                            role="assistant",
                            content=event.data.get("content", ""),
                            blocks=event.data.get("blocks") or [],
                            citations=event.data.get("citations") or [],
                            tool_trace=event.data.get("tool_trace") or [],
                            budget_exhausted=bool(event.data.get("budget_exhausted", False)),
                            provider_notice=event.data.get("provider_notice"),
                        )
                    )
                    session.commit()
                yield {"event": event.type, "data": json.dumps(event.data, default=str)}
        except Exception:
            logger.exception("The assistant failed mid-turn")
            yield {
                "event": "error",
                "data": json.dumps({"message": "The assistant failed while answering."}),
            }

    return EventSourceResponse(iterate_in_threadpool(produce()))
