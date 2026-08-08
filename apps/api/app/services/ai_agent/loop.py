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
from .context import permitted_from_profile, profile_sentence, roll_profile
from .guards import (
    bind_citations,
    collect_citations,
    permitted_numbers,
    permitted_percentages,
    strip_unverified_numbers,
)
from .registry import ToolError, describe_tools, execute, label_for, openai_tools

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
    """Split off the complete sentences, keeping the unfinished tail.

    A terminator (`.!?`) only ends a sentence when it is followed by
    whitespace or the end of the buffer -- the same rule `guards._SENTENCE`
    applies. Without that lookahead, a decimal figure like "89.7" or "0.412"
    is itself a false sentence boundary: the digits before and after the dot
    get scanned as two separate fragments by `strip_unverified_numbers`, so
    a real figure fails the guard (neither half is independently permitted)
    or a fabricated one slips through (whichever half's digits happen to
    coincide with something permitted). Since the buffer is streamed
    token-by-token, a terminator at the very end of what has arrived so far
    is genuinely ambiguous -- "0.4" could still become "0.412" on the next
    delta -- so it is treated as unfinished and left in the tail rather than
    guessed at; it flushes once more text (or the stream's end) confirms it.
    A newline always ends a sentence outright, matching `guards._SENTENCE`'s
    `\\n+` alternative.
    """
    out: List[str] = []
    start = 0
    n = len(buffer)
    for i, ch in enumerate(buffer):
        if ch == "\n":
            piece = buffer[start : i + 1].strip()
            if piece:
                out.append(piece)
            start = i + 1
        elif ch in ".!?":
            j = i + 1
            if j >= n:
                # Could still be a decimal point mid-figure; wait for more.
                continue
            if buffer[j].isspace():
                piece = buffer[start:j].strip()
                if piece:
                    out.append(piece)
                start = j
    return out, buffer[start:]


