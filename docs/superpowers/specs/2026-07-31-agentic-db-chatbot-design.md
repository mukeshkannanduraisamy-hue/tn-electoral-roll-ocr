# Agentic, database-connected AI assistant

**Date:** 2026-07-31
**Status:** Approved for planning
**Scope:** Slices A (agent core) + B (tool coverage) + C (chat UI)

---

## 1. Problem

The assistant today reaches one table through six aggregates.

`nvidia_ai_service.query_nvidia_copilot` makes a single blocking call and returns
prose. When a question looks statistical, `/api/voters/ai-copilot` asks the model
for an infographic *spec* from a closed vocabulary, runs the SQL itself, and
attaches a chart. That is the whole of its database access.

Everything else in the database is invisible to it: individual electors,
households, OCR confidence, page provenance, pipeline state, polling stations,
audit history. The database holds 3,473 electors, 3,495 records, 27,886 OCR
blocks, 158 pages, 6 files, 6 polling stations and 3,474 audit entries. The
assistant can describe none of it.

Three further gaps:

* **No memory.** Every message is the first message. Follow-up questions fail.
* **No streaming.** A 30-second call shows a frozen "Working…".
* **No composition.** One question yields one answer; it cannot look something
  up and then reason about what it found.

## 2. Goal

The assistant answers any read-only question about the roll, the OCR pipeline
and the workspace — with figures that came from SQL, records that exist, and a
visible trail showing how each answer was obtained.

It does not write to the database.

## 3. Decisions

| Decision | Choice | Why |
|---|---|---|
| Capability boundary | **Read-only** | An electoral roll is a legal record. A wrong write is discovered long after it happens. |
| Database access | **Typed tools + guarded SQL** | Tools make common questions provably correct; guarded SQL covers the long tail without a code change. |
| Latency | **Two-tier router + SSE streaming** | Preserves the 0.44s path (commit `1784600`) for non-data messages; streaming keeps the slow path feeling fast. |
| Answer rendering | **Rich blocks + click-to-open** | Tables, cards and charts in the panel; citations are chips the *operator* clicks. The assistant never navigates on its own. |

### 3.1 The invariant this design preserves

The codebase's governing principle, stated in `infographic.py`, is that **the
language model never produces a number.** This design widens the aperture
without weakening the rule:

> The set of permitted figures is rebuilt from **every tool result in the turn.**
> The model may quote any number a tool returned, and no others.

So the assistant can now say "412 electors in part 289" — because SQL said so —
while remaining structurally unable to invent "roughly 400". Sentences quoting an
untraceable figure are dropped, exactly as `strip_invented_numbers` does today.

The same rule governs record references. Tools return rows carrying `id` and
`epic`. The model cites them as `[[v:<id>]]` markers. **A marker not present in
the turn's tool results is stripped before the response leaves the server.**
There are no hallucinated electors.

## 4. Architecture

```
FloatingAiChatbot (web)
      │  POST /api/ai/chat        → SSE
      ▼
routers/ai_chat.py                 thread persistence, auth, streaming
      │
      ▼
services/ai_agent/
  ├── registry.py    tool declaration → JSON schema, one source of truth
  ├── router.py      fast classifier: smalltalk | howto | data
  ├── loop.py        bounded agent loop, emits stream events
  ├── guards.py      number integrity, citation binding, budgets
  ├── context.py     cached roll profile + app-view context
  └── tools/
        electors.py   search_voters, get_voter, household_of
        analytics.py  aggregate            → wraps infographic.py
        quality.py    ocr_quality, low_confidence_records, find_anomalies
        pipeline.py   file_status, page_details, job_status
        geography.py  roll_overview, polling_station
        sql.py        run_readonly_sql
```

`nvidia_ai_service.py` keeps its existing responsibility — HTTP transport,
credential resolution, error explanation — and gains two functions: a streaming
call and a tool-calling call. **No agent logic lives in it.** Its existing public
functions (`query_nvidia_copilot`, `propose_infographic_spec`,
`narrate_infographic`, `check_credentials`, `strip_invented_numbers`,
`wants_infographic`, `local_infographic_spec`) keep their current behaviour, and
`test_nvidia_ai_service.py` keeps passing unchanged.

