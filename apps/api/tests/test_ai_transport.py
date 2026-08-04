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
