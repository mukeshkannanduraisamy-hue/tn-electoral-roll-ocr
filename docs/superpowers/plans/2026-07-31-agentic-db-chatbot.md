# Agentic DB-Connected AI Assistant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-shot chatbot with a read-only agent that answers any question about the electoral roll, the OCR pipeline and the workspace, using typed database tools plus a guarded SQL escape hatch, streamed over SSE with persisted conversation threads.

**Architecture:** A tool registry declares typed read-only tools over the existing SQLAlchemy models. A two-tier router sends conversational messages to the fast model unchanged and data questions into a bounded agent loop. The loop runs tools, and the *backend* — not the model — converts tool results into render blocks. Answer guards then discard any figure or record citation the tools did not produce.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, `sse-starlette`, Pydantic v2, pytest; Next.js 15 / React 19, Zustand, TypeScript, Tailwind, lucide-react.

## Global Constraints

- **Read-only.** No task adds a write path to the chat. No `INSERT`/`UPDATE`/`DELETE` reachable from the agent.
- **The model never produces a number.** Permitted figures are rebuilt from every tool result in the turn; sentences quoting anything else are dropped.
- **The model never produces a record reference.** `[[v:<id>]]` markers not present in the turn's tool results are stripped server-side.
- **The model never produces a render block.** Tables, cards and charts are built by the backend from tool results.
- **Forbidden tables, absolutely:** `users`, `sessions`, `app_settings`. `app_settings` holds the NVIDIA API key.
- **Budgets:** 4 tool rounds, 6 tool calls, 20s wall clock per turn.
- **Do not modify** `app/services/infographic.py`. Do not change the behaviour of any existing public function in `app/services/nvidia_ai_service.py`.
- **`POST /api/voters/ai-copilot` keeps working unchanged** for the whole plan.
- Alembic head at plan time is `96eb30bf1679`.
- Backend tests run against the configured database and must clean up after themselves (see `tests/test_infographic.py`). There is no `conftest.py` and no separate test database.
- Backend test command: `npm run test:backend` (or `cd apps/api && .venv/Scripts/python.exe -m pytest`).
- Frontend gates: `cd apps/web && npm run typecheck` and `npm run lint`. There is no frontend test runner — do not invent one.
- Shared types live in `packages/shared-types`.

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `apps/api/app/services/ai_agent/__init__.py` | Package marker; re-exports `run_agent`. |
| `apps/api/app/services/ai_agent/registry.py` | Tool declaration, JSON-schema generation, argument validation, dispatch. |
| `apps/api/app/services/ai_agent/tools/electors.py` | `search_voters`, `get_voter`, `household_of`. |
| `apps/api/app/services/ai_agent/tools/analytics.py` | `aggregate` — wraps `infographic.py`. |
| `apps/api/app/services/ai_agent/tools/quality.py` | `ocr_quality`, `low_confidence_records`, `find_anomalies`. |
| `apps/api/app/services/ai_agent/tools/pipeline.py` | `file_status`, `page_details`, `job_status`. |
| `apps/api/app/services/ai_agent/tools/geography.py` | `roll_overview`, `polling_station`. |
| `apps/api/app/services/ai_agent/tools/sql.py` | `run_readonly_sql` + the SQL guard. |
| `apps/api/app/services/ai_agent/guards.py` | Number integrity, citation binding. |
| `apps/api/app/services/ai_agent/blocks.py` | Tool result → render block. |
| `apps/api/app/services/ai_agent/router.py` | Intent classification. |
| `apps/api/app/services/ai_agent/context.py` | Cached roll profile. |
| `apps/api/app/services/ai_agent/loop.py` | The bounded agent loop. |
| `apps/api/app/routers/ai_chat.py` | `/api/ai/*` endpoints, SSE. |
| `apps/api/migrations/versions/<rev>_chat_threads.py` | Two new tables. |
| `apps/web/src/lib/aiChatApi.ts` | Streaming client + thread CRUD. |
| `apps/web/src/hooks/useAiChat.ts` | Stream state machine. |
| `apps/web/src/components/ai/MessageBlocks.tsx` | Block renderer. |
| `apps/web/src/components/ai/VoterChip.tsx` | Click-to-open citation chip. |
| `apps/web/src/components/ai/ToolTrace.tsx` | Collapsible step trace. |
| `apps/web/src/components/ai/ThreadMenu.tsx` | Thread history. |

**Modified:** `apps/api/app/db.py` (two models), `apps/api/app/services/nvidia_ai_service.py` (add streaming + tool transports only), `apps/api/app/main.py` (register router), `apps/web/src/components/FloatingAiChatbot.tsx`, `packages/shared-types/src/index.ts`.

---

### Task 1: Chat thread persistence

**Files:**
- Modify: `apps/api/app/db.py` (append after `SummaryRow`)
- Create: `apps/api/migrations/versions/<rev>_chat_threads.py`
- Test: `apps/api/tests/test_chat_persistence.py`

**Interfaces:**
- Consumes: `Base`, `_utcnow`, `session_scope` from `app.db`.
- Produces: `ChatThreadRow(id, user_id, title, created_at, updated_at)`, `ChatMessageRow(id, thread_id, role, content, tool_trace, citations, blocks, created_at)`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_chat_persistence.py`:

```python
"""Chat threads outlive a process, and deleting a thread takes its messages."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import ChatMessageRow, ChatThreadRow, session_scope  # noqa: E402


@pytest.fixture()
def thread_id():
    tid = uuid.uuid4().hex[:32]
    with session_scope() as s:
        s.add(ChatThreadRow(id=tid, user_id="test-user", title="Fixture thread"))
    yield tid
    with session_scope() as s:
        row = s.get(ChatThreadRow, tid)
        if row is not None:
            s.delete(row)


def test_messages_round_trip_their_json_columns(thread_id):
    with session_scope() as s:
        s.add(
            ChatMessageRow(
                id=uuid.uuid4().hex[:32],
                thread_id=thread_id,
                role="assistant",
                content="412 electors.",
                tool_trace=[{"tool": "search_voters", "rows": 412}],
                citations=[{"id": "v1", "epic": "ABC1234567"}],
                blocks=[{"kind": "table", "columns": ["name"]}],
            )
        )
    with session_scope() as s:
        row = s.query(ChatMessageRow).filter_by(thread_id=thread_id).one()
        assert row.tool_trace[0]["tool"] == "search_voters"
        assert row.citations[0]["epic"] == "ABC1234567"
        assert row.blocks[0]["kind"] == "table"


def test_deleting_a_thread_removes_its_messages(thread_id):
    with session_scope() as s:
        s.add(
            ChatMessageRow(
                id=uuid.uuid4().hex[:32], thread_id=thread_id, role="user", content="hi"
            )
        )
    with session_scope() as s:
        s.delete(s.get(ChatThreadRow, thread_id))
    with session_scope() as s:
        assert s.query(ChatMessageRow).filter_by(thread_id=thread_id).count() == 0
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_chat_persistence.py -v
```

Expected: `ImportError: cannot import name 'ChatMessageRow' from 'app.db'`.

- [ ] **Step 3: Add the models**

Append to `apps/api/app/db.py`, after `SummaryRow`:

```python
# ---------------------------------------------------------------------------
# Assistant conversations
# ---------------------------------------------------------------------------


class ChatThreadRow(Base):
    """One conversation with the assistant.

    Threads are per-user. The assistant reads the database on the operator's
    behalf, so a thread must never be visible to another account.
    """

    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, index=True
    )

    messages: Mapped[list["ChatMessageRow"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", passive_deletes=True
    )


class ChatMessageRow(Base):
    """One turn.

    `tool_trace`, `citations` and `blocks` are stored so reopening a thread
    replays exactly what the operator saw, including which tools ran. An answer
    whose workings cannot be reread is an answer that cannot be audited.
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="user")
    """user | assistant"""
    content: Mapped[str] = mapped_column(Text, default="")
    tool_trace: Mapped[list] = mapped_column(JSON, default=list)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    thread: Mapped["ChatThreadRow"] = relationship(back_populates="messages")
```

If `relationship` is not already imported in `db.py`, add it to the existing `from sqlalchemy.orm import ...` line.

- [ ] **Step 4: Write the migration**

Create `apps/api/migrations/versions/b1c2d3e4f5a6_chat_threads.py`:

```python
"""Assistant conversation threads.

Revision ID: b1c2d3e4f5a6
Revises: 96eb30bf1679
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "96eb30bf1679"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])
    op.create_index("ix_chat_threads_updated_at", "chat_threads", ["updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "thread_id",
            sa.String(32),
            sa.ForeignKey("chat_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), server_default="user"),
        sa.Column("content", sa.Text(), server_default=""),
        sa.Column("tool_trace", sa.JSON(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
```

- [ ] **Step 5: Apply the migration and run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m alembic upgrade head && .venv/Scripts/python.exe -m pytest tests/test_chat_persistence.py tests/test_migrations.py -v
```

Expected: PASS. `test_migrations.py` must stay green — it checks the model metadata matches the migrations.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/db.py apps/api/migrations/versions/b1c2d3e4f5a6_chat_threads.py apps/api/tests/test_chat_persistence.py
git commit -m "feat(ai): persist assistant conversation threads"
```

---

### Task 2: Tool registry

**Files:**
- Create: `apps/api/app/services/ai_agent/__init__.py`, `apps/api/app/services/ai_agent/registry.py`
- Create: `apps/api/app/services/ai_agent/tools/__init__.py`
- Test: `apps/api/tests/test_ai_tool_registry.py`

**Interfaces:**
- Produces:
  - `class ToolError(Exception)` — a tool failed in a way the model should be told about.
  - `@register(name: str, description: str, args_model: type[BaseModel], label: str)` decorator over `handler(session: Session, args: BaseModel) -> dict`.
  - `REGISTRY: dict[str, ToolDef]`
  - `openai_tools() -> list[dict]`
  - `execute(session: Session, name: str, raw_args: dict) -> dict`
  - `describe_tools() -> str` — plain-text catalogue for the planner transport.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_tool_registry.py`:

```python
"""The registry is the only way a tool becomes reachable by the model."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.services.ai_agent import registry  # noqa: E402


class _Args(BaseModel):
    n: int = 1


@pytest.fixture()
def sample_tool():
    @registry.register(
        name="_sample", description="A sample.", args_model=_Args, label="Sampling"
    )
    def _handler(session, args: _Args) -> dict:
        return {"doubled": args.n * 2}

    yield "_sample"
    registry.REGISTRY.pop("_sample", None)


def test_schema_is_emitted_in_openai_shape(sample_tool):
    schema = next(t for t in registry.openai_tools() if t["function"]["name"] == "_sample")
    assert schema["type"] == "function"
    assert schema["function"]["description"] == "A sample."
    assert "n" in schema["function"]["parameters"]["properties"]


def test_execute_validates_and_dispatches(sample_tool):
    assert registry.execute(None, "_sample", {"n": 21}) == {"doubled": 42}


def test_unknown_tool_is_refused():
    with pytest.raises(registry.ToolError, match="Unknown tool"):
        registry.execute(None, "definitely_not_a_tool", {})


def test_bad_arguments_are_refused_not_coerced(sample_tool):
    with pytest.raises(registry.ToolError, match="Invalid arguments"):
        registry.execute(None, "_sample", {"n": "not a number"})


def test_catalogue_names_every_registered_tool(sample_tool):
    assert "_sample" in registry.describe_tools()
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tool_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.ai_agent'`.

- [ ] **Step 3: Create the package**

Create `apps/api/app/services/ai_agent/__init__.py`:

```python
"""The read-only assistant agent.

Tools read the database; the model chooses which to call and writes the prose
around the results. Every figure and every record reference in a reply is
checked against what the tools actually returned — see `guards.py`.
"""
```

Create `apps/api/app/services/ai_agent/tools/__init__.py`:

```python
"""Tool implementations. Importing this package registers every tool."""

from . import analytics, electors, geography, pipeline, quality, sql  # noqa: F401
```

Leave the imports failing for now; Task 3 onwards fills them in. To keep this task independently testable, write the file as an empty docstring for now and add the imports in Task 8:

```python
"""Tool implementations. Importing this package registers every tool."""
```

- [ ] **Step 4: Write the registry**

Create `apps/api/app/services/ai_agent/registry.py`:

```python
"""Tool declaration and dispatch.

A tool is reachable by the model only if it is registered here. That is the
point: the surface the model can touch is a list you can read in one sitting,
not "whatever the ORM exposes".

Handlers return plain data — rows, counts, payloads — never prose. Turning a
result into something a human reads is `blocks.py`'s job, and writing the
sentences around it is the model's.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """A tool could not run.

    Raised rather than returned, and reported back to the model as a failed
    step, so it answers without that data instead of inventing it.
    """


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    args_model: Type[BaseModel]
    handler: Callable[[Optional[Session], BaseModel], Dict[str, Any]]
    #: Short present-tense phrase shown in the UI trace while the tool runs.
    label: str


REGISTRY: Dict[str, ToolDef] = {}


def register(
    *, name: str, description: str, args_model: Type[BaseModel], label: str
) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    """Declare a tool. Re-registering a name replaces it, which keeps reloads sane."""

    def decorate(handler: Callable[..., Dict[str, Any]]):
        REGISTRY[name] = ToolDef(
            name=name,
            description=description,
            args_model=args_model,
            handler=handler,
            label=label,
        )
        return handler

    return decorate


def _parameters_schema(args_model: Type[BaseModel]) -> Dict[str, Any]:
    """Pydantic's JSON schema, flattened enough for the providers to accept it."""
    schema = args_model.model_json_schema()
    schema.pop("title", None)
    schema.pop("$defs", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    schema.setdefault("type", "object")
    return schema


def openai_tools() -> List[Dict[str, Any]]:
    """The `tools` array for a provider that supports native function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": _parameters_schema(tool.args_model),
            },
        }
        for tool in REGISTRY.values()
    ]


def describe_tools() -> str:
    """A plain-text catalogue, for models without native tool calling."""
    lines = []
    for tool in REGISTRY.values():
        props = _parameters_schema(tool.args_model).get("properties", {})
        args = ", ".join(sorted(props)) or "no arguments"
        lines.append(f"- {tool.name}({args}): {tool.description}")
    return "\n".join(lines)


def label_for(name: str) -> str:
    tool = REGISTRY.get(name)
    return tool.label if tool else name


def execute(
    session: Optional[Session], name: str, raw_args: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate the model's arguments, then run the tool.

    Arguments are rejected rather than coerced. A model that passes a string
    where a part number's row count belongs has misunderstood the question, and
    guessing on its behalf produces a confident answer to the wrong query.
    """
    tool = REGISTRY.get(name)
    if tool is None:
        raise ToolError(
            f"Unknown tool {name!r}. Available: {', '.join(sorted(REGISTRY))}"
        )

    try:
        args = tool.args_model.model_validate(raw_args or {})
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'args'}: {e['msg']}"
            for e in exc.errors()[:4]
        )
        raise ToolError(f"Invalid arguments for {name}: {problems}") from exc

    try:
        result = tool.handler(session, args)
    except ToolError:
        raise
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        raise ToolError(f"{name} failed: {type(exc).__name__}") from exc

    if not isinstance(result, dict):
        raise ToolError(f"{name} returned {type(result).__name__}, expected an object")
    return result
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tool_registry.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ai_agent apps/api/tests/test_ai_tool_registry.py
git commit -m "feat(ai): add typed tool registry for the assistant"
```

---

### Task 3: Elector tools

**Files:**
- Create: `apps/api/app/services/ai_agent/tools/electors.py`
- Test: `apps/api/tests/test_ai_tools_electors.py`

**Interfaces:**
- Consumes: `registry.register`, `registry.ToolError`; `VoterRow` from `app.db`; `resolve_household` from `app.routers.voters` (extracted in Step 3).
- Produces tools `search_voters`, `get_voter`, `household_of`. Every elector dict returned carries at least `id`, `epic`, `name`, `part_number` — `guards.collect_citations` (Task 8) recognises a citable record by the presence of both `id` and `epic`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_tools_electors.py`:

```python
"""Elector lookup tools.

The fixture population lives in its own part so counts are exact regardless of
what else is in the development database — the same approach as
`test_infographic.py`.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import electors  # noqa: F401,E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"
PEOPLE = [
    ("Muthu Vel", "TNAI0000001", 72, "Male", "12"),
    ("Kamala Devi", "TNAI0000002", 53, "Female", "12"),
    ("Divya R", "TNAI0000003", 25, "Female", "44"),
]


@pytest.fixture(scope="module")
def sample_part():
    with session_scope() as s:
        for name, epic, age, gender, house in PEOPLE:
            s.add(
                VoterRow(
                    id=uuid.uuid4().hex[:32],
                    epic=epic,
                    name=name,
                    age=age,
                    gender=gender,
                    house_number=house,
                    part_number=PART,
                    constituency="Test Constituency",
                    search_text=f"{name} {epic} {house} {PART}".lower(),
                )
            )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_search_filters_to_the_part(sample_part):
    result = _run("search_voters", {"part_number": sample_part})
    assert result["total"] == 3
    assert {r["epic"] for r in result["rows"]} == {e for _, e, _, _, _ in PEOPLE}


def test_search_rows_carry_the_fields_a_citation_needs(sample_part):
    row = _run("search_voters", {"part_number": sample_part})["rows"][0]
    for key in ("id", "epic", "name", "part_number"):
        assert key in row


def test_search_honours_the_limit(sample_part):
    assert len(_run("search_voters", {"part_number": sample_part, "limit": 2})["rows"]) == 2


def test_search_by_gender_and_age(sample_part):
    result = _run(
        "search_voters", {"part_number": sample_part, "gender": "Female", "max_age": 30}
    )
    assert [r["name"] for r in result["rows"]] == ["Divya R"]


def test_get_voter_by_epic_returns_provenance(sample_part):
    result = _run("get_voter", {"epic": "TNAI0000001"})
    assert result["voter"]["name"] == "Muthu Vel"
    assert "provenance" in result
    assert "ocr_fields" in result


def test_get_voter_refuses_an_unknown_epic():
    with pytest.raises(registry.ToolError, match="No elector"):
        _run("get_voter", {"epic": "NOSUCHEPIC1"})


def test_get_voter_requires_an_identifier():
    with pytest.raises(registry.ToolError, match="voter_id or epic"):
        _run("get_voter", {})


def test_household_groups_by_house_number(sample_part):
    result = _run("household_of", {"epic": "TNAI0000001"})
    assert result["household"]["house_number"] == "12"
    assert result["household"]["size"] == 2
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_electors.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.ai_agent.tools.electors'`.

- [ ] **Step 3: Extract the household resolver so the tool and the endpoint share it**

`apps/api/app/routers/voters.py` currently builds the household inline in its family-tree endpoint (the code returning `{"target_voter_id": ..., "household": {...}, "families": [...]}` around lines 300-380). Move that body into a module-level function in the same file, above the endpoint:

```python
def resolve_household(session: Session, voter_id: str) -> dict:
    """Household and resolved families for one elector.

    Extracted from the endpoint so the assistant's `household_of` tool answers
    with exactly what the Family tab shows. Two code paths producing two
    different households for the same person is a bug waiting to be reported as
    a data problem.
    """
```

Move the existing implementation verbatim into it, and reduce the endpoint to:

```python
    return resolve_household(session, voter_id)
```

Do not change behaviour. Confirm with `pytest tests/test_family_tree_solver.py -v` after the move.

- [ ] **Step 4: Write the tools**

Create `apps/api/app/services/ai_agent/tools/electors.py`:

```python
"""Row-level lookup over the curated voter table.