`infographic.py` is not modified. The `aggregate` tool calls
`validate_spec` and `build_infographic` as they stand.

### 4.1 Request flow

1. **Route.** Heuristics first — keyword and pattern matching in the spirit of
   the existing `wants_infographic`. A cheap model call resolves only genuinely
   ambiguous messages. `smalltalk` and `howto` answer directly from the fast
   model with the app guide; that path keeps today's latency. Only `data`
   enters the loop.

2. **Loop.** Bounded at **4 tool rounds, 6 tool calls, 20 seconds wall clock.**
   Two transports behind one interface:
   * *native* — OpenAI-style `tools` array, when the configured model supports it;
   * *planner* — the model emits `{"tool": "...", "args": {...}}`; the backend
     validates and executes, and feeds the result back as the next turn.

   Support is probed once per model name and cached, so changing the model from
   the Settings page cannot break the assistant. The planner transport is what
   makes an 8B model usable.

3. **Stream.** SSE events: `status`, `tool_call`, `tool_result`, `token`,
   `citations`, `blocks`, `done`, `error`.

### 4.1.1 API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/ai/chat` | Send a message; streams the reply. |
| `GET` | `/api/ai/threads` | List the caller's threads. |
| `GET` | `/api/ai/threads/{id}` | Replay one thread's messages. |
| `DELETE` | `/api/ai/threads/{id}` | Delete a thread and its messages. |

`POST /api/ai/chat` carries the message, an optional `thread_id` and the app-view
context, so it cannot be consumed by `EventSource` (which is GET-only). The
client reads the response body as a stream via `fetch` and parses SSE frames
itself. `sse-starlette` — already a dependency — serves the response.

The existing `POST /api/voters/ai-copilot` stays in place and unchanged, so
nothing breaks while the new endpoint is built alongside it.

### 4.2 Errors

* A tool that raises reports its failure into the trace, and the model is told it
  failed. It answers without that data rather than guessing.
* Budget exhaustion returns the partial answer and an explicit "I ran out of
  steps" — never a confident summary of work that did not finish.
* No configured model falls back to the existing offline guide
  (`_local_rule_fallback`).
* A rejected SQL query is returned to the operator with the reason it was
  rejected.

## 5. Tool surface

All tools are read-only. Each declares a Pydantic argument model, a UI label, and
returns structured data — never prose.

### Electors

* **`search_voters`** — `name, epic, part_number, constituency, gender, min_age,
  max_age, house_number, verified, is_supplement, source_file_id, limit ≤ 50,
  offset`. Returns matching rows and the total matched.
* **`get_voter`** — `voter_id | epic`. Full record, per-field OCR confidence,
  source page reference and bbox.
* **`household_of`** — `voter_id | epic`. Household and resolved families,
  reusing the logic behind the existing household endpoint in `voters.py`.

### Analytics

* **`aggregate`** — `metric, dimension?, filters?`. Delegates to
  `infographic.build_infographic`. Same 6 metrics, 7 dimensions, 9 filters, same
  chart payload the frontend already renders.

### Quality

* **`ocr_quality`** — `scope: file | page | part, id`. Mean and minimum
  confidence, error and warning counts, edited and reviewed counts, and the
  worst-performing fields.
* **`low_confidence_records`** — `scope?, threshold?, limit`. Records ranked by
  `min_confidence`: a review queue, produced read-only.
* **`find_anomalies`** — `kind, limit`, where `kind` is one of
  `duplicate_epic`, `implausible_age`, `missing_field`, `epic_format`,
  `count_mismatch`. Returns the rows and why each was flagged.

`count_mismatch` exists because `polling_stations` stores *declared*
`total_electors`, `male_electors` and `female_electors`, while `voters` holds
what OCR actually extracted. Comparing them is an integrity check the workspace
does not currently perform.

### Pipeline

* **`file_status`** — `file_id?`. Status, pages done, page count, errors, template.
* **`page_details`** — `page_id | file_id + page_number`. Page type,
  classification confidence, `ocr_ms`, error, record count.
* **`job_status`** — `job_id?`. Queue state, completed and failed pages, current item.

### Geography and shape

