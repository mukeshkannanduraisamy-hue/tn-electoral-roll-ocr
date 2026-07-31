"""The chat assistant and its credential handling.

The assistant answers questions; it does not drive the interface. And the API key
is write-only over the HTTP surface — set, replaced, tested or cleared, never read
back — so a compromised browser session cannot exfiltrate it.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import AppSettingRow, session_scope  # noqa: E402
from app.services import app_settings as store  # noqa: E402
from app.services.app_settings import AiCredentials, mask_secret  # noqa: E402
from app.services.nvidia_ai_service import (  # noqa: E402
    ChatOutcome,
    _explain_http_error,
    _local_rule_fallback,
    check_credentials,
    query_nvidia_copilot,
)

UNSET = AiCredentials(api_key="", base_url="", model="")


@pytest.fixture
def session():
    with session_scope() as s:
        yield s


@pytest.fixture
def clean_settings(session):
    """Remove any AI settings before and after, so runs do not affect each other.

    Uses the test's own session rather than opening a second one — SQLite would
    block the write behind the still-open transaction and the suite would hang.
    """
    def purge():
        session.query(AppSettingRow).filter(
            AppSettingRow.key.in_([
                store.NVIDIA_API_KEY, store.NVIDIA_BASE_URL, store.NVIDIA_MODEL,
            ])
        ).delete(synchronize_session=False)
        session.commit()
    purge()
    yield
    purge()


# --- The assistant answers; it does not change the UI ----------------------


def test_empty_message_is_answered_not_errored():
    assert "Ask me anything" in query_nvidia_copilot("")["reply"]


def test_reply_carries_no_ui_commands():
    """The customiser is gone: a reply is prose, not instructions for the app."""
    result = query_nvidia_copilot("switch to emerald theme", UNSET)
    assert set(result) == {"reply"}
    assert "ui_changes" not in result


def test_offline_fallback_answers_from_the_guide():
    assert "Excel" in _local_rule_fallback("how do I export?")["reply"]
    assert "Family tab" in _local_rule_fallback("show me the family tree")["reply"]
    assert "23 database columns" in _local_rule_fallback("how do columns work")["reply"]


def test_offline_fallback_says_it_is_offline_when_it_cannot_help():
    reply = _local_rule_fallback("who won the 2019 election")["reply"]
    assert "not configured" in reply
    assert "Settings" in reply


def test_unconfigured_credentials_never_attempt_a_call():
    """With no key the offline guide answers, rather than a failed request."""
    result = query_nvidia_copilot("how do I export to Excel?", UNSET)
    assert "Excel" in result["reply"]


def test_check_credentials_reports_the_missing_key_plainly():
    outcome = check_credentials(UNSET)
    assert outcome["ok"] is False
    assert "No API key" in outcome["detail"]


# --- Diagnostics: a failure must say which failure it was -------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "key was rejected"),
        (403, "key was rejected"),
        (404, "was not found"),
        (429, "Rate limited"),
        (400, "malformed"),
        (500, "server error"),
        (503, "server error"),
    ],
)
def test_each_status_maps_to_the_action_it_implies(status, expected):
    """One generic "did not respond" left an operator with nothing to act on:
    a rejected key, a missing model and an exhausted quota need different fixes."""
    assert expected in _explain_http_error(status, "", "some/model")


def test_a_rejected_key_names_the_model_it_lacks_access_to():
    message = _explain_http_error(403, "", "z-ai/glm-5.2")
    assert "z-ai/glm-5.2" in message
    assert "build.nvidia.com" in message


def test_a_missing_model_points_at_the_name_and_url():
    message = _explain_http_error(404, "404 page not found", "nope/gone")
    assert "nope/gone" in message
    assert "base URL" in message


def test_an_error_body_is_truncated_rather_than_dumped():
    message = _explain_http_error(400, "x" * 5000, "some/model")
    assert len(message) < 500


def test_an_outcome_is_only_ok_with_actual_content():
    assert ChatOutcome(content="hello").ok is True
    assert ChatOutcome(content="").ok is False
    assert ChatOutcome(error="boom").ok is False


def test_reasoning_exhaustion_is_reported_as_such(monkeypatch):
    """A reasoning model can spend its whole budget thinking. That is a budget
    problem, not an empty answer, and the message must say so."""
    import app.services.nvidia_ai_service as svc

    def fake_urlopen(req, timeout=None):
        class R:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
            def read(self_inner):
                return json.dumps({
                    "choices": [{
                        "message": {"content": "", "reasoning_content": "thinking…"},
                        "finish_reason": "length",
                    }]
                }).encode()
        return R()

    monkeypatch.setattr(svc.urllib.request, "urlopen", fake_urlopen)
    creds = AiCredentials("nvapi-test", "https://example.test/v1", "reasoner/x")
    outcome = svc._chat([{"role": "user", "content": "hi"}], creds,
                        temperature=0.0, max_tokens=16)
    assert outcome.ok is False
    assert "reasoning" in outcome.error
    assert "16-token" in outcome.error


def test_content_is_returned_when_the_model_answers(monkeypatch):
    import app.services.nvidia_ai_service as svc

    def fake_urlopen(req, timeout=None):
        class R:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
            def read(self_inner):
                return json.dumps({
                    "choices": [{
                        "message": {"content": " ready ", "reasoning_content": "…"},
                        "finish_reason": "stop",
                    }]
                }).encode()
        return R()

    monkeypatch.setattr(svc.urllib.request, "urlopen", fake_urlopen)
    creds = AiCredentials("nvapi-test", "https://example.test/v1", "reasoner/x")
    outcome = svc._chat([{"role": "user", "content": "hi"}], creds,
                        temperature=0.0, max_tokens=512)
    assert outcome.ok is True
    assert outcome.content == "ready"


# --- Masking: the key is never disclosed -----------------------------------


def test_mask_shows_the_prefix_and_last_four_only():
    hint = mask_secret("nvapi-abcdefghijklmnopqrstuvwxyz1234")
    assert hint == "nvapi-…1234"
    assert "abcdefgh" not in hint


def test_mask_fully_redacts_something_too_short_to_hint_at():
    assert mask_secret("short") == "•" * 5
    assert mask_secret("") == ""
    assert mask_secret(None) == ""


def test_describe_never_returns_the_key(session, clean_settings):
    secret = f"nvapi-{uuid.uuid4().hex}{uuid.uuid4().hex}"
    store.set_setting(session, store.NVIDIA_API_KEY, secret, "tester")
    session.commit()

    described = store.describe_ai_config(session)
    assert described["configured"] is True
    assert described["source"] == "settings"
    assert described["updated_by"] == "tester"
    # The whole point: the secret is absent from every value in the payload.
    assert secret not in str(described)
    assert described["key_hint"] == mask_secret(secret)


# --- Storage semantics ------------------------------------------------------


def test_a_setting_round_trips(session, clean_settings):
    store.set_setting(session, store.NVIDIA_MODEL, "some/model", "tester")
    session.commit()
    assert store.get_setting(session, store.NVIDIA_MODEL) == "some/model"


def test_blank_and_missing_settings_read_as_none(session, clean_settings):
    assert store.get_setting(session, store.NVIDIA_MODEL) is None
    store.set_setting(session, store.NVIDIA_MODEL, "   ", "tester")
    session.commit()
    assert store.get_setting(session, store.NVIDIA_MODEL) is None


def test_clearing_reports_whether_anything_was_there(session, clean_settings):
    assert store.clear_setting(session, store.NVIDIA_API_KEY) is False
    store.set_setting(session, store.NVIDIA_API_KEY, "nvapi-xyz", "tester")
    session.commit()
    assert store.clear_setting(session, store.NVIDIA_API_KEY) is True
    session.commit()
    assert store.get_setting(session, store.NVIDIA_API_KEY) is None


def test_settings_override_the_environment(session, clean_settings, monkeypatch):
    """An operator must be able to change the key without a redeploy."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-from-environment")
    assert store.resolve_ai_credentials(session).api_key == "nvapi-from-environment"
    assert store.describe_ai_config(session)["source"] == "environment"

    store.set_setting(session, store.NVIDIA_API_KEY, "nvapi-from-settings", "tester")
    session.commit()
    assert store.resolve_ai_credentials(session).api_key == "nvapi-from-settings"
    assert store.describe_ai_config(session)["source"] == "settings"