These are the tools that let the assistant answer "who", not just "how many".
Every row carries `id` and `epic` so `guards.collect_citations` can bind a
citation to it; a record the model mentions that these tools did not return is
stripped before the reply leaves the server.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....db import OCRBlockRow, VoterRow
from ..registry import ToolError, register

#: A model that asks for 500 rows is trying to read the table rather than
#: answer a question, and the prompt cannot hold them anyway.
MAX_ROWS = 50


class SearchVotersArgs(BaseModel):
    search: Optional[str] = Field(None, description="Free text over name, EPIC, house, part")
    name: Optional[str] = None
    epic: Optional[str] = None
    part_number: Optional[str] = None
    constituency: Optional[str] = None
    gender: Optional[str] = Field(None, description="Male | Female | Third Gender")
    house_number: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    verified: Optional[bool] = None
    is_supplement: Optional[bool] = None
    source_file_id: Optional[str] = None
    limit: int = Field(20, ge=1, le=MAX_ROWS)
    offset: int = Field(0, ge=0)


def _row(voter: VoterRow) -> Dict[str, Any]:
    return {
        "id": voter.id,
        "epic": voter.epic,
        "name": voter.name,
        "age": voter.age,
        "gender": voter.gender,
        "relation_type": voter.relation_type,
        "relation_name": voter.relation_name,
        "house_number": voter.house_number,
        "part_number": voter.part_number,
        "constituency": voter.constituency,
        "verified": bool(voter.verified),
        "is_supplement": bool(voter.is_supplement),
    }


def _apply(stmt, args: SearchVotersArgs):
    if args.search:
        stmt = stmt.where(VoterRow.search_text.like(f"%{args.search.strip().lower()}%"))
    if args.name:
        stmt = stmt.where(VoterRow.name.like(f"%{args.name.strip()}%"))
    if args.epic:
        stmt = stmt.where(VoterRow.epic == args.epic.strip().upper())
    if args.part_number:
        stmt = stmt.where(VoterRow.part_number == args.part_number.strip())
    if args.constituency:
        stmt = stmt.where(VoterRow.constituency == args.constituency.strip())
    if args.gender:
        stmt = stmt.where(VoterRow.gender == args.gender.strip())
    if args.house_number:
        stmt = stmt.where(VoterRow.house_number.like(f"%{args.house_number.strip()}%"))
    if args.min_age is not None:
        stmt = stmt.where(VoterRow.age >= args.min_age)
    if args.max_age is not None:
        stmt = stmt.where(VoterRow.age <= args.max_age)
    if args.verified is not None:
        stmt = stmt.where(VoterRow.verified.is_(args.verified))
    if args.is_supplement is not None:
        stmt = stmt.where(VoterRow.is_supplement.is_(args.is_supplement))
    if args.source_file_id:
        stmt = stmt.where(VoterRow.source_file_id == args.source_file_id.strip())
    return stmt


@register(
    name="search_voters",
    description=(
        "Find electors on the curated roll by name, EPIC, part, constituency, "
        "gender, age range, house number, verification state or source file. "
        "Returns matching rows and the total number matched."
    ),
    args_model=SearchVotersArgs,
    label="Searching electors",
)
def search_voters(session: Session, args: SearchVotersArgs) -> Dict[str, Any]:
    total = session.execute(
        _apply(select(func.count()).select_from(VoterRow), args)
    ).scalar_one()

    stmt = _apply(select(VoterRow), args).order_by(
        VoterRow.part_number, VoterRow.serial, VoterRow.name
    )
    rows = session.execute(stmt.limit(args.limit).offset(args.offset)).scalars().all()

    return {
        "rows": [_row(v) for v in rows],
        "returned": len(rows),
        "total": total,
        "truncated": total > args.offset + len(rows),
    }


class GetVoterArgs(BaseModel):
    voter_id: Optional[str] = None
    epic: Optional[str] = None


def _find_one(session: Session, voter_id: Optional[str], epic: Optional[str]) -> VoterRow:
    if not voter_id and not epic:
        raise ToolError("Provide voter_id or epic.")
    stmt = select(VoterRow)
    stmt = (
        stmt.where(VoterRow.id == voter_id.strip())
        if voter_id
        else stmt.where(VoterRow.epic == (epic or "").strip().upper())
    )
    voter = session.execute(stmt).scalar_one_or_none()
    if voter is None:
        raise ToolError(f"No elector found for {voter_id or epic!r}.")
    return voter


@register(
    name="get_voter",
    description=(
        "Fetch one elector in full by voter_id or EPIC, including the OCR "
        "field confidences and the page the record was read from."
    ),
    args_model=GetVoterArgs,
    label="Opening elector record",
)
def get_voter(session: Session, args: GetVoterArgs) -> Dict[str, Any]:
    voter = _find_one(session, args.voter_id, args.epic)

    blocks: List[Dict[str, Any]] = []
    if voter.source_record_id:
        found = (
            session.execute(
                select(OCRBlockRow).where(OCRBlockRow.record_id == voter.source_record_id)
            )
            .scalars()
            .all()
        )
        blocks = [
            {
                "field_name": b.field_name,
                "raw_text": b.raw_text,
                "corrected_text": b.corrected_text,
                "confidence": round(float(b.confidence or 0.0), 3),
                "bbox": [b.bbox_x0, b.bbox_y0, b.bbox_x1, b.bbox_y1],
            }
            for b in found
        ]

    return {
        "voter": {**_row(voter), "serial": voter.serial, "notes": voter.notes},
        "provenance": {
            "source_file_id": voter.source_file_id,
            "source_file_name": voter.source_file_name,
            "page_id": voter.page_id,
            "page_number": voter.page_number,
            "source_record_id": voter.source_record_id,
            "polling_station_id": voter.polling_station_id,
        },
        "ocr_fields": blocks,
    }


class HouseholdArgs(BaseModel):
    voter_id: Optional[str] = None
    epic: Optional[str] = None


@register(
    name="household_of",
    description=(
        "The household an elector belongs to and the families resolved within "
        "it, with the evidence behind each link. Same result as the Family tab."
    ),
    args_model=HouseholdArgs,
    label="Resolving household",
)
def household_of(session: Session, args: HouseholdArgs) -> Dict[str, Any]:
    from ....routers.voters import resolve_household

    voter = _find_one(session, args.voter_id, args.epic)
    return resolve_household(session, voter.id)
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_electors.py tests/test_family_tree_solver.py -v
```

Expected: all pass. If `household_of` returns a household of size 3 rather than 2, the extracted resolver is grouping by part rather than house number — reread the moved code, do not adjust the test.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ai_agent/tools/electors.py apps/api/app/routers/voters.py apps/api/tests/test_ai_tools_electors.py
git commit -m "feat(ai): add elector search, lookup and household tools"
```

---

### Task 4: Analytics tool

**Files:**
- Create: `apps/api/app/services/ai_agent/tools/analytics.py`
- Test: `apps/api/tests/test_ai_tools_analytics.py`

**Interfaces:**
- Consumes: `infographic.validate_spec`, `infographic.build_infographic`, `infographic.catalogue`, `infographic.SpecError` — all unchanged.
- Produces tool `aggregate`, returning `{"infographic": <the existing chart payload>}`. Task 10's `blocks.py` renders that key as a `chart` block using the existing `InfographicCard`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_tools_analytics.py`:

```python
"""The aggregate tool is a thin, validating wrapper over infographic.py.

It must not become a second implementation of the metric vocabulary: the
guarantee that a chart's numbers came from SQL lives in one module, and that is
where it stays.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import analytics  # noqa: F401,E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def sample_part():
    with session_scope() as s:
        for i, (gender, age) in enumerate(
            [("Male", 40), ("Male", 60), ("Female", 30)]
        ):
            s.add(
                VoterRow(
                    id=uuid.uuid4().hex[:32],
                    epic=f"TNAG{i:07d}",
                    name=f"Person {i}",
                    age=age,
                    gender=gender,
                    part_number=PART,
                    search_text=f"person {i} {PART}".lower(),
                )
            )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)


def _run(args):
    with session_scope() as s:
        return registry.execute(s, "aggregate", args)


def test_counts_come_from_sql(sample_part):
    result = _run({"metric": "voter_count", "filters": {"part_number": sample_part}})
    assert result["infographic"]["total"] == 3


def test_breakdown_returns_a_series(sample_part):
    chart = _run(
        {
            "metric": "voter_count",
            "dimension": "gender",
            "filters": {"part_number": sample_part},
        }
    )["infographic"]
    assert {p["label"]: p["value"] for p in chart["series"]} == {"Male": 2, "Female": 1}


def test_an_unknown_metric_is_refused_with_the_vocabulary(sample_part):
    with pytest.raises(registry.ToolError) as exc:
        _run({"metric": "vibes"})
    assert "voter_count" in str(exc.value)


def test_the_tool_description_lists_the_metric_keys():
    assert "voter_count" in registry.REGISTRY["aggregate"].description
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_analytics.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.ai_agent.tools.analytics'`.

- [ ] **Step 3: Write the tool**

Create `apps/api/app/services/ai_agent/tools/analytics.py`:

```python
"""Aggregates, delegated whole to `infographic.py`.

This module deliberately contains no SQL. `infographic.py` exists precisely so
that one closed vocabulary decides what can be measured and one code path
computes it; a second aggregate implementation living in the agent would let the
two disagree, and the operator would have no way to tell which was right.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....services import infographic as info
from ..registry import ToolError, register

_METRIC_KEYS = ", ".join(sorted(info.METRICS))
_DIMENSION_KEYS = ", ".join(sorted(info.DIMENSIONS))
_FILTER_KEYS = ", ".join(sorted(info.FILTERS))


class AggregateArgs(BaseModel):
    metric: str = Field(..., description=f"One of: {_METRIC_KEYS}")
    dimension: Optional[str] = Field(None, description=f"One of: {_DIMENSION_KEYS}")
    filters: Optional[Dict[str, Any]] = Field(
        None, description=f"Any of: {_FILTER_KEYS}"
    )
    title: Optional[str] = Field(None, description="Short label, six words or fewer")


@register(
    name="aggregate",
    description=(
        "Compute a figure over the roll, optionally broken down and filtered. "
        f"Metrics: {_METRIC_KEYS}. Dimensions: {_DIMENSION_KEYS}. "
        f"Filters: {_FILTER_KEYS}. Returns a chart payload whose values were "
        "computed by SQL."
    ),
    args_model=AggregateArgs,
    label="Computing aggregate",
)
def aggregate(session: Session, args: AggregateArgs) -> Dict[str, Any]:
    try:
        spec = info.validate_spec(
            {
                "metric": args.metric,
                "dimension": args.dimension,
                "filters": args.filters or {},
                "title": args.title,
            }
        )
    except info.SpecError as exc:
        raise ToolError(str(exc)) from exc

    return {"infographic": info.build_infographic(session, spec)}


def catalogue() -> Dict[str, Any]:
    """Re-exported for the system prompt, so the model sees the vocabulary."""
    return info.catalogue()
```

- [ ] **Step 4: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_analytics.py tests/test_infographic.py -v
```

Expected: all pass, including the untouched `test_infographic.py`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/ai_agent/tools/analytics.py apps/api/tests/test_ai_tools_analytics.py
git commit -m "feat(ai): expose infographic aggregates as an agent tool"
```

---

### Task 5: Quality tools

**Files:**
- Create: `apps/api/app/services/ai_agent/tools/quality.py`
- Test: `apps/api/tests/test_ai_tools_quality.py`

**Interfaces:**
- Consumes: `RecordRow`, `VoterRow`, `PollingStationRow`, `PageRow` from `app.db`.
- Produces tools `ocr_quality`, `low_confidence_records`, `find_anomalies`. `find_anomalies` accepts `kind` ∈ `duplicate_epic | implausible_age | missing_field | epic_format | count_mismatch`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_tools_quality.py`:

```python
"""Data-quality tools.

These answer the question the workspace cannot currently ask: not "how many
electors are there" but "which of these records should I not believe".
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import quality  # noqa: F401,E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def sample_part():
    """One good record, one with an impossible age, one missing its gender."""
    with session_scope() as s:
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000001", name="Good Record",
                age=45, gender="Male", part_number=PART, search_text="good",
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000002", name="Impossible Age",
                age=3, gender="Female", part_number=PART, search_text="impossible",
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000003", name="No Gender",
                age=30, gender="", part_number=PART, search_text="nogender",
            )
        )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_implausible_age_flags_only_the_child(sample_part):
    rows = _run("find_anomalies", {"kind": "implausible_age", "part_number": sample_part})["rows"]
    assert [r["epic"] for r in rows] == ["TNAQ0000002"]
    assert rows[0]["reason"]


def test_missing_field_flags_the_blank_gender(sample_part):
    rows = _run("find_anomalies", {"kind": "missing_field", "part_number": sample_part})["rows"]
    assert [r["epic"] for r in rows] == ["TNAQ0000003"]


def test_anomaly_rows_are_citable(sample_part):
    rows = _run("find_anomalies", {"kind": "implausible_age", "part_number": sample_part})["rows"]
    assert "id" in rows[0] and "epic" in rows[0]


def test_unknown_anomaly_kind_is_refused():
    with pytest.raises(registry.ToolError, match="Invalid arguments"):
        _run("find_anomalies", {"kind": "bad_vibes"})


def test_ocr_quality_for_a_part_reports_a_population(sample_part):
    result = _run("ocr_quality", {"scope": "part", "id": sample_part})
    assert result["population"] == 3
    assert "mean_confidence" in result


def test_low_confidence_records_respects_its_limit():
    result = _run("low_confidence_records", {"limit": 5})
    assert len(result["rows"]) <= 5
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_quality.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.ai_agent.tools.quality'`.

- [ ] **Step 3: Write the tools**

Create `apps/api/app/services/ai_agent/tools/quality.py`:

```python
"""Data quality: which records should not be believed, and why.

The OCR pipeline stores its own uncertainty — per-record `min_confidence`, per
-field block confidences, error and warning counts — and the roll prints its own
declared totals in `polling_stations`. Neither is currently surfaced as a
question anyone can ask. These tools make both askable.

Every flagged row says *why* it was flagged. A list of suspect records with no
stated reason is an accusation, not a finding.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Integer, distinct, func, select
from sqlalchemy.orm import Session

from ....db import PollingStationRow, RecordRow, VoterRow
from ..registry import ToolError, register

#: Matches `infographic.MIN_PLAUSIBLE_AGE`. An elector below this is a mis-read.
MIN_PLAUSIBLE_AGE = 18
#: Tamil Nadu EPIC numbers are three letters then seven digits.
EPIC_PATTERN = "^[A-Z]{3}[0-9]{7}$"
_EPIC_RE = re.compile(EPIC_PATTERN)


class OcrQualityArgs(BaseModel):
    scope: Literal["file", "page", "part", "all"] = "all"
    id: Optional[str] = Field(None, description="File id, page id or part number")


@register(
    name="ocr_quality",
    description=(
        "OCR confidence and review state for a file, page, part or the whole "
        "corpus: mean and minimum confidence, error and warning counts, how "
        "many records were edited or reviewed."
    ),
    args_model=OcrQualityArgs,
    label="Measuring OCR quality",
)
def ocr_quality(session: Session, args: OcrQualityArgs) -> Dict[str, Any]:
    if args.scope != "all" and not args.id:
        raise ToolError(f"scope={args.scope!r} needs an id.")

    stmt = select(
        func.count(),
        func.avg(RecordRow.mean_confidence),
        func.min(RecordRow.min_confidence),
        func.sum(RecordRow.error_count),
        func.sum(RecordRow.warning_count),
        func.sum(func.cast(RecordRow.edited, Integer)),
        func.sum(func.cast(RecordRow.reviewed, Integer)),
    ).select_from(RecordRow)

    if args.scope == "file":
        stmt = stmt.where(RecordRow.file_id == args.id)
    elif args.scope == "page":
        stmt = stmt.where(RecordRow.page_id == args.id)
    elif args.scope == "part":
        # Records carry no part number; the voters promoted from them do.
        pages = select(distinct(VoterRow.page_id)).where(VoterRow.part_number == args.id)
        stmt = stmt.where(RecordRow.page_id.in_(pages))

    count, mean_c, min_c, errors, warnings, edited, reviewed = session.execute(
        stmt
    ).one()

    population = count
    if args.scope == "part":
        population = session.execute(
            select(func.count()).select_from(VoterRow).where(VoterRow.part_number == args.id)
        ).scalar_one()

    return {
        "scope": args.scope,
        "id": args.id,
        "records": count,
        "population": population,
        "mean_confidence": round(float(mean_c), 3) if mean_c is not None else None,
        "min_confidence": round(float(min_c), 3) if min_c is not None else None,
        "error_count": int(errors or 0),
        "warning_count": int(warnings or 0),
        "edited": int(edited or 0),
        "reviewed": int(reviewed or 0),
    }