#: `stream_chat` folds provider failures into the same text stream as real
#: content — see nvidia_ai_service.stream_chat's except blocks and the
#: `had_parse_failure` branch, all of which yield a single chunk of the form
#: "\n\n[<explanation>]" and then end the generator. That chunk is not
#: assistant prose: it carries digits (status codes, quota counts) that must
#: never be checked against `permitted_numbers` and presented as if a tool
#: had attested them, and it must not simply vanish either — an operator who
#: sees a short answer needs to know it was cut short and why. Detected at
#: the whole-chunk level (not by scanning the assembled buffer) because every
#: call site in `stream_chat` yields the marker as one complete chunk, never
#: split across deltas the way real token-by-token content is.
def _as_provider_notice(delta: str) -> Optional[str]:
    if delta.startswith("\n\n[") and delta.rstrip().endswith("]"):
        return delta.strip()[1:-1].strip()
    if delta.startswith("[") and delta.rstrip().endswith("]"):
        return delta.strip()[1:-1].strip()
    return None


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

    # `context.invalidate()` is deliberately not called from here. This loop is
    # a per-message read path: it never observes a file finishing processing
    # (that event happens elsewhere, in whatever pipeline step ingests a
    # roll), so it has nothing to invalidate the cache *on*. Ownership of
    # calling `invalidate()` belongs to that ingestion step, not to a reader.
    # Until it is wired up there, `roll_profile`'s 60-second TTL is the only
    # staleness bound a caller here gets -- accepted, not overlooked.
    try:
        profile_dict = roll_profile(session)
    except Exception:
        logger.exception("Could not build the roll profile")
        profile_dict = {}
    profile = profile_sentence(profile_dict)
    profile_allowed, profile_percentages = permitted_from_profile(profile_dict)

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
    # Maps a failed call's (tool_name, canonical_args) to the error text it
    # produced. `json.dumps(..., sort_keys=True, default=str)` canonicalises
    # the arguments so key order alone cannot make two identical calls look
    # different. A model that repeats a call verbatim after it already failed
    # gains nothing by trying again -- the database state has not changed --
    # so the repeat is not re-executed; it still costs a slot from
    # MAX_TOOL_CALLS (a free retry loop is still a loop), but the feedback it
    # gets is explicit about the repeat rather than the same error text a
    # second time, which evidently read to the model as worth trying again.
    failed_calls: Dict[tuple, str] = {}

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
                # `chat_with_tools` flags `unsupported` from a substring match
                # against a 400 body ("tool"|"function") — a heuristic a
                # reviewer reproduced false positives for (a malformed
                # max_tokens complaint, a deprecated function_call warning).
                # Always log the raw body so a false positive is diagnosable.
                # But only let it *write* the cache when this model's support
                # was still unknown: once a call has actually succeeded with
                # `tools` attached (native is True), a single later refusal is
                # more likely one of those false positives than a model that
                # changed capability mid-session, so it is treated as a
                # this-turn-only fallback rather than being allowed to erase a
                # confirmed capability for every later turn.
                logger.warning(
                    "%s rejected the tools array (status=%s): %s",
                    creds.model, outcome.status, outcome.error,
                )
                if native is not True:
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

        if native is not False:
            # OpenAI-compatible transports require every `role: "tool"`
            # message to follow an assistant message that declared the
            # matching `tool_call_id` -- otherwise the conversation is
            # malformed and a real provider will reject the next request.
            # This is that assistant turn: one per round, listing every call
            # the model asked for this round, appended before any of that
            # round's `tool` results below. (The planner path does not need
            # this -- it feeds results back as plain `user` messages, not
            # `role: "tool"`, so there is no `tool_call_id` contract to
            # satisfy.)
            assistant_turn: Dict[str, Any] = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["arguments"]),
                        },
                    }
                    for call in outcome.tool_calls
                ],
            }
            # Only set when the model actually wrote prose alongside its tool
            # calls. Omitted rather than set to `None`: the key is not part
            # of every provider's accepted schema for an assistant message,
            # while omitting it entirely is unambiguous and matches what we
            # send when there was nothing to say.
            if outcome.content:
                assistant_turn["content"] = outcome.content
            messages.append(assistant_turn)

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

            call_key = (name, json.dumps(args, sort_keys=True, default=str))
            prior_error = failed_calls.get(call_key)

            if prior_error is not None:
                # Already tried this exact call and it already failed -- do
                # not spend a database round trip repeating it. The slot is
                # still charged against the budget above (calls_made already
                # incremented), so this cannot turn into a free retry loop.
                error_text = (
                    f"You already called {name} with these exact arguments and it "
                    f"failed with: {prior_error} Repeating it will not change the "
                    "result. Change the arguments or use a different tool."
                )
            else:
                try:
                    result = execute(session, name, args)
                except ToolError as exc:
                    error_text = str(exc)
                except Exception as exc:
                    # `registry.execute` already wraps every exception a handler
                    # raises into `ToolError` -- this branch is a belt-and-braces
                    # net against a bug in `execute` itself or a future tool that
                    # forgets that contract. Either way, one broken tool must
                    # degrade to "this step failed" rather than take down the
                    # whole SSE turn the operator is watching.
                    logger.exception("Tool %s failed outside its ToolError contract", name)
                    error_text = f"{name} failed unexpectedly ({type(exc).__name__})."
                else:
                    error_text = None
                if error_text is not None:
                    failed_calls[call_key] = error_text

            if error_text is not None:
                trace.append({"tool": name, "args": args, "ok": False, "error": error_text})
                yield AgentEvent(
                    "tool_result",
                    {"id": call.get("id"), "name": name, "ok": False, "error": error_text},
                )
                messages.append(
                    {"role": "user", "content": f"Tool {name} failed: {error_text}"}
                    if native is False
                    else {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": f"ERROR: {error_text}",
                    }
                )
                continue

            tool_results.append(result)
            try:
                made_blocks.extend(blocks_for(name, result))
            except Exception:
                # Rendering is cosmetic; a shape `blocks.py` was not written
                # for must not cost the operator the verified prose answer.
                logger.exception("blocks_for(%s) failed on a successful result", name)
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
    else:
        # The `for` loop ran out of rounds without ever `break`-ing, which
        # only happens when every single round returned a fresh tool call —
        # the model was still asking for data when the round budget cut it
        # off. That is exhaustion, not a clean stop, so it must set the same
        # flag the call/deadline checks set, otherwise the answer prompt below
        # never asks the model to say the turn was cut short and
        # `done.budget_exhausted` reports False for a truncated turn.
        budget_hit = True

    # --- write the answer ---------------------------------------------------
    yield AgentEvent("status", {"message": "Writing"})

    # Unioned with the roll-profile seed built above: those counts were
    # injected into the system prompt directly, never passed through a tool
    # call, so `tool_results` alone would not contain them -- see
    # `context.permitted_from_profile` for why a model correctly echoing a
    # figure it was handed would otherwise fail its own answer's guard.
    allowed = permitted_numbers(tool_results, user_prompt=message) | profile_allowed
    percentages = permitted_percentages(tool_results) | profile_percentages
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
    provider_notice: Optional[str] = None
    for delta in stream_chat(messages, creds, temperature=0.4, max_tokens=600):
        notice = _as_provider_notice(delta)
        if notice is not None:
            # Not assistant content: never folded into `buffer`, never checked
            # against the number guard, never silently dropped either.
            provider_notice = notice
            yield AgentEvent("status", {"message": f"The provider stopped early: {notice}"})
            continue

        buffer += delta
        complete, buffer = _sentences(buffer)
        for sentence in complete:
            kept, dropped = strip_unverified_numbers(sentence, allowed, percentages)
            dropped_total += dropped
            if not kept:
                continue
            bound, _ = bind_citations(kept, known)
            if bound:
                verified.append(bound)
                yield AgentEvent("token", {"text": bound + " "})

    tail = buffer.strip()
    if tail:
        kept, dropped = strip_unverified_numbers(tail, allowed, percentages)
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
            "provider_notice": provider_notice,
        },
    )