* **`roll_overview`** — files, parts, constituencies, polling stations, counts,
  ingest dates.
* **`polling_station`** — `part_number | station_id`. Station details including
  its declared elector counts.

### Escape hatch

* **`run_readonly_sql`** — `sql, rationale`. Returns rows and the SQL, which is
  shown to the operator.

## 6. The SQL guard

A parser is not a security boundary, so the guard is layered:

1. **Parse.** A single `SELECT` or `WITH` only. Rejected: multiple statements,
   comment-based smuggling, and any of `INSERT`, `UPDATE`, `DELETE`, `DROP`,
   `ALTER`, `CREATE`, `REPLACE`, `ATTACH`, `PRAGMA`, `VACUUM`.

2. **Table allowlist — not a denylist.** Permitted: `voters`, `records`,
   `pages`, `files`, `polling_stations`, `photos`, `ocr_blocks`, `jobs`,
   `summaries`, `audit_logs`. Everything else is refused.

   **`users`, `sessions` and `app_settings` are unreachable.** `app_settings`
   stores the NVIDIA API key; the assistant must never be able to read its own
   credentials out of the database.

3. **Separate read-only connection.** A second SQLite handle opened
   `file:…?mode=ro`. If the parser were ever bypassed, the connection still
   cannot write.

4. **Forced `LIMIT 200`** and a statement timeout enforced through SQLite's
   progress handler.

5. **Displayed.** The SQL appears in the chat trace. An answer that cannot be
   audited cannot be trusted.

## 7. Data model

Two tables, one Alembic migration in `apps/api/migrations/versions`:

```
chat_threads
  id           str  pk
  user_id      str  fk → users.id, CASCADE
  title        str
  created_at   datetime
  updated_at   datetime

chat_messages
  id           str  pk
  thread_id    str  fk → chat_threads.id, CASCADE
  role         str  user | assistant
  content      text
  tool_trace   json
  citations    json
  blocks       json
  created_at   datetime
```

History window: the last 12 messages are sent verbatim; older turns collapse into
a running summary. This bounds prompt growth, which is what commits `9e250eb` and
`1784600` were fighting when they cut `max_tokens` and the HTTP timeout.

A cached **roll profile** — constituency names, part numbers, file names, row
counts — is injected into the system prompt so the model knows the shape of the
data without spending a tool call discovering it. It is refreshed when files
change.

## 8. Frontend

* `useAiChat` hook reads the SSE stream and exposes a **Stop** control.
* Messages render as typed blocks: `prose | table | voter_card | chart |
  tool_trace | sql`.
* `[[v:<id>]]` markers render as `<VoterChip>`. Clicking one opens that elector
  in the main workspace. **The chat hands the operator a link; the operator
  decides.** This preserves the boundary drawn when UI-driving was removed
  (`FloatingAiChatbot.tsx` header comment).
* Collapsible trace — *"Ran 2 steps"* expanding to
  `search_voters(part_number=289) → 412 rows`.
* Thread history dropdown and a New thread control.
* The panel widens to ~520px at `sm` and above; tables sit in their own
  horizontal-scroll container so the 380px case still reads.
* `InfographicCard` is reused unchanged for the `chart` block.

## 9. Testing

* Every tool against a seeded fixture database (`apps/api/tests/fixtures`).
* **Guard tests written as adversarial cases:** write attempts, multiple
  statements, comment smuggling, `app_settings` and `users` access, absent
  `LIMIT`, timeout enforcement.
* Number integrity: fabricated figures dropped; tool-sourced figures preserved.
* Citation binding: unknown `[[v:…]]` markers stripped.
* Router classification over sample English and Tamil messages.
* Loop behaviour against a mocked model: scripted tool calls on both transports,
  budget exhaustion, tool failure, malformed planner JSON.
* `test_nvidia_ai_service.py` and `test_infographic.py` stay green without
  modification.

## 10. Out of scope

Deferred to their own specs:

* **Briefings** — composed multi-chart reports over a file or part.
* **Proactive quality** — a standing "these records look wrong" analysis surfaced
  outside the chat.
* **Writes of any kind** — verification, field correction, job control, exports.
* **Vision re-reading** of a field from its stored bbox crop.