class LowConfidenceArgs(BaseModel):
    file_id: Optional[str] = None
    threshold: float = Field(0.75, ge=0.0, le=1.0)
    limit: int = Field(20, ge=1, le=50)


@register(
    name="low_confidence_records",
    description=(
        "OCR records whose minimum field confidence falls below a threshold, "
        "worst first. A review queue: which records to check by hand."
    ),
    args_model=LowConfidenceArgs,
    label="Ranking low-confidence records",
)
def low_confidence_records(session: Session, args: LowConfidenceArgs) -> Dict[str, Any]:
    stmt = select(RecordRow).where(RecordRow.min_confidence < args.threshold)
    if args.file_id:
        stmt = stmt.where(RecordRow.file_id == args.file_id)
    rows = (
        session.execute(stmt.order_by(RecordRow.min_confidence).limit(args.limit))
        .scalars()
        .all()
    )
    return {
        "threshold": args.threshold,
        "rows": [
            {
                "record_id": r.id,
                "file_id": r.file_id,
                "page_id": r.page_id,
                "page_number": r.page_number,
                "min_confidence": round(float(r.min_confidence or 0.0), 3),
                "mean_confidence": round(float(r.mean_confidence or 0.0), 3),
                "error_count": r.error_count,
                "reviewed": bool(r.reviewed),
            }
            for r in rows
        ],
        "returned": len(rows),
    }


class AnomalyArgs(BaseModel):
    kind: Literal[
        "duplicate_epic",
        "implausible_age",
        "missing_field",
        "epic_format",
        "count_mismatch",
    ]
    part_number: Optional[str] = None
    limit: int = Field(25, ge=1, le=50)


def _citable(voter: VoterRow, reason: str) -> Dict[str, Any]:
    return {
        "id": voter.id,
        "epic": voter.epic,
        "name": voter.name,
        "age": voter.age,
        "gender": voter.gender,
        "part_number": voter.part_number,
        "reason": reason,
    }


@register(
    name="find_anomalies",
    description=(
        "Records that look wrong. kind=duplicate_epic finds repeated EPIC "
        "numbers; implausible_age finds electors under 18; missing_field finds "
        "blank name, gender or house number; epic_format finds EPICs that do "
        "not match three letters and seven digits; count_mismatch compares each "
        "polling station's declared elector total against how many were "
        "actually extracted."
    ),
    args_model=AnomalyArgs,
    label="Scanning for anomalies",
)
def find_anomalies(session: Session, args: AnomalyArgs) -> Dict[str, Any]:
    def scoped(stmt):
        return stmt.where(VoterRow.part_number == args.part_number) if args.part_number else stmt

    rows: List[Dict[str, Any]] = []

    if args.kind == "implausible_age":
        found = session.execute(
            scoped(
                select(VoterRow).where(
                    VoterRow.age.is_not(None), VoterRow.age < MIN_PLAUSIBLE_AGE
                )
            ).order_by(VoterRow.age).limit(args.limit)
        ).scalars().all()
        rows = [
            _citable(v, f"Age {v.age} is below the minimum elector age of {MIN_PLAUSIBLE_AGE}.")
            for v in found
        ]

    elif args.kind == "missing_field":
        found = session.execute(
            scoped(
                select(VoterRow).where(
                    (VoterRow.name == "")
                    | (VoterRow.gender == "")
                    | (VoterRow.house_number == "")
                )
            ).limit(args.limit)
        ).scalars().all()
        for v in found:
            blank = [
                f for f in ("name", "gender", "house_number") if not getattr(v, f)
            ]
            rows = rows + [_citable(v, f"Blank: {', '.join(blank)}.")]

    elif args.kind == "epic_format":
        # SQLite has no built-in REGEXP, so the pattern is applied in Python
        # over a bounded scan rather than pushed into the query.
        found = session.execute(scoped(select(VoterRow)).limit(500)).scalars().all()
        rows = [
            _citable(v, f"EPIC {v.epic!r} does not match three letters then seven digits.")
            for v in found
            if not _EPIC_RE.match((v.epic or "").upper())
        ][: args.limit]

    elif args.kind == "duplicate_epic":
        # The voters table enforces uniqueness, so duplicates can only survive
        # upstream in the OCR records. That is where to look.
        dupes = session.execute(
            select(RecordRow.search_text, func.count())
            .where(RecordRow.search_text != "")
            .group_by(RecordRow.search_text)
            .having(func.count() > 1)
            .limit(args.limit)
        ).all()
        rows = [
            {"search_text": text[:120], "occurrences": n,
             "reason": "The same extracted text appears on more than one record."}
            for text, n in dupes
        ]

    else:  # count_mismatch
        stations = session.execute(
            select(PollingStationRow).limit(args.limit)
        ).scalars().all()
        for st in stations:
            extracted = session.execute(
                select(func.count())
                .select_from(VoterRow)
                .where(VoterRow.part_number == st.part_number)
            ).scalar_one()
            declared = int(st.total_electors or 0)
            if declared and extracted != declared:
                rows.append(
                    {
                        "part_number": st.part_number,
                        "station_name": st.name,
                        "declared_electors": declared,
                        "extracted_electors": extracted,
                        "difference": extracted - declared,
                        "reason": "The roll's printed total and the extracted count disagree.",
                    }
                )

    return {"kind": args.kind, "rows": rows, "returned": len(rows)}
```

- [ ] **Step 4: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_quality.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/ai_agent/tools/quality.py apps/api/tests/test_ai_tools_quality.py
git commit -m "feat(ai): add OCR quality and anomaly detection tools"
```

---

### Task 6: Pipeline and geography tools

**Files:**
- Create: `apps/api/app/services/ai_agent/tools/pipeline.py`, `apps/api/app/services/ai_agent/tools/geography.py`
- Test: `apps/api/tests/test_ai_tools_pipeline.py`

**Interfaces:**
- Consumes: `FileRow`, `PageRow`, `JobRow`, `PollingStationRow`, `VoterRow` from `app.db`.
- Produces tools `file_status`, `page_details`, `job_status`, `roll_overview`, `polling_station`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_tools_pipeline.py`:

```python
"""Pipeline and geography tools.

These let the assistant answer "what is the state of my corpus" — which files
are processed, which pages failed, what the roll covers — without the operator
navigating four different screens.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import geography, pipeline  # noqa: F401,E402


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_file_status_without_an_id_lists_every_file():
    result = _run("file_status", {})
    assert "files" in result
    assert isinstance(result["files"], list)


def test_file_status_refuses_an_unknown_file():
    with pytest.raises(registry.ToolError, match="No file"):
        _run("file_status", {"file_id": "definitely-not-a-file"})


def test_job_status_returns_a_list():
    assert isinstance(_run("job_status", {})["jobs"], list)


def test_roll_overview_reports_totals_and_coverage():
    result = _run("roll_overview", {})
    for key in ("voters", "files", "pages", "records", "parts", "constituencies"):
        assert key in result


def test_page_details_needs_an_identifier():
    with pytest.raises(registry.ToolError, match="page_id or"):
        _run("page_details", {})


def test_polling_station_needs_an_identifier():
    with pytest.raises(registry.ToolError, match="part_number or station_id"):
        _run("polling_station", {})
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_pipeline.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.ai_agent.tools.pipeline'`.

- [ ] **Step 3: Write the pipeline tools**

Create `apps/api/app/services/ai_agent/tools/pipeline.py`:

```python
"""The state of the OCR corpus: files, pages, jobs.

"Why are there only 3,473 electors when I uploaded six files?" is a pipeline
question, not a roll question, and until now the assistant could not tell the
difference.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ....db import FileRow, JobRow, PageRow, RecordRow
from ..registry import ToolError, register


class FileStatusArgs(BaseModel):
    file_id: Optional[str] = Field(None, description="Omit to list every file")


@register(
    name="file_status",
    description=(
        "Processing state of one uploaded PDF or of every file: status, pages "
        "done out of total, page count, template and any error."
    ),
    args_model=FileStatusArgs,
    label="Checking file status",
)
def file_status(session: Session, args: FileStatusArgs) -> Dict[str, Any]:
    stmt = select(FileRow).order_by(FileRow.created_at.desc())
    if args.file_id:
        stmt = stmt.where(FileRow.id == args.file_id.strip())

    files = session.execute(stmt.limit(50)).scalars().all()
    if args.file_id and not files:
        raise ToolError(f"No file with id {args.file_id!r}.")

    return {
        "files": [
            {
                "file_id": f.id,
                "name": f.name,
                "status": f.status,
                "page_count": f.page_count,
                "pages_done": f.pages_done,
                "size_bytes": f.size_bytes,
                "template_id": f.template_id,
                "languages": f.languages,
                "error": f.error,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in files
        ],
        "returned": len(files),
    }


class PageDetailsArgs(BaseModel):
    page_id: Optional[str] = None
    file_id: Optional[str] = None
    page_number: Optional[int] = None
    failed_only: bool = Field(False, description="With file_id, list only failed pages")


@register(
    name="page_details",
    description=(
        "One page, or the pages of a file: page type, classification "
        "confidence, OCR duration, error, and how many records it produced. "
        "Set failed_only to list just the pages that failed."
    ),
    args_model=PageDetailsArgs,
    label="Inspecting pages",
)
def page_details(session: Session, args: PageDetailsArgs) -> Dict[str, Any]:
    if not args.page_id and not args.file_id:
        raise ToolError("Provide page_id or file_id (optionally with page_number).")

    stmt = select(PageRow)
    if args.page_id:
        stmt = stmt.where(PageRow.id == args.page_id.strip())
    else:
        stmt = stmt.where(PageRow.file_id == args.file_id.strip())
        if args.page_number is not None:
            stmt = stmt.where(PageRow.page_number == args.page_number)
        if args.failed_only:
            stmt = stmt.where(PageRow.status == "failed")

    pages = session.execute(stmt.order_by(PageRow.page_number).limit(50)).scalars().all()
    if args.page_id and not pages:
        raise ToolError(f"No page with id {args.page_id!r}.")

    rows = []
    for p in pages:
        record_count = session.execute(
            select(func.count()).select_from(RecordRow).where(RecordRow.page_id == p.id)
        ).scalar_one()
        rows.append(
            {
                "page_id": p.id,
                "file_id": p.file_id,
                "page_number": p.page_number,
                "status": p.status,
                "page_type": p.page_type,
                "classification_confidence": round(float(p.classification_confidence or 0.0), 3),
                "template_id": p.template_id,
                "ocr_ms": p.ocr_ms,
                "error": p.error,
                "records": record_count,
            }
        )
    return {"pages": rows, "returned": len(rows)}


class JobStatusArgs(BaseModel):
    job_id: Optional[str] = Field(None, description="Omit for the most recent jobs")


@register(
    name="job_status",
    description=(
        "OCR job queue state: queued, running or finished, with completed and "
        "failed page counts and the item currently being processed."
    ),
    args_model=JobStatusArgs,
    label="Checking jobs",
)
def job_status(session: Session, args: JobStatusArgs) -> Dict[str, Any]:
    stmt = select(JobRow).order_by(JobRow.created_at.desc())
    if args.job_id:
        stmt = stmt.where(JobRow.id == args.job_id.strip())

    jobs = session.execute(stmt.limit(10)).scalars().all()
    if args.job_id and not jobs:
        raise ToolError(f"No job with id {args.job_id!r}.")

    return {
        "jobs": [
            {
                "job_id": j.id,
                "status": j.status,
                "file_ids": j.file_ids,
                "total_pages": j.total_pages,
                "completed_pages": j.completed_pages,
                "failed_pages": j.failed_pages,
                "current_item": j.current_item,
                "error": j.error,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in jobs
        ],
        "returned": len(jobs),
    }
```

- [ ] **Step 4: Write the geography tools**

Create `apps/api/app/services/ai_agent/tools/geography.py`:

```python
"""What the roll covers, and the polling stations behind it.

`polling_station` returns the station's *declared* elector counts alongside
what was actually extracted. Those two numbers disagreeing is the single most
useful integrity signal in the corpus, and nothing else surfaces it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from ....db import FileRow, PageRow, PollingStationRow, RecordRow, VoterRow
from ..registry import ToolError, register


class RollOverviewArgs(BaseModel):
    pass


@register(
    name="roll_overview",
    description=(
        "The shape of the corpus: how many electors, files, pages and records, "
        "which parts and constituencies are covered, and which polling "
        "stations exist. Use this first when a question is about scope."
    ),
    args_model=RollOverviewArgs,
    label="Reading roll overview",
)
def roll_overview(session: Session, _args: RollOverviewArgs) -> Dict[str, Any]:
    def count(model) -> int:
        return session.execute(select(func.count()).select_from(model)).scalar_one()

    parts = session.execute(
        select(distinct(VoterRow.part_number)).where(VoterRow.part_number != "")
    ).scalars().all()
    constituencies = session.execute(
        select(distinct(VoterRow.constituency)).where(VoterRow.constituency != "")
    ).scalars().all()

    return {
        "voters": count(VoterRow),
        "files": count(FileRow),
        "pages": count(PageRow),
        "records": count(RecordRow),
        "polling_stations": count(PollingStationRow),
        "parts": sorted(parts)[:100],
        "part_count": len(parts),
        "constituencies": sorted(constituencies)[:50],
    }


class PollingStationArgs(BaseModel):
    part_number: Optional[str] = None
    station_id: Optional[str] = None


@register(
    name="polling_station",
    description=(
        "A polling station's details and its declared elector counts, together "
        "with how many electors were actually extracted for that part. A "
        "difference between the two means the roll and the extraction disagree."
    ),
    args_model=PollingStationArgs,
    label="Reading polling station",
)
def polling_station(session: Session, args: PollingStationArgs) -> Dict[str, Any]:
    if not args.part_number and not args.station_id:
        raise ToolError("Provide part_number or station_id.")

    stmt = select(PollingStationRow)
    stmt = (
        stmt.where(PollingStationRow.id == args.station_id.strip())
        if args.station_id
        else stmt.where(PollingStationRow.part_number == (args.part_number or "").strip())
    )
    station = session.execute(stmt).scalars().first()
    if station is None:
        raise ToolError(f"No polling station for {args.station_id or args.part_number!r}.")

    extracted = session.execute(
        select(func.count())
        .select_from(VoterRow)
        .where(VoterRow.part_number == station.part_number)
    ).scalar_one()

    return {
        "station": {
            "station_id": station.id,
            "part_number": station.part_number,
            "name": station.name,
            "name_tam": station.name_tam,
            "building_name": station.building_name,
            "address": station.address,
            "district": station.district,
            "ac_number": station.ac_number,
            "ac_name": station.ac_name,
        },
        "declared": {
            "total_electors": station.total_electors,
            "male_electors": station.male_electors,
            "female_electors": station.female_electors,
            "third_gender_electors": station.third_gender_electors,
        },
        "extracted": {"total_electors": extracted},
        "difference": extracted - int(station.total_electors or 0),
    }
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_tools_pipeline.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ai_agent/tools/pipeline.py apps/api/app/services/ai_agent/tools/geography.py apps/api/tests/test_ai_tools_pipeline.py
git commit -m "feat(ai): add pipeline state and roll geography tools"
```

---

### Task 7: The guarded read-only SQL escape hatch

**This is the highest-risk task in the plan.** The tests are the deliverable as much as the code. Do not weaken a test to make an implementation pass.

**Files:**
- Create: `apps/api/app/services/ai_agent/tools/sql.py`
- Test: `apps/api/tests/test_ai_sql_guard.py`

**Interfaces:**
- Consumes: `database_url` from `app.db`, `settings` from `app.config`.
- Produces: `ALLOWED_TABLES: frozenset[str]`, `class SqlGuardError(ToolError)`, `guard_sql(sql: str) -> str` (returns the wrapped, limited statement), and the tool `run_readonly_sql`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_sql_guard.py`:

```python
"""The SQL guard.

A parser is not a security boundary, so this is tested as an attack surface
rather than as a feature. Every case below is a thing the model might emit —
whether by misunderstanding, by following a badly worded question, or because
something upstream told it to.

The rule that matters most: `app_settings` holds the NVIDIA API key. The
assistant must never be able to read its own credentials out of the database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import sql as sqltool  # noqa: E402


def _guard(statement: str):
    return sqltool.guard_sql(statement)


# --- what must be refused --------------------------------------------------

@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE voters SET verified = 1",
        "DELETE FROM voters",
        "INSERT INTO voters (id) VALUES ('x')",
        "DROP TABLE voters",
        "ALTER TABLE voters ADD COLUMN x TEXT",
        "CREATE TABLE evil (id TEXT)",
        "PRAGMA table_info(voters)",
        "ATTACH DATABASE 'other.db' AS other",
        "VACUUM",
    ],
)
def test_writes_and_ddl_are_refused(statement):
    with pytest.raises(sqltool.SqlGuardError):
        _guard(statement)


def test_multiple_statements_are_refused():
    with pytest.raises(sqltool.SqlGuardError, match="one statement"):
        _guard("SELECT 1; DROP TABLE voters")


