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
    # A frame that parses fine but carries no content (e.g. the role-announcing
    # frame most providers send first) produces no output and no marker — this
    # is not data loss, there was never any content to lose.
    frames = [
        json.dumps({"choices": [{"delta": {"role": "assistant"}}]}),
        json.dumps({"choices": [{"delta": {"content": "ok"}}]}),
    ]
    monkeypatch.setattr(svc.urllib.request, "urlopen", lambda *a, **k: _sse(*frames))
    assert "".join(svc.stream_chat([], CREDS, temperature=0.3, max_tokens=64)) == "ok"


def test_stream_chat_flags_an_unparseable_frame_instead_of_going_silent(monkeypatch):
    # Unlike a contentless frame, a frame that FAILS to parse as JSON is always a
    # reliable signal something was lost — valid JSON, however short, always
    # parses. The stream still terminates cleanly with [DONE] here; the marker
    # must still appear because content genuinely went missing along the way.
    frames = [
        json.dumps({"choices": [{"delta": {"content": "ok"}}]}),
        "not json at all",
    ]
    monkeypatch.setattr(svc.urllib.request, "urlopen", lambda *a, **k: _sse(*frames))
    out = "".join(svc.stream_chat([], CREDS, temperature=0.3, max_tokens=64))
    assert out == "ok\n\n[Part of the response could not be read and has been omitted.]"


def test_stream_chat_flags_truncation_when_stream_ends_without_done(monkeypatch):
    # A connection that drops mid-write: one good frame, then a frame cut off
    # mid-JSON, then nothing — no [DONE] sentinel at all. Silently returning
    # "Hi " here would read as a complete answer; Task 11 hands this text
    # straight to the number guard and presents it as the assistant's reply.
    body = (
        f"data: {json.dumps({'choices': [{'delta': {'content': 'Hi '}}]})}\n\n"
        'data: {"choices": [{"delta": {"content": "cut off\n\n'
    )
    monkeypatch.setattr(
        svc.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(body.encode("utf-8"))
    )
    out = "".join(svc.stream_chat([], CREDS, temperature=0.3, max_tokens=64))
    assert out == "Hi \n\n[Part of the response could not be read and has been omitted.]"


def test_stream_chat_reports_missing_credentials_without_calling_out(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("urlopen should not be called without an API key")

    monkeypatch.setattr(svc.urllib.request, "urlopen", fail_if_called)
    unconfigured = AiCredentials(api_key="", base_url="https://example.invalid/v1", model="test-model")
    out = "".join(svc.stream_chat([], unconfigured, temperature=0.3, max_tokens=64))
    assert "No API key is configured" in out


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


def test_400_without_tools_sent_is_never_reported_unsupported(monkeypatch):
    # A 400 whose body happens to mention "tool_choice" for an unrelated reason
    # must not be read as "this model refused tool calling" when no tools were
    # even offered in the request.
    import urllib.error

    detail = json.dumps({"error": {"message": "Invalid tool_choice: value not in enum"}})

    def raise_400(*a, **k):
        raise urllib.error.HTTPError(
            url="https://example.invalid/v1/chat/completions",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(detail.encode()),
        )

    monkeypatch.setattr(svc.urllib.request, "urlopen", raise_400)
    outcome = svc.chat_with_tools([], CREDS, [], temperature=0.2, max_tokens=256)
    assert outcome.unsupported is False


def test_tool_support_is_remembered_per_model(monkeypatch):
    # _TOOL_SUPPORT is module-level cache state; swap in a fresh dict so this
    # test does not leak "model-a"/"model-b" entries into whatever else runs
    # in the same process.
    monkeypatch.setattr(svc, "_TOOL_SUPPORT", {})
    svc.remember_tool_support("model-a", False)
    svc.remember_tool_support("model-b", True)
    assert svc.supports_native_tools("model-a") is False
    assert svc.supports_native_tools("model-b") is True
    assert svc.supports_native_tools("model-never-seen") is None


def test_existing_behaviour_is_untouched():
    # The legacy path must keep working exactly as before.
    assert svc.wants_infographic("voters by gender") is True
    assert svc.local_infographic_spec("voters by gender")["dimension"] == "gender"
