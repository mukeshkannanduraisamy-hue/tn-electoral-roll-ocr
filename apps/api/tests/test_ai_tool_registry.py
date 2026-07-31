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


def test_unusable_arguments_are_refused(sample_tool):
    with pytest.raises(registry.ToolError, match="Invalid arguments"):
        registry.execute(None, "_sample", {"n": "not a number"})


def test_compatible_arguments_are_coerced(sample_tool):
    # String "42" is coerced to int 42 because pydantic can do so successfully
    assert registry.execute(None, "_sample", {"n": "42"}) == {"doubled": 84}
    # Bool True is coerced to int 1
    assert registry.execute(None, "_sample", {"n": True}) == {"doubled": 2}


def test_non_string_tool_name_is_refused():
    with pytest.raises(registry.ToolError, match="Invalid tool name"):
        registry.execute(None, ["not", "a", "string"], {})


def test_catalogue_names_every_registered_tool(sample_tool):
    assert "_sample" in registry.describe_tools()