def test_comments_are_refused_outright():
    # Comments are how keyword scanning gets defeated. Rejecting them is
    # cheaper than trying to parse around them.
    with pytest.raises(sqltool.SqlGuardError, match="[Cc]omment"):
        _guard("SELECT id FROM voters -- DROP TABLE voters")
    with pytest.raises(sqltool.SqlGuardError, match="[Cc]omment"):
        _guard("SELECT /* sneaky */ id FROM voters")


@pytest.mark.parametrize("table", ["app_settings", "users", "sessions"])
def test_the_forbidden_tables_are_unreachable(table):
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard(f"SELECT * FROM {table}")


def test_the_api_key_cannot_be_reached_through_a_join():
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard("SELECT v.name, a.value FROM voters v JOIN app_settings a ON 1=1")


def test_the_api_key_cannot_be_reached_through_a_subquery():
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard("SELECT (SELECT value FROM app_settings LIMIT 1) AS leaked")


def test_a_cte_cannot_launder_a_forbidden_table():
    with pytest.raises(sqltool.SqlGuardError, match="not available"):
        _guard("WITH x AS (SELECT value FROM app_settings) SELECT * FROM x")


def test_a_bare_non_select_is_refused():
    with pytest.raises(sqltool.SqlGuardError, match="SELECT"):
        _guard("EXPLAIN SELECT 1")


# --- what must be allowed --------------------------------------------------

def test_a_plain_select_is_accepted_and_limited():
    guarded = _guard("SELECT name FROM voters")
    assert "LIMIT" in guarded.upper()


def test_a_cte_over_allowed_tables_is_accepted():
    guarded = _guard(
        "WITH per_part AS (SELECT part_number, COUNT(*) n FROM voters GROUP BY part_number) "
        "SELECT * FROM per_part"
    )
    assert "LIMIT" in guarded.upper()


def test_a_join_across_allowed_tables_is_accepted():
    _guard("SELECT v.name FROM voters v JOIN pages p ON p.id = v.page_id")


# --- end to end ------------------------------------------------------------

def _run(args):
    with session_scope() as s:
        return registry.execute(s, "run_readonly_sql", args)


def test_the_tool_returns_rows_and_echoes_the_sql():
    result = _run({"sql": "SELECT COUNT(*) AS n FROM voters", "rationale": "count"})
    assert result["columns"] == ["n"]
    assert isinstance(result["rows"][0]["n"], int)
    assert "voters" in result["sql"]


def test_the_tool_reports_a_refusal_as_a_tool_error():
    with pytest.raises(registry.ToolError, match="not available"):
        _run({"sql": "SELECT * FROM app_settings", "rationale": "leak the key"})


def test_results_are_capped():
    result = _run({"sql": "SELECT id FROM voters", "rationale": "all ids"})
    assert len(result["rows"]) <= sqltool.ROW_LIMIT
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_sql_guard.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.ai_agent.tools.sql'`.

- [ ] **Step 3: Write the guard and the tool**

Create `apps/api/app/services/ai_agent/tools/sql.py`:

```python
"""A read-only SQL escape hatch, for the questions the typed tools do not cover.

Layered on purpose. A regex parser can be fooled, so it is not the only thing
standing between the model and the database:

1.  Reject anything that is not a single SELECT or WITH.
2.  Reject comments outright — they are how keyword scans get defeated.
3.  Require every referenced table to be on an allowlist. Not a denylist: a
    denylist is a list of the attacks someone thought of.
4.  Execute on a connection opened read-only at the OS level, so a bypass of
    1-3 still cannot write.
5.  Cap rows and wall-clock time.

`app_settings` is excluded because it stores the NVIDIA API key. An assistant
able to select its own credentials out of the database is one prompt away from
printing them into a chat transcript.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ....config import settings
from ....db import database_url
from ..registry import ToolError, register

logger = logging.getLogger(__name__)

#: Everything the assistant may read. Adding a table here is a deliberate act.
ALLOWED_TABLES = frozenset(
    {
        "voters",
        "records",
        "pages",
        "files",
        "polling_stations",
        "photos",
        "ocr_blocks",
        "jobs",
        "summaries",
        "audit_logs",
    }
)

ROW_LIMIT = 200
TIMEOUT_SECONDS = 5.0

_FORBIDDEN_KEYWORD = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|"
    r"vacuum|reindex|begin|commit|rollback|truncate|grant|revoke)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--|/\*|\*/|#)")
#: Every position a table name can appear in a SELECT we accept.
_TABLE_REF = re.compile(r"\b(?:from|join)\s+[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
#: Names introduced by a CTE are not real tables and must not be allowlisted.
_CTE_NAME = re.compile(r"(?:\bwith\s+|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", re.IGNORECASE)


class SqlGuardError(ToolError):
    """The statement was refused. The reason is shown to the operator."""


def guard_sql(raw: str) -> str:
    """Validate a statement and return the wrapped, row-limited form.

    Raises `SqlGuardError` with a reason the operator can read. The reason is
    deliberately specific: "not available" for a forbidden table tells them the
    assistant tried, and what it tried, which is information they should have.
    """
    statement = (raw or "").strip()
    if not statement:
        raise SqlGuardError("No SQL was provided.")

    if _COMMENT.search(statement):
        raise SqlGuardError("SQL comments are not allowed.")

    statement = statement.rstrip(";").strip()
    if ";" in statement:
        raise SqlGuardError("Only one statement may be run at a time.")

    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        raise SqlGuardError("Only a SELECT (or WITH … SELECT) may be run.")

    forbidden = _FORBIDDEN_KEYWORD.search(statement)
    if forbidden:
        raise SqlGuardError(
            f"{forbidden.group(1).upper()} is not permitted; this tool is read-only."
        )

    cte_names = {name.lower() for name in _CTE_NAME.findall(statement)}
    referenced = {name.lower() for name in _TABLE_REF.findall(statement)}
    for table in sorted(referenced - cte_names):
        if table not in ALLOWED_TABLES:
            raise SqlGuardError(
                f"The table {table!r} is not available to the assistant. "
                f"Readable tables: {', '.join(sorted(ALLOWED_TABLES))}."
            )

    return f"SELECT * FROM (\n{statement}\n) LIMIT {ROW_LIMIT}"


def _readonly_connection() -> sqlite3.Connection:
    """A connection the operating system will not let us write through.

    Belt and braces. If the parser above were ever bypassed, this is what still
    stands between a crafted statement and the database.
    """
    if not database_url().startswith("sqlite"):
        raise SqlGuardError(
            "The SQL tool is available only on SQLite deployments. "
            "Use the typed tools instead."
        )

    path = (settings.data_dir / "ocr.sqlite").as_posix()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row

    deadline = time.monotonic() + TIMEOUT_SECONDS

    def _abort_when_out_of_time() -> int:
        # A non-zero return aborts the query.
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(_abort_when_out_of_time, 10_000)
    return conn


class RunSqlArgs(BaseModel):
    sql: str = Field(..., description="A single SELECT or WITH … SELECT statement")
    rationale: str = Field(
        ..., description="One sentence: what this query is for. Shown to the operator."
    )


@register(
    name="run_readonly_sql",
    description=(
        "Run one read-only SELECT when no other tool can answer the question. "
        f"Readable tables: {', '.join(sorted(ALLOWED_TABLES))}. Results are "
        f"capped at {ROW_LIMIT} rows and the SQL is shown to the operator. "
        "Prefer a typed tool whenever one fits."
    ),
    args_model=RunSqlArgs,
    label="Running SQL",
)
def run_readonly_sql(_session: Session, args: RunSqlArgs) -> Dict[str, Any]:
    guarded = guard_sql(args.sql)

    conn = _readonly_connection()
    try:
        cursor = conn.execute(guarded)
        fetched = cursor.fetchall()
        columns: List[str] = [d[0] for d in (cursor.description or [])]
    except sqlite3.OperationalError as exc:
        raise SqlGuardError(f"The query could not run: {exc}") from exc
    finally:
        conn.close()

    rows = [dict(zip(columns, tuple(row))) for row in fetched]
    logger.info("Assistant SQL (%s) returned %d rows", args.rationale[:80], len(rows))

    return {
        "sql": args.sql.strip(),
        "rationale": args.rationale,
        "columns": columns,
        "rows": rows,
        "returned": len(rows),
        "truncated": len(rows) >= ROW_LIMIT,
    }
```

- [ ] **Step 4: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_sql_guard.py -v
```

Expected: all pass. If `test_a_cte_over_allowed_tables_is_accepted` fails, `_CTE_NAME` is not matching the CTE alias — fix the regex, do not add the alias to `ALLOWED_TABLES`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/ai_agent/tools/sql.py apps/api/tests/test_ai_sql_guard.py
git commit -m "feat(ai): add guarded read-only SQL escape hatch"
```

---

### Task 8: Answer guards and render blocks

**Files:**
- Create: `apps/api/app/services/ai_agent/guards.py`, `apps/api/app/services/ai_agent/blocks.py`
- Modify: `apps/api/app/services/ai_agent/tools/__init__.py` (import every tool module)
- Test: `apps/api/tests/test_ai_guards.py`

**Interfaces:**
- Produces:
  - `permitted_numbers(tool_results: list[dict]) -> set[str]`
  - `strip_unverified_numbers(text: str, allowed: set[str]) -> tuple[str, int]`
  - `collect_citations(tool_results: list[dict]) -> dict[str, dict]` — keyed by voter id; a mapping counts as citable when it has both `id` and `epic`.
  - `bind_citations(text: str, known: dict[str, dict]) -> tuple[str, list[dict]]`
  - `blocks_for(tool_name: str, result: dict) -> list[dict]` — block kinds `table | voter_card | chart | sql`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_guards.py`:

```python
"""The guards that make the assistant's answers checkable.

`infographic.py` established the rule: the model does not produce numbers. The
agent widens the aperture — the model may now quote any figure a tool returned —
without widening the licence. Anything else still goes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ai_agent import blocks, guards  # noqa: E402

TOOL_RESULTS = [
    {
        "rows": [
            {"id": "v1", "epic": "TNAI0000001", "name": "Muthu Vel", "age": 72},
            {"id": "v2", "epic": "TNAI0000002", "name": "Kamala Devi", "age": 53},
        ],
        "total": 412,
    }
]


def test_numbers_from_tool_results_are_permitted():
    allowed = guards.permitted_numbers(TOOL_RESULTS)
    assert "412" in allowed and "72" in allowed


def test_a_sentence_quoting_a_real_figure_survives():
    text = "There are 412 electors in this part."
    kept, dropped = guards.strip_unverified_numbers(text, guards.permitted_numbers(TOOL_RESULTS))
    assert kept == text
    assert dropped == 0


def test_a_sentence_quoting_an_invented_figure_is_dropped():
    text = "There are 412 electors. Roughly 900 of them are women."
    kept, dropped = guards.strip_unverified_numbers(text, guards.permitted_numbers(TOOL_RESULTS))
    assert "900" not in kept
    assert "412" in kept
    assert dropped == 1


def test_numbers_inside_identifiers_are_permitted():
    # An EPIC contains digits and is not a claim about quantity.
    allowed = guards.permitted_numbers(TOOL_RESULTS)
    text = "Muthu Vel holds EPIC TNAI0000001."
    kept, dropped = guards.strip_unverified_numbers(text, allowed)
    assert dropped == 0


def test_citations_are_collected_from_any_nesting_depth():
    known = guards.collect_citations(TOOL_RESULTS)
    assert set(known) == {"v1", "v2"}
    assert known["v1"]["name"] == "Muthu Vel"


def test_a_known_marker_is_kept_and_reported():
    known = guards.collect_citations(TOOL_RESULTS)
    text, cited = guards.bind_citations("See [[v:v1]] for the household.", known)
    assert "[[v:v1]]" in text
    assert [c["id"] for c in cited] == ["v1"]


def test_an_invented_marker_is_stripped():
    known = guards.collect_citations(TOOL_RESULTS)
    text, cited = guards.bind_citations("See [[v:ghost]] and [[v:v2]].", known)
    assert "ghost" not in text
    assert [c["id"] for c in cited] == ["v2"]


def test_search_results_become_a_table_block():
    made = blocks.blocks_for("search_voters", TOOL_RESULTS[0])
    assert made[0]["kind"] == "table"
    assert "name" in made[0]["columns"]


def test_an_aggregate_becomes_a_chart_block():
    made = blocks.blocks_for("aggregate", {"infographic": {"title": "Electors", "series": []}})
    assert made[0]["kind"] == "chart"
    assert made[0]["infographic"]["title"] == "Electors"


def test_sql_results_become_a_sql_block_and_a_table():
    made = blocks.blocks_for(
        "run_readonly_sql",
        {"sql": "SELECT 1", "columns": ["n"], "rows": [{"n": 1}], "rationale": "why"},
    )
    kinds = [b["kind"] for b in made]
    assert kinds == ["sql", "table"]
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_guards.py -v
```

Expected: `ImportError: cannot import name 'blocks'`.

- [ ] **Step 3: Write the guards**

Create `apps/api/app/services/ai_agent/guards.py`:

```python
"""What makes an answer checkable.

`infographic.py` states the principle: a number the model typed cannot be
verified, so it must not reach the operator. That module enforced it against a
single chart payload. Here the same rule is enforced against every tool result
in the turn — which is what lets the assistant finally say "412 electors"
without letting it say "roughly 400".

Record references work the same way. The model cites electors as `[[v:<id>]]`
markers; a marker naming a record the tools did not return is removed before the
reply leaves the server. There are no hallucinated electors.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Set, Tuple

logger = logging.getLogger(__name__)

_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKER = re.compile(r"\[\[v:([A-Za-z0-9_-]{1,40})\]\]")


def _walk(value: Any) -> Iterable[Any]:
    """Every scalar anywhere inside a tool result."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def permitted_numbers(tool_results: List[Dict[str, Any]]) -> Set[str]:
    """Every numeric string the model is allowed to echo back.

    Generous within the results and closed outside them: a count may legitimately
    be quoted rounded, and an identifier such as an EPIC or a part code contains
    digits that are not claims about quantity.
    """
    allowed: Set[str] = set()
    for scalar in _walk(tool_results):
        if scalar is None or isinstance(scalar, bool):
            continue
        if isinstance(scalar, (int, float)):
            allowed.add(f"{float(scalar):g}")
            allowed.add(str(int(scalar)))
            allowed.add(str(int(scalar) + 1))  # a rate may be rounded either way
        else:
            for run in _DIGITS.findall(str(scalar)):
                allowed.add(run)
    return allowed


def strip_unverified_numbers(text: str, allowed: Set[str]) -> Tuple[str, int]:
    """Drop any sentence quoting a figure no tool produced.

    The sentence goes whole rather than having the number edited out of it: a
    claim with its figure removed reads as though it were still supported.
    """
    kept: List[str] = []
    dropped = 0
    for sentence in _SENTENCE.split(text or ""):
        candidate = sentence.strip()
        if not candidate:
            continue
        invented = [
            run for run in _DIGITS.findall(candidate.replace(",", "")) if run not in allowed
        ]
        if invented:
            dropped += 1
            logger.warning(
                "Discarded an assistant sentence quoting unverified figures %s: %r",
                invented, candidate,
            )
            continue
        kept.append(candidate)
    return " ".join(kept), dropped


def collect_citations(tool_results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Every elector the tools actually returned, keyed by id.

    A mapping counts as a citable record when it carries both `id` and `epic`.
    That is the contract the elector tools honour, and it means a new tool
    becomes citable simply by returning rows in the same shape.
    """
    found: Dict[str, Dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "id" in value and "epic" in value:
                found[str(value["id"])] = {
                    "id": str(value["id"]),
                    "epic": value.get("epic"),
                    "name": value.get("name"),
                    "part_number": value.get("part_number"),
                }
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(tool_results)
    return found


def bind_citations(
    text: str, known: Dict[str, Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]]]:
    """Keep markers naming a returned record; delete the rest."""
    cited: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def replace(match: "re.Match[str]") -> str:
        voter_id = match.group(1)
        record = known.get(voter_id)
        if record is None:
            logger.warning("Stripped a citation to an unknown record %r", voter_id)
            return ""
        if voter_id not in seen:
            seen.add(voter_id)
            cited.append(record)
        return match.group(0)

    bound = _MARKER.sub(replace, text or "")
    return re.sub(r"[ \t]{2,}", " ", bound).strip(), cited
```

- [ ] **Step 4: Write the block builder**

Create `apps/api/app/services/ai_agent/blocks.py`:

```python
"""Tool result → what the panel renders.

Deliberately not the model's job. Asking a language model to emit a table is
asking it to retype data it was just given, and a retyped table is a table with
a typo in it. The model writes the prose; the rows come straight from the tool.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: Column order for elector tables. Anything not listed is dropped, so a tool
#: that starts returning a new field does not silently widen the table.
_VOTER_COLUMNS = (
    "name", "epic", "age", "gender", "relation_name",
    "house_number", "part_number", "verified",
)


def _table(rows: List[Dict[str, Any]], columns: List[str], **extra: Any) -> Dict[str, Any]:
    return {
        "kind": "table",
        "columns": columns,
        "rows": [{c: row.get(c) for c in columns} for row in rows],
        **extra,
    }


def blocks_for(tool_name: str, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The render blocks one tool result produces. Never more than two."""
    if tool_name == "aggregate":
        chart = result.get("infographic")
        return [{"kind": "chart", "infographic": chart}] if chart else []

    if tool_name == "get_voter":
        return [
            {
                "kind": "voter_card",
                "voter": result.get("voter") or {},
                "provenance": result.get("provenance") or {},
                "ocr_fields": result.get("ocr_fields") or [],
            }
        ]

    if tool_name == "run_readonly_sql":
        rows = result.get("rows") or []
        columns = result.get("columns") or []
        made: List[Dict[str, Any]] = [
            {
                "kind": "sql",
                "sql": result.get("sql", ""),
                "rationale": result.get("rationale", ""),
                "returned": result.get("returned", len(rows)),
            }
        ]
        if rows:
            made.append(_table(rows, list(columns)))
        return made

    rows = result.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        first = rows[0]
        if "epic" in first:
            columns = [c for c in _VOTER_COLUMNS if c in first]
            if "reason" in first:
                columns = columns + ["reason"]
        else:
            columns = list(first.keys())[:8]
        return [
            _table(
                rows,
                columns,
                total=result.get("total"),
                truncated=bool(result.get("truncated")),
            )
        ]

    for key in ("files", "pages", "jobs"):
        listed = result.get(key)
        if isinstance(listed, list) and listed and isinstance(listed[0], dict):
            return [_table(listed, list(listed[0].keys())[:8])]

    return []
