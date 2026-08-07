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


# ---------------------------------------------------------------------------
# Adversarial probing of the four carried-forward requirements, plus other
# scripted-model behaviour the brief calls out: repeated tool calls, a tool
# that raises outside its declared contract, budget exhaustion mid-turn, and
# a turn where every tool call fails.
# ---------------------------------------------------------------------------


def test_percentage_phrased_confidence_survives_the_guard(monkeypatch):
    """(a) `permitted_percentages` must reach the guard, or a legitimate
    percentage-phrased sentence about a confidence score is dropped.
    """
    _script(
        monkeypatch,
        [
            ToolCallOutcome(tool_calls=[{"id": "c1", "name": "file_status", "arguments": {}}]),
            ToolCallOutcome(content=""),
        ],
        answer="Average confidence across the corpus is about 87%.",
    )
    monkeypatch.setattr(loop, "execute", lambda session, name, args: {"mean_confidence": 0.87})
    events = _drain("how confident is the OCR")
    done = events[-1]
    assert done.type == "done"
    assert "87%" in done.data["content"]


def test_a_provider_notice_mid_stream_is_not_treated_as_content(monkeypatch):
    """(b) `stream_chat` yields provider errors as bracketed text in the same
    stream as real content. That text must never be checked against the
    number guard as if a tool had attested its digits, and it must not
    silently vanish either.
    """
    _script(monkeypatch, [ToolCallOutcome(content="")])
    monkeypatch.setattr(
        loop,
        "stream_chat",
        lambda *a, **k: iter(
            [
                "The roll is small. ",
                "\n\n[Rate limited by the provider (HTTP 429) 1000 requests remaining]",
            ]
        ),
    )
    events = _drain("how many electors")
    done = events[-1]
    assert done.type == "done"
    assert "1000" not in done.data["content"]
    assert "429" not in done.data["content"]
    assert done.data["provider_notice"] and "429" in done.data["provider_notice"]
    statuses = [e.data.get("message", "") for e in events if e.type == "status"]
    assert any("provider stopped early" in s.lower() for s in statuses)


def test_a_lone_false_positive_unsupported_flag_does_not_downgrade_an_established_model(
    monkeypatch,
):
    """(c) `chat_with_tools` flags `unsupported` from a substring match on a 400
    body that can false-positive on ordinary errors (a bad max_tokens value
    mentioning "function", a deprecated function_call warning). Once a model
    is already known to support tools, a single such flag must not overwrite
    that via `remember_tool_support` -- it should be treated as this call's
    problem, not evidence the model changed capability.
    """

    def fake_tools(messages, creds, tools, **_k):
        if tools:
            return ToolCallOutcome(
                error="max_tokens must be a positive integer; this function argument was invalid",
                status=400,
                unsupported=True,
            )
        return ToolCallOutcome(content='{"answer": "Still fine."}')

    monkeypatch.setattr(loop, "chat_with_tools", fake_tools)
    monkeypatch.setattr(loop, "stream_chat", lambda *a, **k: iter(["Still fine."]))
    monkeypatch.setattr(loop, "supports_native_tools", lambda _m: True)  # already established
    recorded = {}
    monkeypatch.setattr(
        loop, "remember_tool_support", lambda model, ok: recorded.setdefault(model, ok)
    )

    events = _drain("how many electors")
    assert recorded == {}
    assert "done" in _types(events)


def test_round_budget_exhaustion_is_reported_not_silently_truncated(monkeypatch):
    """(d)-adjacent: exhausting MAX_ROUNDS while the model is still asking for
    tools is budget exhaustion too, not a clean stop -- `done.budget_exhausted`
    must say so.
    """
    always_calling = [
        ToolCallOutcome(tool_calls=[{"id": f"c{i}", "name": "roll_overview", "arguments": {}}])
        for i in range(20)
    ]
    _script(monkeypatch, always_calling, answer="Ran out.")
    events = _drain("keep going forever")
    done = events[-1]
    assert done.data["budget_exhausted"] is True


def test_a_model_calling_the_same_tool_repeatedly_stays_bounded(monkeypatch):
    repeat = [
        ToolCallOutcome(tool_calls=[{"id": f"c{i}", "name": "roll_overview", "arguments": {}}])
        for i in range(3)
    ] + [ToolCallOutcome(content="")]
    _script(monkeypatch, repeat, answer="It is a small corpus.")
    events = _drain("tell me again and again")
    assert "done" in _types(events)
    assert len([e for e in events if e.type == "tool_call"]) <= loop.MAX_TOOL_CALLS


