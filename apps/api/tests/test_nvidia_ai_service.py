"""Unit tests for NVIDIA AI LLM Service (z-ai/glm-5.2)."""

import pytest
from app.services.nvidia_ai_service import query_nvidia_copilot, _local_rule_fallback


def test_local_rule_fallback_theme():
    res = _local_rule_fallback("Switch to Emerald theme")
    assert "reply" in res
    assert res["ui_changes"].get("theme") == "emerald"


def test_local_rule_fallback_filters():
    res = _local_rule_fallback("Show female voters 18-25")
    assert "reply" in res
    filters = res["ui_changes"].get("filters", {})
    assert filters.get("gender") == "Female"
    assert filters.get("minAge") == "18"
    assert filters.get("maxAge") == "25"


def test_query_nvidia_copilot_empty():
    res = query_nvidia_copilot("")
    assert "Please enter a message" in res["reply"]