```

- [ ] **Step 5: Wire every tool module into the package**

Replace `apps/api/app/services/ai_agent/tools/__init__.py` with:

```python
"""Tool implementations. Importing this package registers every tool."""

from . import analytics, electors, geography, pipeline, quality, sql  # noqa: F401
```

- [ ] **Step 6: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_guards.py tests/test_ai_tool_registry.py -v
```

Expected: all pass.

- [ ] **Step 7: Confirm every tool registered**

```bash
cd apps/api && .venv/Scripts/python.exe -c "from app.services.ai_agent import tools; from app.services.ai_agent.registry import REGISTRY; print(len(REGISTRY), sorted(REGISTRY))"
```

Expected: `13` and the names `aggregate, file_status, find_anomalies, get_voter, household_of, job_status, low_confidence_records, ocr_quality, page_details, polling_station, roll_overview, run_readonly_sql, search_voters`.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/ai_agent/guards.py apps/api/app/services/ai_agent/blocks.py apps/api/app/services/ai_agent/tools/__init__.py apps/api/tests/test_ai_guards.py
git commit -m "feat(ai): add answer guards and render-block builder"
```

---

### Task 9: Intent router and roll profile

**Files:**
- Create: `apps/api/app/services/ai_agent/router.py`, `apps/api/app/services/ai_agent/context.py`
- Test: `apps/api/tests/test_ai_router.py`

**Interfaces:**
- Consumes: `AiCredentials` from `app.services.app_settings`; `_chat` from `app.services.nvidia_ai_service` (existing private helper — used, not modified).
- Produces:
  - `Intent = Literal["smalltalk", "howto", "data"]`
  - `classify(message: str, creds: AiCredentials | None = None) -> Intent`
  - `roll_profile(session: Session) -> dict` and `profile_sentence(profile: dict) -> str`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_router.py`:

```python
"""Routing decides which model answers, and therefore how fast the reply is.

The fast path exists because commit 1784600 measured it at 0.44s. A router that
sends "hi" into the agent loop throws that away, so the heuristics are tested
without any model configured — they must stand on their own.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.services.ai_agent import context, router  # noqa: E402


@pytest.mark.parametrize(
    "message",
    [
        "hello",
        "thanks!",
        "who are you",
        "வணக்கம்",
    ],
)
def test_conversational_messages_take_the_fast_path(message):
    assert router.classify(message) == "smalltalk"


@pytest.mark.parametrize(
    "message",
    [
        "how do I export to Excel?",
        "where is the column chooser",
        "how to mark a record verified",
    ],
)
def test_application_questions_take_the_fast_path(message):
    assert router.classify(message) == "howto"


@pytest.mark.parametrize(
    "message",
    [
        "how many voters are in part 289?",
        "voters by gender",
        "find electors named Muthu",
        "which pages failed OCR",
        "show me the household at house 12",
        "what is the average age",
        "list low confidence records",
        "எத்தனை வாக்காளர்கள் உள்ளனர்",
        "பாலினம் வாரியாக",
    ],
)
def test_data_questions_enter_the_agent_loop(message):
    assert router.classify(message) == "data"


def test_an_empty_message_is_not_a_data_question():
    assert router.classify("") == "smalltalk"


def test_roll_profile_reports_the_shape_of_the_corpus():
    with session_scope() as s:
        profile = context.roll_profile(s)
    for key in ("voters", "files", "parts", "constituencies"):
        assert key in profile


def test_profile_sentence_is_prose_not_json():
    sentence = context.profile_sentence(
        {"voters": 3473, "files": 6, "parts": ["289"], "constituencies": ["Test"], "part_count": 1}
    )
    assert "3473" in sentence or "3,473" in sentence
    assert "{" not in sentence
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_router.py -v
```

Expected: `ImportError: cannot import name 'router'`.

- [ ] **Step 3: Write the router**

Create `apps/api/app/services/ai_agent/router.py`:

```python
"""Which tier answers this message.

Commit 1784600 bought a 0.44s reply by moving to a small model. That is worth
keeping, so a greeting or a "how do I export" never pays for a tool-calling
round trip. Only questions about the *data* enter the agent loop.

Heuristics decide first and decide most messages. A model call is spent only
when the heuristics are genuinely unsure, and if that call fails the message is
treated as a data question — answering slowly beats answering wrongly.
"""

from __future__ import annotations

import logging
import re
from typing import Literal, Optional

from ..app_settings import AiCredentials

logger = logging.getLogger(__name__)

Intent = Literal["smalltalk", "howto", "data"]


#: Asking about the roll's contents, its quality, or the pipeline's state.
_DATA_CUES = (
    "how many", "count", "total", "average", "percentage", "percent", "share",
    "breakdown", "distribution", "compare", "statistic", "stats", "summary",
    "chart", "graph", "infographic", "list", "find", "search", "show me",
    "who is", "who are", "which", "epic", "part ", "constituency", "household",
    "family", "house number", "verified", "unverified", "supplement",
    "confidence", "anomal", "duplicate", "failed", "error", "job", "page ",
    "polling station", "voter", "elector",
    # Tamil
    "எத்தனை", "சராசரி", "விளக்கப்படம்", "சுருக்கம்", "புள்ளிவிவரம்", "மொத்தம்",
    "வாரியாக", "வாரியான", "அடிப்படையில்", "வாக்காளர்", "பகுதி",
)

#: Asking how to operate the workspace. Answered from the guide, not the data.
_HOWTO_CUES = (
    "how do i", "how to", "how can i", "where is", "where do i", "what does the",
    "can i export", "keyboard shortcut", "which button",
)

#: A greeting, thanks, or a question about the assistant itself.
_SMALLTALK = re.compile(
    r"^\s*(hi|hey|hello|yo|thanks|thank you|ok|okay|cool|bye|good (morning|evening)|"
    r"who are you|what are you|what can you do|help|வணக்கம்|நன்றி)\b",
    re.IGNORECASE,
)

_CLASSIFY_PROMPT = (
    "Classify the user's message for an electoral-roll OCR workspace. Reply with "
    "exactly one word and nothing else:\n"
    "data — asks about the contents of the roll, record quality, or processing state\n"
    "howto — asks how to use the application\n"
    "smalltalk — a greeting, thanks, or a question about you\n"
)


def _heuristic(message: str) -> Optional[Intent]:
    msg = (message or "").strip().lower()
    if not msg:
        return "smalltalk"

    has_data = any(cue in msg for cue in _DATA_CUES)
    has_howto = any(cue in msg for cue in _HOWTO_CUES)

    # "how do I filter by gender" is about the application even though it names
    # a dimension, so a how-to phrasing wins when both fire.
    if has_howto:
        return "howto"
    if has_data:
        return "data"
    if _SMALLTALK.match(msg):
        return "smalltalk"
    return None


def classify(message: str, creds: Optional[AiCredentials] = None) -> Intent:
    """Route one message. Falls back to the slow, correct path when unsure."""
    decided = _heuristic(message)
    if decided is not None:
        return decided

    if creds is None or not creds.configured:
        return "data"

    from ..nvidia_ai_service import _chat

    outcome = _chat(
        [
            {"role": "system", "content": _CLASSIFY_PROMPT},
            {"role": "user", "content": (message or "").strip()[:400]},
        ],
        creds,
        temperature=0.0,
        max_tokens=8,
    )
    word = (outcome.content or "").strip().lower()
    for intent in ("data", "howto", "smalltalk"):
        if intent in word:
            return intent  # type: ignore[return-value]

    logger.info("Router could not classify %r; treating as a data question", message[:60])
    return "data"
```

- [ ] **Step 4: Write the roll profile**

Create `apps/api/app/services/ai_agent/context.py`:

```python
"""What the model is told about the corpus before it is asked anything.

Without this, the first tool call of nearly every conversation is spent
discovering that the roll covers one constituency and six files. Putting the
shape of the data in the system prompt removes a round trip from most turns.

Cached, because it is read on every message and changes only when files are
processed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

#: Long enough to save the repeated queries, short enough that a finished import
#: shows up while the operator is still looking at the screen.
_TTL_SECONDS = 60.0

_cached: Optional[Tuple[float, Dict[str, Any]]] = None


def roll_profile(session: Session, *, force: bool = False) -> Dict[str, Any]:
    """Counts and coverage, straight from `roll_overview`."""
    global _cached

    now = time.monotonic()
    if not force and _cached is not None and now - _cached[0] < _TTL_SECONDS:
        return _cached[1]

    from .registry import execute
    from . import tools  # noqa: F401  (registers the tools)

    profile = execute(session, "roll_overview", {})
    _cached = (now, profile)
    return profile


def invalidate() -> None:
    """Drop the cache. Call after a file finishes processing."""
    global _cached
    _cached = None


def profile_sentence(profile: Dict[str, Any]) -> str:
    """The profile as prose, for the system prompt.

    Prose rather than JSON: a small model reads a sentence more reliably than it
    reads a nested object, and this text is prepended to every single turn.
    """
    parts = profile.get("parts") or []
    constituencies = profile.get("constituencies") or []

    lines = [
        f"This workspace holds {profile.get('voters', 0):,} curated electors "
        f"from {profile.get('files', 0)} uploaded roll files "
        f"({profile.get('pages', 0)} pages, {profile.get('records', 0)} OCR records)."
    ]
    if constituencies:
        lines.append("Constituencies: " + ", ".join(str(c) for c in constituencies[:5]) + ".")
    if parts:
        shown = ", ".join(str(p) for p in parts[:10])
        total = profile.get("part_count", len(parts))
        lines.append(
            f"Parts covered ({total}): {shown}" + (", …" if total > 10 else "") + "."
        )
    return " ".join(lines)
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_router.py -v
```

Expected: all pass. If a Tamil case fails, the cue is missing from `_DATA_CUES` — add it rather than relaxing the test.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ai_agent/router.py apps/api/app/services/ai_agent/context.py apps/api/tests/test_ai_router.py
git commit -m "feat(ai): add intent router and cached roll profile"
```

---

### Task 10: Streaming and tool-calling transports

**Files:**
- Modify: `apps/api/app/services/nvidia_ai_service.py` (append only — change nothing existing)
- Test: `apps/api/tests/test_ai_transport.py`

**Interfaces:**
- Produces:
  - `stream_chat(messages, creds, *, temperature, max_tokens) -> Iterator[str]` — yields content deltas.
  - `chat_with_tools(messages, creds, tools, *, temperature, max_tokens) -> ToolCallOutcome`
  - `@dataclass(frozen=True) ToolCallOutcome(content: str | None, tool_calls: list[dict], error: str | None, status: int | None, unsupported: bool)`
  - `supports_native_tools(model: str) -> bool | None` and `remember_tool_support(model: str, supported: bool) -> None`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_transport.py`:

```python
"""The two new ways of calling the provider.

No network. The HTTP layer is stubbed so the parsing — which is where the bugs
live — is tested directly.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.services import nvidia_ai_service as svc  # noqa: E402
from app.services.app_settings import AiCredentials  # noqa: E402

CREDS = AiCredentials(api_key="test-key", base_url="https://example.invalid/v1", model="test-model")


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _sse(*frames: str) -> _FakeResponse:
    body = "".join(f"data: {f}\n\n" for f in frames) + "data: [DONE]\n\n"
    return _FakeResponse(body.encode("utf-8"))


def test_stream_chat_yields_content_deltas(monkeypatch):
    frames = [
        json.dumps({"choices": [{"delta": {"content": "There are "}}]}),
        json.dumps({"choices": [{"delta": {"content": "412 electors."}}]}),
    ]
    monkeypatch.setattr(svc.urllib.request, "urlopen", lambda *a, **k: _sse(*frames))
    assert "".join(svc.stream_chat([], CREDS, temperature=0.3, max_tokens=64)) == (
        "There are 412 electors."
    )


def test_stream_chat_ignores_frames_without_content(monkeypatch):
    frames = [
        json.dumps({"choices": [{"delta": {"role": "assistant"}}]}),
        json.dumps({"choices": [{"delta": {"content": "ok"}}]}),
        "not json at all",
    ]
    monkeypatch.setattr(svc.urllib.request, "urlopen", lambda *a, **k: _sse(*frames))
    assert "".join(svc.stream_chat([], CREDS, temperature=0.3, max_tokens=64)) == "ok"


def test_chat_with_tools_parses_a_tool_call(monkeypatch):
    body = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "search_voters",
                                "arguments": '{"part_number": "289"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    monkeypatch.setattr(
        svc.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(json.dumps(body).encode())
    )
    outcome = svc.chat_with_tools([], CREDS, [], temperature=0.2, max_tokens=256)
    assert outcome.tool_calls[0]["name"] == "search_voters"
    assert outcome.tool_calls[0]["arguments"] == {"part_number": "289"}


def test_malformed_tool_arguments_do_not_crash_the_parse(monkeypatch):
    body = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"id": "c", "function": {"name": "search_voters", "arguments": "{oops"}}
                    ]
                }
            }
        ]
    }
    monkeypatch.setattr(
        svc.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(json.dumps(body).encode())
    )
    outcome = svc.chat_with_tools([], CREDS, [], temperature=0.2, max_tokens=256)
    assert outcome.tool_calls[0]["arguments"] == {}


def test_tool_support_is_remembered_per_model():
    svc.remember_tool_support("model-a", False)
    svc.remember_tool_support("model-b", True)
    assert svc.supports_native_tools("model-a") is False
    assert svc.supports_native_tools("model-b") is True
    assert svc.supports_native_tools("model-never-seen") is None


def test_existing_behaviour_is_untouched():
    # The legacy path must keep working exactly as before.
    assert svc.wants_infographic("voters by gender") is True
    assert svc.local_infographic_spec("voters by gender")["dimension"] == "gender"
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_transport.py -v
```

Expected: `AttributeError: module 'app.services.nvidia_ai_service' has no attribute 'stream_chat'`.

- [ ] **Step 3: Append the transports**

Append to `apps/api/app/services/nvidia_ai_service.py`, at the end of the file. Change nothing above it.

```python
# ---------------------------------------------------------------------------
# Transports for the agent
#
# Two additions, both additive: a streaming call so a long answer appears as it
# is written rather than after twenty seconds of silence, and a tool-calling
# call so the model can ask for data instead of guessing at it.
#
# Everything above this line keeps its existing behaviour; the legacy
# `/api/voters/ai-copilot` path does not go through here.
# ---------------------------------------------------------------------------

#: Whether a given model accepted a `tools` array. Learned on first refusal
#: rather than hard-coded, because the provider's catalogue changes and an
#: operator can type any model name into the Settings page.
_TOOL_SUPPORT: Dict[str, bool] = {}


def supports_native_tools(model: str) -> Optional[bool]:
    """True, False, or None when it has not been tried yet."""
    return _TOOL_SUPPORT.get(model)


def remember_tool_support(model: str, supported: bool) -> None:
    _TOOL_SUPPORT[model] = supported


def _request(payload: Dict[str, Any], creds: AiCredentials, *, stream: bool):
    return urllib.request.Request(
        f"{creds.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "Authorization": f"Bearer {creds.api_key}",
        },
        method="POST",
    )


def stream_chat(
    messages: List[Dict[str, Any]],
    creds: AiCredentials,
    *,
    temperature: float,
    max_tokens: int,
):
    """Yield content deltas as the model writes them.

    A generator rather than a return value: the caller forwards each fragment to
    the browser, so the operator watches the answer form instead of watching a
    spinner. Errors are yielded as text — an exception mid-stream would leave a
    half-written bubble with no explanation in it.
    """
    payload = {
        "model": creds.model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        with urllib.request.urlopen(_request(payload, creds, stream=True), timeout=60) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    frame = json.loads(data)
                except ValueError:
                    continue
                for choice in frame.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        yield delta
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        yield f"\n\n[{_explain_http_error(exc.code, detail, creds.model)}]"
    except (socket.timeout, TimeoutError):
        yield "\n\n[The provider stopped responding while writing the answer.]"
    except Exception as exc:
        logger.warning("Streaming call failed: %s", type(exc).__name__)
        yield f"\n\n[The answer could not be completed: {type(exc).__name__}.]"


@dataclass(frozen=True)
class ToolCallOutcome:
    """One turn of a tool-calling conversation."""

    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    status: Optional[int] = None
    #: True when the provider rejected the request because of the tools array,
    #: which is how a model without function calling announces itself.
    unsupported: bool = False


def chat_with_tools(
    messages: List[Dict[str, Any]],
    creds: AiCredentials,
    tools: List[Dict[str, Any]],
    *,
    temperature: float,
    max_tokens: int,
) -> ToolCallOutcome:
    """One call that may come back asking for data instead of answering."""
    if not creds.configured:
        return ToolCallOutcome(error="No API key is configured.")

    payload: Dict[str, Any] = {
        "model": creds.model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        with urllib.request.urlopen(_request(payload, creds, stream=False), timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        # A 400 mentioning tools or functions means this model cannot do it.
        unsupported = exc.code == 400 and bool(
            re.search(r"tool|function", detail, re.IGNORECASE)
        )
        if unsupported:
            logger.info("%s does not support native tool calling", creds.model)
        return ToolCallOutcome(
            error=_explain_http_error(exc.code, detail, creds.model),
            status=exc.code,
            unsupported=unsupported,
        )
    except (socket.timeout, TimeoutError):
        return ToolCallOutcome(error="The provider timed out.")
    except Exception as exc:
        logger.warning("Tool call failed: %s", type(exc).__name__)
        return ToolCallOutcome(error=f"Unexpected failure: {type(exc).__name__}.")

    choices = body.get("choices") or []
    if not choices:
        return ToolCallOutcome(error="The provider returned no choices.", status=200)

    message = choices[0].get("message") or {}
    calls: List[Dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw_args = function.get("arguments")
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except ValueError:
            logger.info("Model emitted unparseable tool arguments: %r", raw_args)
            parsed = {}
        calls.append(
            {
                "id": call.get("id") or f"call_{len(calls)}",
                "name": function.get("name") or "",
                "arguments": parsed if isinstance(parsed, dict) else {},
            }
        )

    return ToolCallOutcome(
        content=(message.get("content") or "").strip() or None,
        tool_calls=calls,
        status=200,
    )
```