def test_every_tool_call_failing_still_yields_a_safe_answer(monkeypatch):
    _script(
        monkeypatch,
        [
            ToolCallOutcome(tool_calls=[{"id": "c1", "name": "get_voter", "arguments": {}}]),
            ToolCallOutcome(tool_calls=[{"id": "c2", "name": "get_voter", "arguments": {}}]),
            ToolCallOutcome(content=""),
        ],
        answer="I could not verify anything for this request.",
    )
    events = _drain("who is voter nobody, twice")
    results = [e for e in events if e.type == "tool_result"]
    assert results and all(r.data["ok"] is False for r in results)
    done = events[-1]
    assert done.type == "done"
    assert done.data["content"]


def test_a_tool_that_raises_outside_toolerror_does_not_crash_the_turn(monkeypatch):
    """Belt-and-braces: `registry.execute` is the boundary that promises to
    turn every handler exception into `ToolError`. This proves the loop
    itself does not depend on that promise -- a bug that let a bare
    exception past it still ends the turn as a reported failure, not an
    unhandled exception breaking the whole SSE stream.
    """

    def boom(session, name, args):
        raise RuntimeError("unexpected bug in a tool handler")

    _script(
        monkeypatch,
        [
            ToolCallOutcome(tool_calls=[{"id": "c1", "name": "roll_overview", "arguments": {}}]),
            ToolCallOutcome(content=""),
        ],
        answer="Something went wrong looking that up.",
    )
    monkeypatch.setattr(loop, "execute", boom)
    events = _drain("what does the roll cover")
    result = next(e for e in events if e.type == "tool_result")
    assert result.data["ok"] is False
    assert "done" in _types(events)


def test_an_unknown_tool_name_from_the_planner_path_is_also_reported(monkeypatch):
    """The non-native (planner) transport builds its own tool_calls list by
    hand, from JSON the model wrote -- an unknown tool name here must be
    caught the same way as it is on the native path.
    """

    calls = {"n": 0}

    def fake_tools(messages, creds, tools, **_k):
        if tools:
            return ToolCallOutcome(error="bad request", status=400, unsupported=True)
        calls["n"] += 1
        if calls["n"] == 1:
            return ToolCallOutcome(content='{"tool": "not_a_real_tool", "args": {}}')
        return ToolCallOutcome(content='{"answer": "I cannot do that."}')

    monkeypatch.setattr(loop, "chat_with_tools", fake_tools)
    monkeypatch.setattr(loop, "stream_chat", lambda *a, **k: iter(["I cannot do that."]))
    monkeypatch.setattr(loop, "supports_native_tools", lambda _m: None)
    monkeypatch.setattr(loop, "remember_tool_support", lambda model, ok: None)

    events = _drain("do something impossible")
    result = next(e for e in events if e.type == "tool_result")
    assert "Unknown tool" in result.data["error"]
    assert "done" in _types(events)


def test_sentences_do_not_split_inside_a_decimal_figure():
    """CRITICAL 1: `_sentences` split on any '.', '!', '?' or '\\n' with no
    lookahead, so "0.412" broke into "0." and "412" as two fragments -- a
    false sentence boundary inside a single number. `guards._SENTENCE`
    already gets this right (it requires whitespace after the terminator);
    this pins `_sentences` to the same rule.
    """
    buffer = "Mean OCR confidence across the corpus is 89.7%. Confidence bottoms out at 0.412."
    complete, tail = loop._sentences(buffer)
    assert complete == ["Mean OCR confidence across the corpus is 89.7%."]
    assert tail.strip() == "Confidence bottoms out at 0.412."
    # Neither fragment may contain a lone digit-dot split.
    for piece in complete:
        assert "89." not in piece or "89.7" in piece