def test_environment_takes_over_again_once_settings_are_cleared(
    session, clean_settings, monkeypatch
):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-from-environment")
    store.set_setting(session, store.NVIDIA_API_KEY, "nvapi-from-settings", "tester")
    session.commit()
    store.clear_setting(session, store.NVIDIA_API_KEY)
    session.commit()
    assert store.resolve_ai_credentials(session).api_key == "nvapi-from-environment"


def test_defaults_fill_in_the_url_and_model(session, clean_settings, monkeypatch):
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    creds = store.resolve_ai_credentials(session)
    assert creds.base_url == store.DEFAULT_BASE_URL
    assert creds.model == store.DEFAULT_MODEL


def test_a_trailing_slash_on_the_base_url_is_normalised(session, clean_settings):
    store.set_setting(session, store.NVIDIA_BASE_URL, "https://example.test/v1/", "t")
    session.commit()
    assert store.resolve_ai_credentials(session).base_url == "https://example.test/v1"


def test_unconfigured_is_reported_when_nothing_is_set(
    session, clean_settings, monkeypatch
):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr(store, "DEFAULT_NVIDIA_API_KEY", "")
    described = store.describe_ai_config(session)
    assert described["configured"] is False
    assert described["source"] == "none"
    assert described["key_hint"] == ""


def test_a_secret_value_is_kept_out_of_the_log(session, clean_settings, caplog):
    secret = "nvapi-do-not-log-this-value"
    with caplog.at_level("INFO"):
        store.set_setting(session, store.NVIDIA_API_KEY, secret, "tester")
    session.commit()
    assert secret not in caplog.text
    assert "value hidden" in caplog.text


def test_a_non_secret_value_may_be_logged(session, clean_settings, caplog):
    with caplog.at_level("INFO"):
        store.set_setting(session, store.NVIDIA_MODEL, "some/model", "tester")
    session.commit()
    assert "some/model" in caplog.text