Add `field` to the existing dataclasses import at the top of the file:

```python
from dataclasses import dataclass, field
```

- [ ] **Step 4: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_transport.py tests/test_nvidia_ai_service.py -v
```

Expected: all pass, including the pre-existing suite.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/nvidia_ai_service.py apps/api/tests/test_ai_transport.py
git commit -m "feat(ai): add streaming and tool-calling transports"
```

---

### Task 11: The agent loop

**Files:**
- Create: `apps/api/app/services/ai_agent/loop.py`
- Modify: `apps/api/app/services/ai_agent/__init__.py` (re-export `run_agent`)
- Test: `apps/api/tests/test_ai_loop.py`

**Interfaces:**
- Consumes: `registry.execute`, `registry.openai_tools`, `registry.describe_tools`, `registry.label_for`, `registry.ToolError`; `guards.*`; `blocks.blocks_for`; `context.roll_profile`, `context.profile_sentence`; `nvidia_ai_service.chat_with_tools`, `stream_chat`, `supports_native_tools`, `remember_tool_support`.
- Produces:
  - `@dataclass(frozen=True) AgentEvent(type: str, data: dict)` — `type` ∈ `status | tool_call | tool_result | token | blocks | citations | done | error`.
  - `run_agent(session, message, *, creds, history=None, app_context=None) -> Iterator[AgentEvent]`
  - Budget constants `MAX_ROUNDS = 4`, `MAX_TOOL_CALLS = 6`, `DEADLINE_SECONDS = 20.0`.

**Streaming and the number guard.** The final prose is streamed, but a sentence is forwarded to the browser only once it is complete *and* has passed `strip_unverified_numbers`. Streaming raw tokens would put an unverified figure on screen before the guard could see it, and a figure the operator has already read cannot be unread. Sentence-level granularity keeps the guarantee absolute while still showing the answer as it forms.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_loop.py`:

```python
"""The agent loop, driven by a scripted model.

No network: `chat_with_tools` and `stream_chat` are replaced, so what is under
test is the loop's own behaviour — how it dispatches tools, how it respects its
budgets, and what it does when something fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.services.ai_agent import loop  # noqa: E402
from app.services.app_settings import AiCredentials  # noqa: E402
from app.services.nvidia_ai_service import ToolCallOutcome  # noqa: E402

CREDS = AiCredentials(api_key="k", base_url="https://example.invalid/v1", model="test-model")


def _script(monkeypatch, outcomes, answer="Done."):
    """Make the model return `outcomes` in order, then stream `answer`."""
    remaining = list(outcomes)

    def fake_tools(*_a, **_k):
        return remaining.pop(0) if remaining else ToolCallOutcome(content="")

    monkeypatch.setattr(loop, "chat_with_tools", fake_tools)
    monkeypatch.setattr(loop, "stream_chat", lambda *a, **k: iter([answer]))
    monkeypatch.setattr(loop, "supports_native_tools", lambda _m: True)


def _drain(message):
    with session_scope() as s:
        return list(loop.run_agent(s, message, creds=CREDS))


def _types(events):
    return [e.type for e in events]


def test_an_answer_with_no_tools_still_completes(monkeypatch):
    _script(monkeypatch, [ToolCallOutcome(content="")], answer="Nothing to look up.")
    events = _drain("tell me about the workspace")
    assert "done" in _types(events)
    assert "Nothing to look up." in events[-1].data["content"]


def test_a_tool_call_is_dispatched_and_reported(monkeypatch):
    _script(
        monkeypatch,
        [
            ToolCallOutcome(
                tool_calls=[{"id": "c1", "name": "roll_overview", "arguments": {}}]
            ),
            ToolCallOutcome(content=""),
        ],
        answer="The corpus is small.",
    )
    events = _drain("what does the roll cover")
    assert "tool_call" in _types(events)
    assert "tool_result" in _types(events)
    call = next(e for e in events if e.type == "tool_call")
    assert call.data["name"] == "roll_overview"


def test_a_failing_tool_is_reported_not_hidden(monkeypatch):
    _script(
        monkeypatch,
        [
            ToolCallOutcome(
                tool_calls=[{"id": "c1", "name": "get_voter", "arguments": {}}]
            ),
            ToolCallOutcome(content=""),
        ],
        answer="I could not find that elector.",
    )
    events = _drain("who is voter nobody")
    result = next(e for e in events if e.type == "tool_result")
    assert result.data["ok"] is False
    assert "voter_id or epic" in result.data["error"]


def test_an_unknown_tool_name_does_not_stop_the_turn(monkeypatch):
    _script(
        monkeypatch,
        [
            ToolCallOutcome(
                tool_calls=[{"id": "c1", "name": "invent_data", "arguments": {}}]
            ),
            ToolCallOutcome(content=""),
        ],
        answer="I cannot do that.",
    )
    events = _drain("do something impossible")
    assert "done" in _types(events)
    result = next(e for e in events if e.type == "tool_result")
    assert "Unknown tool" in result.data["error"]


def test_the_tool_call_budget_is_enforced(monkeypatch):
    always_calling = [
        ToolCallOutcome(tool_calls=[{"id": f"c{i}", "name": "roll_overview", "arguments": {}}])
        for i in range(20)
    ]
    _script(monkeypatch, always_calling, answer="Ran out.")
    events = _drain("keep going forever")
    assert len([e for e in events if e.type == "tool_call"]) <= loop.MAX_TOOL_CALLS
    assert "done" in _types(events)


def test_an_invented_figure_never_reaches_the_client(monkeypatch):
    _script(
        monkeypatch,
        [ToolCallOutcome(content="")],
        answer="The roll holds 999999 electors.",
    )
    events = _drain("how many electors are there")
    done = events[-1]
    assert "999999" not in done.data["content"]


def test_a_provider_error_becomes_an_error_event(monkeypatch):
    monkeypatch.setattr(
        loop, "chat_with_tools", lambda *a, **k: ToolCallOutcome(error="The API key was rejected.")
    )
    monkeypatch.setattr(loop, "supports_native_tools", lambda _m: True)
    events = _drain("how many electors")
    assert "error" in _types(events)
    assert "API key" in events[-1].data["message"]


def test_native_refusal_falls_back_to_the_planner(monkeypatch):
    calls = {"n": 0}

    def fake_tools(messages, creds, tools, **_k):
        calls["n"] += 1
        if tools:
            return ToolCallOutcome(error="bad request", status=400, unsupported=True)
        return ToolCallOutcome(content='{"answer": "Planner answered."}')

    monkeypatch.setattr(loop, "chat_with_tools", fake_tools)
    monkeypatch.setattr(loop, "stream_chat", lambda *a, **k: iter(["Planner answered."]))
    monkeypatch.setattr(loop, "supports_native_tools", lambda _m: None)
    recorded = {}
    monkeypatch.setattr(
        loop, "remember_tool_support", lambda model, ok: recorded.setdefault(model, ok)
    )

    events = _drain("how many electors")
    assert recorded == {"test-model": False}
    assert "done" in _types(events)


def test_no_credentials_produces_an_error_event():
    blank = AiCredentials(api_key="", base_url="", model="")
    with session_scope() as s:
        events = list(loop.run_agent(s, "how many electors", creds=blank))
    assert events[-1].type == "error"
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_loop.py -v
```

Expected: `ImportError: cannot import name 'loop'`.

- [ ] **Step 3: Write the loop**

Create `apps/api/app/services/ai_agent/loop.py`:

```python
"""The agent loop.

Bounded on purpose. An agent with no budget is an agent that can spend an
operator's afternoon and a provider's quota on a question that had no answer,
and the failure mode is silence rather than an error. Four rounds, six calls,
twenty seconds; past that it says so.

Two transports, one loop. A model with native function calling gets a `tools`
array; one without gets a catalogue and is asked for JSON. The second exists
because the configured model is chosen from a Settings page, and an operator
who picks an 8B model should get a working assistant rather than a broken one.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy.orm import Session

from ..app_settings import AiCredentials
from ..nvidia_ai_service import (
    ToolCallOutcome,
    chat_with_tools,
    remember_tool_support,
    stream_chat,
    supports_native_tools,
)
from . import tools as _tools  # noqa: F401  (registers every tool)
from .blocks import blocks_for
from .context import profile_sentence, roll_profile
from .guards import (
    bind_citations,
    collect_citations,
    permitted_numbers,
    strip_unverified_numbers,
)
from .registry import REGISTRY, ToolError, describe_tools, execute, label_for, openai_tools

logger = logging.getLogger(__name__)

MAX_ROUNDS = 4
MAX_TOOL_CALLS = 6
DEADLINE_SECONDS = 20.0

#: How many turns of prior conversation are replayed verbatim.
#:
#: The spec called for older turns to collapse into a running summary. This
#: truncates instead, deliberately: summarising costs an extra model call on
#: every turn, and the goal — bounding prompt growth so the timeouts fixed in
#: commits 9e250eb and 1784600 do not return — is met by truncation alone. The
#: cost is that a conversation longer than twelve turns forgets its opening.
#: Revisit if that turns out to matter in use.
HISTORY_TURNS = 12

_SYSTEM = """You are the analyst embedded in a Tamil Nadu electoral roll OCR workspace.

{profile}

You answer by calling tools. You do not know any figure you have not been given
by a tool, and you must not estimate, round or infer one — a figure you type is
discarded before the operator sees it, taking the sentence with it.

Rules:
- Call a tool whenever the question is about the data. Prefer a specific tool
  over run_readonly_sql; use SQL only when nothing else fits.
- Reply in the language the user wrote in (English or Tamil).
- Reference an elector as [[v:<voter id>]], using an id a tool returned. Never
  invent one; invented references are removed.
- Do not describe tables or charts you were shown — they are rendered beside
  your answer. Say what they mean.
- Be concise and concrete. If a tool failed, say what you could not find out.
- Prose only. No JSON, no markdown code fences.
"""

_PLANNER = """You have no function-calling support, so you act one step at a time.

Available tools:
{catalogue}

Reply with JSON only, and nothing else. Either ask for data:
  {{"tool": "<tool name>", "args": {{...}}}}
or answer, once you have what you need:
  {{"answer": "<your reply>"}}
"""


@dataclass(frozen=True)
class AgentEvent:
    """One thing worth telling the client about."""

    type: str
    data: Dict[str, Any] = field(default_factory=dict)


def _sentences(buffer: str) -> tuple[List[str], str]:
    """Split off the complete sentences, keeping the unfinished tail."""
    out: List[str] = []
    start = 0
    for i, ch in enumerate(buffer):
        if ch in ".!?\n":
            piece = buffer[start : i + 1].strip()
            if piece:
                out.append(piece)
            start = i + 1
    return out, buffer[start:]