def test_a_sentence_with_two_decimal_figures_survives_the_full_pipeline(monkeypatch):
    """End-to-end reproduction of CRITICAL 1 through the real `run_agent`: a
    model answer quoting two decimal figures, both grounded in a real tool
    result, must reach the operator intact. Before the fix, the false
    sentence boundary inside "0.412" corrupted the answer -- either the
    correct figure was dropped (neither half of a split number is
    independently permitted) or a wrong fragment survived by coincidence.
    """
    _script(
        monkeypatch,
        [
            ToolCallOutcome(tool_calls=[{"id": "c1", "name": "ocr_quality", "arguments": {}}]),
            ToolCallOutcome(content=""),
        ],
        answer="Mean confidence is 89.7%. It bottoms out at 0.412.",
    )
    monkeypatch.setattr(
        loop, "execute",
        lambda session, name, args: {"mean_confidence": 0.897, "worst_case": 0.412},
    )
    events = _drain("how confident is the OCR")
    done = events[-1]
    assert done.type == "done"
    assert done.data["dropped_sentences"] == 0
    assert "89.7%" in done.data["content"]
    assert "0.412" in done.data["content"]


def test_a_profile_figure_the_backend_itself_injected_survives_the_guard(monkeypatch):
    """IMPORTANT 3: `context.profile_sentence` puts real counts straight into
    the system prompt to save a round trip -- those counts never pass
    through `tool_results`. Before the fix, a model faithfully echoing a
    figure it was just handed got that correct sentence destroyed by its own
    guard and replaced with "I could not produce an answer I can stand
    behind," which is a true answer overwritten by a false one.
    """
    _script(
        monkeypatch,
        [ToolCallOutcome(content="")],
        answer="This workspace holds 1,093 curated electors from 0 files.",
    )
    monkeypatch.setattr(
        loop, "roll_profile",
        lambda session: {
            "voters": 1093, "files": 0, "pages": 12, "records": 1093,
            "parts": [], "part_count": 0, "constituencies": [], "constituency_count": 0,
        },
    )
    events = _drain("how big is this workspace")
    done = events[-1]
    assert done.type == "done"
    assert done.data["dropped_sentences"] == 0
    assert "1,093" in done.data["content"]
    assert (
        "I could not produce an answer" not in done.data["content"]
    )


def test_native_tool_calls_are_preceded_by_a_declaring_assistant_message(monkeypatch):
    """OpenAI-compatible transports reject a `role: "tool"` message that does
    not follow an assistant message declaring the matching `tool_call_id` --
    the loop must build that assistant turn itself, since nothing else does.

    Every other test here only inspects the loop's *events*; none of them
    would notice if the `messages` list handed to the transport were
    malformed. This test scripts `chat_with_tools` to record the actual
    `messages` argument on each call and asserts the wire-format invariant
    directly, across two rounds of tool calls.
    """
    captured: list[list[dict]] = []
    outcomes = [
        ToolCallOutcome(tool_calls=[{"id": "c1", "name": "roll_overview", "arguments": {}}]),
        ToolCallOutcome(tool_calls=[{"id": "c2", "name": "file_status", "arguments": {}}]),
        ToolCallOutcome(content=""),
    ]

    def fake_tools(messages, creds, tools, **_k):
        captured.append(list(messages))
        return outcomes.pop(0)

    monkeypatch.setattr(loop, "chat_with_tools", fake_tools)
    monkeypatch.setattr(loop, "stream_chat", lambda *a, **k: iter(["Done."]))
    monkeypatch.setattr(loop, "supports_native_tools", lambda _m: True)

    events = _drain("what does the roll cover, twice")
    assert "done" in _types(events)

    # The last call carries the fullest history -- both rounds' messages.
    final_messages = captured[-1]

    assistant_msgs = [m for m in final_messages if m.get("role") == "assistant"]
    tool_msgs = [m for m in final_messages if m.get("role") == "tool"]

    # Exactly one assistant message per round, not one per call.
    assert len(assistant_msgs) == 2
    assert [tc["id"] for tc in assistant_msgs[0]["tool_calls"]] == ["c1"]
    assert [tc["id"] for tc in assistant_msgs[1]["tool_calls"]] == ["c2"]

    assert len(tool_msgs) == 2
    for i, msg in enumerate(final_messages):
        if msg.get("role") != "tool":
            continue
        call_id = msg["tool_call_id"]
        preceding = final_messages[:i]
        assert any(
            m.get("role") == "assistant"
            and any(tc["id"] == call_id for tc in m.get("tool_calls", []))
            for m in preceding
        ), f"role:tool message for {call_id!r} has no preceding assistant message declaring it"