def _history_messages(history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    if not history:
        return []
    return [
        {"role": h.get("role") or "user", "content": str(h.get("content") or "")}
        for h in history[-HISTORY_TURNS:]
        if (h.get("content") or "").strip()
    ]


def _planner_step(messages: List[Dict[str, Any]], creds: AiCredentials) -> ToolCallOutcome:
    """One planner turn, translated into the same shape as a native tool call."""
    outcome = chat_with_tools(messages, creds, [], temperature=0.1, max_tokens=700)
    if outcome.error:
        return outcome

    text = (outcome.content or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        # Not JSON: treat it as the answer, which is what a small model that has
        # given up on the format is trying to give us anyway.
        return ToolCallOutcome(content=text)

    if isinstance(parsed, dict) and parsed.get("tool"):
        return ToolCallOutcome(
            tool_calls=[
                {
                    "id": "planner",
                    "name": str(parsed["tool"]),
                    "arguments": parsed.get("args") if isinstance(parsed.get("args"), dict) else {},
                }
            ]
        )
    if isinstance(parsed, dict) and parsed.get("answer"):
        return ToolCallOutcome(content=str(parsed["answer"]))
    return ToolCallOutcome(content=text)


def run_agent(
    session: Session,
    message: str,
    *,
    creds: AiCredentials,
    history: Optional[List[Dict[str, str]]] = None,
    app_context: Optional[Dict[str, Any]] = None,
) -> Iterator[AgentEvent]:
    """Answer one data question, streaming what happens as it happens."""
    if not creds.configured:
        yield AgentEvent(
            "error",
            {"message": "No API key is configured. Add one under Settings."},
        )
        return

    deadline = time.monotonic() + DEADLINE_SECONDS
    native = supports_native_tools(creds.model)

    try:
        profile = profile_sentence(roll_profile(session))
    except Exception:
        logger.exception("Could not build the roll profile")
        profile = ""

    system = _SYSTEM.format(profile=profile)
    if native is False:
        system = system + "\n\n" + _PLANNER.format(catalogue=describe_tools())

    user_content = (message or "").strip()
    if app_context:
        user_content += f"\n\n[The operator is looking at: {json.dumps(app_context, default=str)}]"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        *_history_messages(history),
        {"role": "user", "content": user_content},
    ]

    tool_results: List[Dict[str, Any]] = []
    made_blocks: List[Dict[str, Any]] = []
    trace: List[Dict[str, Any]] = []
    calls_made = 0
    budget_hit = False

    for _round in range(MAX_ROUNDS):
        if time.monotonic() > deadline:
            budget_hit = True
            break

        yield AgentEvent("status", {"message": "Thinking"})

        if native is False:
            outcome = _planner_step(messages, creds)
        else:
            outcome = chat_with_tools(
                messages, creds, openai_tools(), temperature=0.2, max_tokens=700
            )
            if outcome.unsupported:
                remember_tool_support(creds.model, False)
                native = False
                messages[0] = {
                    "role": "system",
                    "content": system + "\n\n" + _PLANNER.format(catalogue=describe_tools()),
                }
                outcome = _planner_step(messages, creds)
            elif native is None and not outcome.error:
                remember_tool_support(creds.model, True)
                native = True

        if outcome.error:
            yield AgentEvent("error", {"message": outcome.error})
            return

        if not outcome.tool_calls:
            break

        for call in outcome.tool_calls:
            if calls_made >= MAX_TOOL_CALLS or time.monotonic() > deadline:
                budget_hit = True
                break
            calls_made += 1

            name = call.get("name") or ""
            args = call.get("arguments") or {}
            yield AgentEvent(
                "tool_call",
                {"id": call.get("id"), "name": name, "label": label_for(name), "args": args},
            )

            try:
                result = execute(session, name, args)
            except ToolError as exc:
                trace.append({"tool": name, "args": args, "ok": False, "error": str(exc)})
                yield AgentEvent(
                    "tool_result",
                    {"id": call.get("id"), "name": name, "ok": False, "error": str(exc)},
                )
                messages.append(
                    {"role": "user", "content": f"Tool {name} failed: {exc}"}
                    if native is False
                    else {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": f"ERROR: {exc}",
                    }
                )
                continue

            tool_results.append(result)
            made_blocks.extend(blocks_for(name, result))
            summary = {
                "tool": name,
                "args": args,
                "ok": True,
                "returned": result.get("returned", result.get("total")),
            }
            trace.append(summary)
            yield AgentEvent(
                "tool_result",
                {"id": call.get("id"), "name": name, "ok": True, "summary": summary},
            )

            payload = json.dumps(result, default=str)[:6000]
            messages.append(
                {"role": "user", "content": f"Result of {name}: {payload}"}
                if native is False
                else {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": payload,
                }
            )

        if budget_hit:
            break

    # --- write the answer ---------------------------------------------------
    yield AgentEvent("status", {"message": "Writing"})

    allowed = permitted_numbers(tool_results)
    known = collect_citations(tool_results)

    messages.append(
        {
            "role": "user",
            "content": (
                "Now answer the question in prose, using only the figures above. "
                + ("Say that you ran out of steps before finishing. " if budget_hit else "")
            ),
        }
    )

    verified: List[str] = []
    buffer = ""
    dropped_total = 0
    for delta in stream_chat(messages, creds, temperature=0.4, max_tokens=600):
        buffer += delta
        complete, buffer = _sentences(buffer)
        for sentence in complete:
            kept, dropped = strip_unverified_numbers(sentence, allowed)
            dropped_total += dropped
            if not kept:
                continue
            bound, _ = bind_citations(kept, known)
            if bound:
                verified.append(bound)
                yield AgentEvent("token", {"text": bound + " "})

    tail = buffer.strip()
    if tail:
        kept, dropped = strip_unverified_numbers(tail, allowed)
        dropped_total += dropped
        if kept:
            bound, _ = bind_citations(kept, known)
            if bound:
                verified.append(bound)
                yield AgentEvent("token", {"text": bound})

    content = " ".join(verified).strip()
    _, cited = bind_citations(content, known)

    if made_blocks:
        yield AgentEvent("blocks", {"blocks": made_blocks})
    if cited:
        yield AgentEvent("citations", {"citations": cited})

    if not content:
        content = (
            "I could not produce an answer I can stand behind. "
            "The figures I was given did not support one."
        )

    yield AgentEvent(
        "done",
        {
            "content": content,
            "blocks": made_blocks,
            "citations": cited,
            "tool_trace": trace,
            "dropped_sentences": dropped_total,
            "budget_exhausted": budget_hit,
        },
    )
```

- [ ] **Step 4: Re-export from the package**

Append to `apps/api/app/services/ai_agent/__init__.py`:

```python
from .loop import AgentEvent, run_agent  # noqa: F401,E402
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_loop.py -v
```

Expected: 9 passed. If `test_an_invented_figure_never_reaches_the_client` fails, the guard is being applied after the event is yielded rather than before — the order in the streaming block matters.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ai_agent/loop.py apps/api/app/services/ai_agent/__init__.py apps/api/tests/test_ai_loop.py
git commit -m "feat(ai): add the bounded agent loop with dual transports"
```

---

### Task 12: Chat API endpoints

**Files:**
- Create: `apps/api/app/routers/ai_chat.py`
- Modify: `apps/api/app/main.py` (register the router)
- Test: `apps/api/tests/test_ai_chat_api.py`

**Interfaces:**
- Consumes: `require_user`, `get_session`, `ChatThreadRow`, `ChatMessageRow`, `app_settings.resolve_ai_credentials`, `router.classify`, `loop.run_agent`, `nvidia_ai_service.query_nvidia_copilot`.
- Produces: `POST /api/ai/chat`, `GET /api/ai/threads`, `GET /api/ai/threads/{id}`, `DELETE /api/ai/threads/{id}`.

**SSE frame contract.** Every frame is `event: <type>` plus `data: <json>`. Types are exactly the `AgentEvent` types: `status`, `tool_call`, `tool_result`, `token`, `blocks`, `citations`, `done`, `error`. The client treats `done` and `error` as terminal.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/test_ai_chat_api.py`:

```python
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

from app.auth import require_user  # noqa: E402
from app.db import ChatThreadRow, UserRow, session_scope  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client_as():
    """A client authenticated as an arbitrary user id."""

    def _make(user_id: str):
        app.dependency_overrides[require_user] = lambda: UserRow(
            id=user_id, username=user_id, password_hash="x", display_name=user_id
        )
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture()
def owned_thread():
    tid = uuid.uuid4().hex[:32]
    with session_scope() as s:
        s.add(ChatThreadRow(id=tid, user_id="owner", title="Mine"))
    yield tid
    with session_scope() as s:
        row = s.get(ChatThreadRow, tid)
        if row is not None:
            s.delete(row)


def test_threads_list_only_the_callers_own(client_as, owned_thread):
    mine = client_as("owner").get("/api/ai/threads").json()
    assert any(t["id"] == owned_thread for t in mine["threads"])

    theirs = client_as("someone-else").get("/api/ai/threads").json()
    assert all(t["id"] != owned_thread for t in theirs["threads"])


def test_another_users_thread_is_not_readable(client_as, owned_thread):
    response = client_as("someone-else").get(f"/api/ai/threads/{owned_thread}")
    assert response.status_code == 404


def test_another_users_thread_cannot_be_deleted(client_as, owned_thread):
    assert client_as("someone-else").delete(f"/api/ai/threads/{owned_thread}").status_code == 404
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
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_chat_api.py -v
```

Expected: 404s — the routes do not exist.

- [ ] **Step 3: Write the router**

Create `apps/api/app/routers/ai_chat.py`:

```python
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
from starlette.concurrency import iterate_in_threadpool

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
    and does not enter the loop.
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

    intent = classify(message, creds)

    def produce() -> Iterator[Dict[str, str]]:
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

        final: Optional[AgentEvent] = None
        try:
            for event in events:
                if event.type in ("done", "error"):
                    final = event
                yield {"event": event.type, "data": json.dumps(event.data, default=str)}
        except Exception:
            logger.exception("The assistant failed mid-turn")
            yield {
                "event": "error",
                "data": json.dumps({"message": "The assistant failed while answering."}),
            }
            return

        if final is not None and final.type == "done":
            session.add(
                ChatMessageRow(
                    id=_new_id(),
                    thread_id=thread_id,
                    role="assistant",
                    content=final.data.get("content", ""),
                    blocks=final.data.get("blocks") or [],
                    citations=final.data.get("citations") or [],
                    tool_trace=final.data.get("tool_trace") or [],
                )
            )
            session.commit()

    return EventSourceResponse(iterate_in_threadpool(produce()))
```

- [ ] **Step 4: Register the router**

In `apps/api/app/main.py`, add `ai_chat` to the existing router import, then register it beside the others:

```python
app.include_router(ai_chat.router, prefix="/api/ai", tags=["ai"], dependencies=PROTECTED)
```

- [ ] **Step 5: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_ai_chat_api.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Verify the whole backend suite still passes**

```bash
npm run test:backend
```

Expected: every pre-existing test green alongside the new ones.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/routers/ai_chat.py apps/api/app/main.py apps/api/tests/test_ai_chat_api.py
git commit -m "feat(ai): add streaming chat endpoints with per-user threads"
```

---

### Task 13: Shared types, streaming client and the chat hook

**Files:**
- Modify: `packages/shared-types/src/index.ts` (append after `AiCopilotResponse`, around line 741)
- Create: `apps/web/src/lib/aiChatApi.ts`, `apps/web/src/hooks/useAiChat.ts`
- Verify: `cd apps/web && npm run typecheck`

**Interfaces:**
- Produces (shared types): `ChatBlock`, `ChatTableBlock`, `ChatVoterCardBlock`, `ChatChartBlock`, `ChatSqlBlock`, `ChatCitation`, `ChatToolStep`, `ChatMessage`, `ChatThreadSummary`, `ChatThread`, `AgentStreamEvent`.
- Produces (client): `streamChat(body, handlers) => () => void` (returns an abort function), `listThreads()`, `getThread(id)`, `deleteThread(id)`.
- Produces (hook): `useAiChat()` returning `{ messages, send, stop, loading, status, steps, threadId, newThread, loadThread, threads, refreshThreads, deleteThread }`.

- [ ] **Step 1: Add the shared types**

Append to `packages/shared-types/src/index.ts`, immediately after `AiCopilotResponse`:

```typescript
// ---------------------------------------------------------------------------
// The agentic assistant
//
// Blocks are built by the server from tool results, never by the model. That is
// deliberate: asking a language model to emit a table is asking it to retype
// data it was just given, and a retyped table is a table with a typo in it.
// ---------------------------------------------------------------------------

export interface ChatTableBlock {
  kind: "table";
  columns: string[];
  rows: Record<string, unknown>[];
  total?: number | null;
  truncated?: boolean;
}

export interface ChatVoterCardBlock {
  kind: "voter_card";
  voter: Record<string, unknown>;
  provenance: Record<string, unknown>;
  ocr_fields: {
    field_name: string;
    raw_text: string;
    corrected_text: string;
    confidence: number;
    bbox: number[];
  }[];
}

export interface ChatChartBlock {
  kind: "chart";
  infographic: Infographic;
}

export interface ChatSqlBlock {
  kind: "sql";
  sql: string;
  rationale: string;
  returned: number;
}

export type ChatBlock =
  | ChatTableBlock
  | ChatVoterCardBlock
  | ChatChartBlock
  | ChatSqlBlock;

/** An elector a tool actually returned. Anything else was stripped server-side. */
export interface ChatCitation {
  id: string;
  epic: string | null;
  name: string | null;
  part_number: string | null;
}

export interface ChatToolStep {
  tool: string;
  args?: Record<string, unknown>;
  ok: boolean;
  returned?: number | null;
  error?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  blocks: ChatBlock[];
  citations: ChatCitation[];
  tool_trace: ChatToolStep[];
  created_at?: string | null;
  /** Set locally while the reply is still streaming. */
  pending?: boolean;
  /** Set when the turn ended in an error rather than an answer. */
  failed?: boolean;
}

export interface ChatThreadSummary {
  id: string;
  title: string;
  updated_at: string | null;
}

export interface ChatThread extends ChatThreadSummary {
  messages: ChatMessage[];
}

export type AgentStreamEvent =
  | { type: "status"; data: { message?: string; thread_id?: string; intent?: string } }
  | { type: "tool_call"; data: { id: string; name: string; label: string; args: Record<string, unknown> } }
  | { type: "tool_result"; data: { id: string; name: string; ok: boolean; error?: string; summary?: ChatToolStep } }
  | { type: "token"; data: { text: string } }
  | { type: "blocks"; data: { blocks: ChatBlock[] } }
  | { type: "citations"; data: { citations: ChatCitation[] } }
  | { type: "done"; data: { content: string; blocks: ChatBlock[]; citations: ChatCitation[]; tool_trace: ChatToolStep[]; budget_exhausted?: boolean } }
  | { type: "error"; data: { message: string } };
```

- [ ] **Step 2: Write the streaming client**

Create `apps/web/src/lib/aiChatApi.ts`:

```typescript
/**
 * Client for the assistant's streaming endpoint.
 *
 * `EventSource` cannot be used: it is GET-only, and a turn carries the message,
 * the thread and the current view context. So the response body is read as a
 * stream and the SSE frames are parsed here.
 */

import type {
  AgentStreamEvent,
  ChatThread,
  ChatThreadSummary,
} from "@ocr/shared-types";

export interface StreamHandlers {
  onEvent: (event: AgentStreamEvent) => void;
  onClose?: () => void;
  onError?: (message: string) => void;
}

export interface StreamBody {
  message: string;
  thread_id?: string | null;
  context?: Record<string, unknown>;
}

/** Split an SSE buffer into complete frames, keeping the unfinished tail. */
function parseFrames(buffer: string): { events: AgentStreamEvent[]; rest: string } {
  const events: AgentStreamEvent[] = [];
  const chunks = buffer.split("\n\n");
  const rest = chunks.pop() ?? "";

  for (const chunk of chunks) {
    let type = "";
    let payload = "";
    for (const line of chunk.split("\n")) {
      if (line.startsWith("event:")) type = line.slice(6).trim();
      else if (line.startsWith("data:")) payload += line.slice(5).trim();
    }
    if (!type || !payload) continue;
    try {
      events.push({ type, data: JSON.parse(payload) } as AgentStreamEvent);
    } catch {
      // A frame we cannot parse is dropped rather than crashing the stream —
      // losing one status line is better than losing the answer.
    }
  }
  return { events, rest };
}

/** Start a turn. Returns a function that aborts it. */
export function streamChat(body: StreamBody, handlers: StreamHandlers): () => void {
  const controller = new AbortController();

  void (async () => {
    try {
      const response = await fetch("/api/ai/chat", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        handlers.onError?.(
          response.status === 401
            ? "Your session has expired. Sign in again."
            : `The assistant could not be reached (HTTP ${response.status}).`,
        );
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseFrames(buffer);
        buffer = rest;
        for (const event of events) handlers.onEvent(event);
      }
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        handlers.onError?.("The connection to the assistant was lost.");
      }
    } finally {
      handlers.onClose?.();
    }
  })();

  return () => controller.abort();
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export function listThreads(): Promise<{ threads: ChatThreadSummary[] }> {
  return json("/api/ai/threads");
}

export function getThread(id: string): Promise<ChatThread> {
  return json(`/api/ai/threads/${id}`);
}

export function deleteThread(id: string): Promise<void> {
  return json(`/api/ai/threads/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 3: Write the hook**

Create `apps/web/src/hooks/useAiChat.ts`:

```typescript
"use client";

/**
 * Conversation state for the assistant.
 *
 * The component renders; this decides what a stream of events means. Keeping
 * that split means the panel and any future full-page view show the same
 * conversation without either owning the protocol.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatBlock,
  ChatCitation,
  ChatMessage,
  ChatThreadSummary,
  ChatToolStep,
} from "@ocr/shared-types";
import {
  deleteThread as apiDeleteThread,
  getThread,
  listThreads,
  streamChat,
} from "@/lib/aiChatApi";

let counter = 0;
const nextId = () => `local-${++counter}`;

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Ask me about the electoral roll, the OCR pipeline or this workspace. " +
    "I read the database directly — figures come from SQL, and I show you which " +
    "steps I ran.",
  blocks: [],
  citations: [],
  tool_trace: [],
};

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [steps, setSteps] = useState<ChatToolStep[]>([]);

  const abortRef = useRef<(() => void) | null>(null);

  const refreshThreads = useCallback(async () => {
    try {
      setThreads((await listThreads()).threads);
    } catch {
      // A missing thread list is not worth interrupting the conversation over.
    }
  }, []);

  useEffect(() => {
    return () => abortRef.current?.();
  }, []);

  const newThread = useCallback(() => {
    abortRef.current?.();
    setThreadId(null);
    setSteps([]);
    setMessages([WELCOME]);
  }, []);

  const loadThread = useCallback(async (id: string) => {
    abortRef.current?.();
    const thread = await getThread(id);
    setThreadId(thread.id);
    setSteps([]);
    setMessages(thread.messages.length ? thread.messages : [WELCOME]);
  }, []);

  const removeThread = useCallback(
    async (id: string) => {
      await apiDeleteThread(id);
      if (id === threadId) newThread();
      void refreshThreads();
    },
    [threadId, newThread, refreshThreads],
  );

  const stop = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setLoading(false);
    setStatus("");
  }, []);

  const send = useCallback(
    (text: string, context?: Record<string, unknown>) => {
      const question = text.trim();
      if (!question || loading) return;

      const replyId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: question, blocks: [], citations: [], tool_trace: [] },
        { id: replyId, role: "assistant", content: "", blocks: [], citations: [], tool_trace: [], pending: true },
      ]);
      setSteps([]);
      setLoading(true);
      setStatus("Thinking");

      const patch = (change: Partial<ChatMessage>) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === replyId ? { ...m, ...change } : m)),
        );

      abortRef.current = streamChat(
        { message: question, thread_id: threadId, context },
        {
          onEvent: (event) => {
            switch (event.type) {
              case "status":
                if (event.data.thread_id) setThreadId(event.data.thread_id);
                if (event.data.message) setStatus(event.data.message);
                break;
              case "tool_call":
                setStatus(event.data.label);
                break;
              case "tool_result":
                setSteps((prev) => [
                  ...prev,
                  event.data.summary ?? {
                    tool: event.data.name,
                    ok: event.data.ok,
                    error: event.data.error,
                  },
                ]);
                break;
              case "token":
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === replyId ? { ...m, content: m.content + event.data.text } : m,
                  ),
                );
                break;
              case "blocks":
                patch({ blocks: event.data.blocks as ChatBlock[] });
                break;
              case "citations":
                patch({ citations: event.data.citations as ChatCitation[] });
                break;
              case "done":
                patch({
                  content: event.data.content,
                  blocks: event.data.blocks,
                  citations: event.data.citations,
                  tool_trace: event.data.tool_trace,
                  pending: false,
                });
                void refreshThreads();
                break;
              case "error":
                patch({ content: event.data.message, pending: false, failed: true });
                break;
            }
          },
          onError: (message) => patch({ content: message, pending: false, failed: true }),
          onClose: () => {
            setLoading(false);
            setStatus("");
            abortRef.current = null;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === replyId && m.pending
                  ? {
                      ...m,
                      pending: false,
                      failed: !m.content,
                      content: m.content || "The answer was interrupted.",
                    }
                  : m,
              ),
            );
          },
        },
      );
    },
    [loading, threadId, refreshThreads],
  );

  return {
    messages,
    threads,
    threadId,
    loading,
    status,
    steps,
    send,
    stop,
    newThread,
    loadThread,
    deleteThread: removeThread,
    refreshThreads,
  };
}
```

- [ ] **Step 4: Typecheck**

```bash
cd apps/web && npm run typecheck
```

Expected: no errors. If `@ocr/shared-types` does not resolve the new names, the package needs rebuilding — check how `apps/web` consumes it and follow the same path the existing `Infographic` type takes.

- [ ] **Step 5: Commit**

```bash
git add packages/shared-types/src/index.ts apps/web/src/lib/aiChatApi.ts apps/web/src/hooks/useAiChat.ts
git commit -m "feat(web): add assistant streaming client, types and chat hook"
```

---

### Task 14: Render blocks and citation chips

**Files:**
- Create: `apps/web/src/components/ai/VoterChip.tsx`, `apps/web/src/components/ai/ToolTrace.tsx`, `apps/web/src/components/ai/MessageBlocks.tsx`
- Verify: `cd apps/web && npm run typecheck && npm run lint`

**Interfaces:**
- Consumes: `ChatBlock`, `ChatCitation`, `ChatToolStep` from `@ocr/shared-types`; `useOcrStore` (`setActiveTab`, `setSelectedRecordId`, `setActiveFileId`, `setActivePageId`); `InfographicCard`.
- Produces:
  - `<VoterChip citation={ChatCitation} />`
  - `<ToolTrace steps={ChatToolStep[]} />`
  - `<MessageBlocks blocks={ChatBlock[]} />`
  - `<AnswerText text={string} citations={ChatCitation[]} />` — renders `[[v:id]]` markers as chips.

- [ ] **Step 1: Write the citation chip**

Create `apps/web/src/components/ai/VoterChip.tsx`:

```typescript
"use client";

/**
 * A citation the operator can act on.
 *
 * Clicking opens the elector in the main workspace. The assistant does not
 * navigate on its own — it hands over a link, and the operator decides whether
 * to follow it. That boundary was drawn deliberately when UI-driving was removed
 * from the earlier assistant, and this keeps it.
 */

import React from "react";
import { ExternalLink } from "lucide-react";
import type { ChatCitation } from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";

export const VoterChip: React.FC<{ citation: ChatCitation }> = ({ citation }) => {
  const setActiveTab = useOcrStore((s) => s.setActiveTab);
  const setSelectedRecordId = useOcrStore((s) => s.setSelectedRecordId);

  const label = citation.name || citation.epic || citation.id;

  return (
    <button
      type="button"
      onClick={() => {
        setSelectedRecordId(citation.id);
        setActiveTab("voters");
      }}
      title={
        citation.epic
          ? `Open ${label} (${citation.epic})`
          : `Open ${label}`
      }
      className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded-md bg-indigo-500/15 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 font-semibold transition-colors align-baseline"
    >
      {label}
      <ExternalLink className="w-3 h-3 shrink-0" />
    </button>
  );
};
```

- [ ] **Step 2: Write the tool trace**

Create `apps/web/src/components/ai/ToolTrace.tsx`:

```typescript
"use client";

/**
 * What the assistant actually did.
 *
 * Collapsed by default — most of the time the answer is the point. Expanded, it
 * shows every step, because an answer whose workings cannot be inspected is an
 * answer that has to be taken on trust.
 */

import React, { useState } from "react";
import { CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import type { ChatToolStep } from "@ocr/shared-types";

export const ToolTrace: React.FC<{ steps: ChatToolStep[] }> = ({ steps }) => {
  const [open, setOpen] = useState(false);
  if (!steps.length) return null;

  return (
    <div className="mt-2 text-[10px]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-slate-400 hover:text-slate-200 font-bold uppercase tracking-wide transition-colors"
      >
        <ChevronRight className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`} />
        Ran {steps.length} step{steps.length === 1 ? "" : "s"}
      </button>

      {open && (
        <ul className="mt-1.5 space-y-1 border-l border-slate-700 pl-2.5">
          {steps.map((step, i) => (
            <li key={`${step.tool}-${i}`} className="flex items-start gap-1.5 font-mono text-slate-400">
              {step.ok ? (
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-3 h-3 text-rose-400 shrink-0 mt-0.5" />
              )}
              <span className="break-all">
                <span className="text-slate-300">{step.tool}</span>
                {step.args && Object.keys(step.args).length > 0 && (
                  <span>
                    (
                    {Object.entries(step.args)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join(", ")}
                    )
                  </span>
                )}
                {step.ok
                  ? step.returned != null && <span className="text-slate-500"> → {step.returned} rows</span>
                  : <span className="text-rose-400"> → {step.error}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
```

- [ ] **Step 3: Write the block renderer**

Create `apps/web/src/components/ai/MessageBlocks.tsx`:

```typescript
"use client";

/**
 * How a tool result looks.
 *
 * Every block here was built by the server from data a tool returned. Nothing
 * on this screen was typed by the language model except the prose beside it.
 */

import React from "react";
import { Database } from "lucide-react";
import type { ChatBlock, ChatCitation } from "@ocr/shared-types";
import { InfographicCard } from "../InfographicCard";
import { VoterChip } from "./VoterChip";

const MARKER = /\[\[v:([A-Za-z0-9_-]{1,40})\]\]/g;

/** Prose with its citation markers turned into chips. */
export const AnswerText: React.FC<{ text: string; citations: ChatCitation[] }> = ({
  text,
  citations,
}) => {
  const byId = new Map(citations.map((c) => [c.id, c]));
  const parts: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;

  MARKER.lastIndex = 0;
  while ((match = MARKER.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const citation = byId.get(match[1]);
    parts.push(
      citation ? (
        <VoterChip key={`${match[1]}-${match.index}`} citation={citation} />
      ) : (
        ""
      ),
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));

  return <p className="whitespace-pre-wrap">{parts}</p>;
};

const cell = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
};

const Table: React.FC<{
  columns: string[];
  rows: Record<string, unknown>[];
  total?: number | null;
  truncated?: boolean;
}> = ({ columns, rows, total, truncated }) => (
  <div className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/40 overflow-hidden">
    <div className="overflow-x-auto">
      <table className="w-full text-[10px] border-collapse">
        <thead>
          <tr className="bg-slate-800/60 text-slate-300">
            {columns.map((c) => (
              <th key={c} className="text-left font-bold uppercase tracking-wide px-2 py-1.5 whitespace-nowrap">
                {c.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-slate-800/70 text-slate-200">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1.5 whitespace-nowrap">{cell(row[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {(truncated || total != null) && (
      <p className="px-2 py-1 text-[9px] text-slate-500 border-t border-slate-800">
        Showing {rows.length}
        {total != null ? ` of ${total}` : ""}
        {truncated ? " — narrow the question to see the rest" : ""}
      </p>
    )}
  </div>
);

export const MessageBlocks: React.FC<{ blocks: ChatBlock[] }> = ({ blocks }) => {
  if (!blocks?.length) return null;

  return (
    <div className="space-y-2">
      {blocks.map((block, i) => {
        if (block.kind === "chart") {
          return <InfographicCard key={i} data={block.infographic} />;
        }

        if (block.kind === "table") {
          return (
            <Table
              key={i}
              columns={block.columns}
              rows={block.rows}
              total={block.total}
              truncated={block.truncated}
            />
          );
        }

        if (block.kind === "sql") {
          return (
            <div key={i} className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/60 p-2.5">
              <p className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wide text-slate-400">
                <Database className="w-3 h-3" />
                Query run — {block.rationale}
              </p>
              <pre className="mt-1.5 text-[10px] text-emerald-300 font-mono whitespace-pre-wrap break-all">
                {block.sql}
              </pre>
            </div>
          );
        }

        const voter = block.voter as Record<string, unknown>;
        const provenance = block.provenance as Record<string, unknown>;
        return (
          <div key={i} className="mt-2 rounded-xl border border-slate-700/60 bg-slate-950/40 p-3">
            <p className="text-xs font-bold text-white">{cell(voter.name)}</p>
            <p className="text-[10px] text-slate-400 font-mono">{cell(voter.epic)}</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
              {["age", "gender", "relation_name", "house_number", "part_number", "verified"].map((key) => (
                <div key={key} className="flex justify-between gap-2 border-b border-slate-800/60 pb-0.5">
                  <dt className="text-slate-500">{key.replace(/_/g, " ")}</dt>
                  <dd className="text-slate-200 font-medium text-right">{cell(voter[key])}</dd>
                </div>
              ))}
            </dl>
            {block.ocr_fields.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-[10px]">
                {block.ocr_fields.map((f) => (
                  <li key={f.field_name} className="flex justify-between gap-2">
                    <span className="text-slate-500">{f.field_name}</span>
                    <span className={f.confidence < 0.75 ? "text-amber-400 font-bold" : "text-slate-400"}>
                      {Math.round(f.confidence * 100)}%
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {provenance.source_file_name != null && (
              <p className="mt-2 text-[9px] text-slate-500">
                From {cell(provenance.source_file_name)}, page {cell(provenance.page_number)}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
};
```

- [ ] **Step 4: Typecheck and lint**

```bash
cd apps/web && npm run typecheck && npm run lint
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/ai
git commit -m "feat(web): render assistant tables, cards, SQL and citation chips"
```

---

### Task 15: Wire the panel together

**Files:**
- Create: `apps/web/src/components/ai/ThreadMenu.tsx`
- Modify: `apps/web/src/components/FloatingAiChatbot.tsx` (rewrite the body; keep the launcher button and the `vi-mc:open-ai-assistant` listener)
- Verify: `cd apps/web && npm run typecheck && npm run lint && npm run build`, then the preview workflow.

**Interfaces:**
- Consumes: `useAiChat`, `MessageBlocks`, `AnswerText`, `ToolTrace`, `getAiSettings`, `useOcrStore`.

- [ ] **Step 1: Write the thread menu**

Create `apps/web/src/components/ai/ThreadMenu.tsx`:

```typescript
"use client";

/** Past conversations. Opening one replays exactly what was shown at the time. */

import React, { useEffect, useState } from "react";
import { History, Plus, Trash2 } from "lucide-react";
import type { ChatThreadSummary } from "@ocr/shared-types";

interface Props {
  threads: ChatThreadSummary[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

export const ThreadMenu: React.FC<Props> = ({
  threads, activeId, onNew, onOpen, onDelete, onRefresh,
}) => {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (open) onRefresh();
  }, [open, onRefresh]);

  return (
    <div className="relative">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onNew}
          aria-label="Start a new conversation"
          className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label="Past conversations"
          className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
        >
          <History className="w-4 h-4" />
        </button>
      </div>

      {open && (
        <div className="absolute right-0 top-10 z-10 w-64 max-h-72 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl p-1">
          {threads.length === 0 ? (
            <p className="p-3 text-[11px] text-slate-500">No past conversations.</p>
          ) : (
            threads.map((t) => (
              <div
                key={t.id}
                className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] ${
                  t.id === activeId ? "bg-indigo-500/20 text-indigo-200" : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <button
                  type="button"
                  onClick={() => { onOpen(t.id); setOpen(false); }}
                  className="flex-1 text-left truncate"
                  title={t.title}
                >
                  {t.title || "Untitled"}
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(t.id)}
                  aria-label={`Delete ${t.title}`}
                  className="text-slate-500 hover:text-rose-400 transition-colors shrink-0"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Rewrite the panel**

Replace `apps/web/src/components/FloatingAiChatbot.tsx` with:

```typescript
"use client";

/**
 * The assistant.
 *
 * It reads the database and answers; it does not touch the interface. An earlier
 * version applied themes, filters and exports on the model's instruction. That
 * is still gone — the closest this comes is a citation chip, which the operator
 * clicks to open a record. The assistant offers; the operator decides.
 *
 * Every figure shown here came from SQL, and every elector named was returned by
 * a tool. Both are enforced server-side in `services/ai_agent/guards.py`, not
 * requested in a prompt.
 */

import React, { useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, Send, Sparkles, Square, User } from "lucide-react";
import { getAiSettings } from "@/lib/voterApi";
import { useAiChat } from "@/hooks/useAiChat";
import { useOcrStore } from "@/store/useOcrStore";
import { AnswerText, MessageBlocks } from "./ai/MessageBlocks";
import { ThreadMenu } from "./ai/ThreadMenu";
import { ToolTrace } from "./ai/ToolTrace";

/** Questions that show the assistant now reads the database, not just charts it. */
const SUGGESTIONS = [
  "Voters by gender",
  "Which pages failed OCR?",
  "Find electors named Muthu",
  "Records with low confidence",
  "Does part 289's count match the roll?",
];

export const FloatingAiChatbot: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);

  const {
    messages, threads, threadId, loading, status, steps,
    send, stop, newThread, loadThread, deleteThread, refreshThreads,
  } = useAiChat();

  const { activeTab, activeFileId, activePageId, selectedRecordId, files } = useOcrStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isOpen, loading, status]);

  useEffect(() => {
    if (isOpen && aiConfigured === null) {
      getAiSettings()
        .then((res) => setAiConfigured(res.configured))
        .catch(() => setAiConfigured(false));
    }
  }, [isOpen, aiConfigured]);

  useEffect(() => {
    const handler = () => setIsOpen(true);
    window.addEventListener("vi-mc:open-ai-assistant", handler);
    return () => window.removeEventListener("vi-mc:open-ai-assistant", handler);
  }, []);

  const submit = (text?: string) => {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    if (!text) setInput("");

    send(question, {
      activeTab,
      ...(activeFileId
        ? { activeFileId, activeFileName: files.find((f) => f.id === activeFileId)?.name }
        : {}),
      ...(activePageId ? { activePageId } : {}),
      ...(selectedRecordId ? { selectedRecordId } : {}),
    });
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {isOpen && (
        // `dark` is forced: the panel is dark by design, so charts inside it use
        // the dark palette even when the rest of the app is light.
        <div className="dark w-[380px] sm:w-[520px] h-[600px] mb-4 bg-slate-900 text-slate-100 border border-indigo-500/50 shadow-2xl rounded-3xl flex flex-col overflow-hidden">
          <div className="p-4 bg-gradient-to-r from-indigo-900/90 via-purple-900/90 to-slate-900 border-b border-slate-800 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-rose-500 grid place-items-center text-white shadow-md shrink-0">
                <Bot className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <h4 className="text-sm font-extrabold text-white flex items-center gap-2">
                  <span>AI Analyst</span>
                  {aiConfigured === false ? (
                    <span
                      title="No API key is set. Add one under Settings for full answers."
                      className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-amber-500/20 text-amber-400 border border-amber-500/40"
                    >
                      Offline
                    </span>
                  ) : aiConfigured ? (
                    <span className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                      Ready
                    </span>
                  ) : null}
                </h4>
                <p className="text-[11px] text-slate-400 truncate">Reads the roll database directly</p>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              <ThreadMenu
                threads={threads}
                activeId={threadId}
                onNew={newThread}
                onOpen={(id) => void loadThread(id)}
                onDelete={(id) => void deleteThread(id)}
                onRefresh={() => void refreshThreads()}
              />
              <button
                onClick={() => setIsOpen(false)}
                aria-label="Close the assistant"
                className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
              >
                <ChevronDown className="w-5 h-5" />
              </button>
            </div>
          </div>

          <div className="px-3 py-2 bg-slate-950/60 border-b border-slate-800 flex gap-1.5 overflow-x-auto text-[11px] font-bold shrink-0">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                disabled={loading}
                className="px-2.5 py-1 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 disabled:opacity-40 text-indigo-300 border border-indigo-500/30 whitespace-nowrap transition-colors"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="flex-1 p-4 overflow-y-auto space-y-3 text-xs">
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-2">
                <div className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="w-7 h-7 rounded-xl bg-indigo-600 text-white grid place-items-center shrink-0 mt-0.5 shadow-sm">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>
                  )}

                  <div
                    className={`max-w-[86%] p-3.5 rounded-2xl leading-relaxed ${
                      msg.role === "user"
                        ? "bg-indigo-600 text-white font-medium rounded-tr-none shadow-md"
                        : msg.failed
                          ? "bg-rose-950/40 text-rose-200 border border-rose-800/60 rounded-tl-none"
                          : "bg-slate-800/90 text-slate-100 border border-slate-700/60 rounded-tl-none"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <AnswerText text={msg.content} citations={msg.citations} />
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}
                    {msg.role === "assistant" && <ToolTrace steps={msg.tool_trace} />}
                  </div>

                  {msg.role === "user" && (
                    <div className="w-7 h-7 rounded-xl bg-slate-700 text-slate-200 grid place-items-center shrink-0 mt-0.5">
                      <User className="w-3.5 h-3.5" />
                    </div>
                  )}
                </div>

                {/* Full width: a table or chart squeezed into 86% of a narrow
                    panel stops being readable. */}
                {msg.role === "assistant" && <MessageBlocks blocks={msg.blocks} />}
              </div>
            ))}

            {loading && (
              <div className="space-y-1.5">
                <div className="flex gap-2.5 items-center text-slate-400 py-1">
                  <div className="w-7 h-7 rounded-xl bg-indigo-600/30 text-indigo-400 grid place-items-center">
                    <Sparkles className="w-3.5 h-3.5 animate-spin" />
                  </div>
                  <span>{status || "Working"}…</span>
                </div>
                <ToolTrace steps={steps} />
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); submit(); }}
            className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2 shrink-0"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the roll, the records, or the pipeline…"
              aria-label="Message the assistant"
              className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            {loading ? (
              <button
                type="button"
                onClick={stop}
                aria-label="Stop"
                className="w-10 h-10 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 grid place-items-center transition-all shrink-0"
              >
                <Square className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                aria-label="Send"
                className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-40 text-white grid place-items-center transition-all shadow-md shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            )}
          </form>
        </div>
      )}

      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2.5 px-4 py-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-rose-600 hover:from-indigo-500 hover:to-rose-500 text-white font-extrabold text-xs rounded-full shadow-2xl shadow-indigo-600/50 hover:scale-105 transition-all duration-200 border border-white/20"
        >
          <Bot className="w-5 h-5 text-white" />
          <span className="tracking-wide">AI Assistant</span>
        </button>
      )}
    </div>
  );
};
```

- [ ] **Step 3: Typecheck, lint and build**

```bash
cd apps/web && npm run typecheck && npm run lint && npm run build
```

Expected: clean.

- [ ] **Step 4: Verify in the running app**

Start the dev server through the preview tooling (never `npm run dev` in a shell), then check each of these against the real 3,473-elector database:

1. `Voters by gender` — a chart appears, and the prose contains no figure the chart does not.
2. `Find electors named Muthu` — a table appears, and names in the prose are clickable chips.
3. Click a chip — the main workspace opens that elector; the panel stays open.
4. `Which pages failed OCR?` — a table of pages, or an honest statement that none did.
5. `Does part 289's count match the roll?` — the declared and extracted counts, both from SQL.
6. `hello` — answers immediately, with no tool trace.
7. Expand `Ran N steps` on a data answer — the tools and row counts are listed.
8. Press Stop mid-answer — streaming halts and the partial answer remains.
9. Open the history menu, reopen a past thread — the tables and charts replay.

Check the browser console and the server log for errors after each. Capture a screenshot of a table answer and one of a chart answer.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/FloatingAiChatbot.tsx apps/web/src/components/ai/ThreadMenu.tsx
git commit -m "feat(web): wire the streaming agentic assistant into the panel"
```

---

## Verification before calling this done

Run all of it, and paste the output rather than summarising it:

```bash
npm run test:backend
```

```bash
cd apps/web && npm run typecheck && npm run lint && npm run build
```

Then confirm, by inspection rather than assumption:

- [ ] `POST /api/voters/ai-copilot` still answers — the legacy endpoint was not broken.
- [ ] `test_infographic.py` and `test_nvidia_ai_service.py` pass unmodified.
- [ ] `SELECT * FROM app_settings` through the chat is refused, and the refusal is visible to the operator.
- [ ] A question whose answer needs no tool still returns in about a second.
- [ ] The nine manual checks in Task 15 Step 4 all pass.
