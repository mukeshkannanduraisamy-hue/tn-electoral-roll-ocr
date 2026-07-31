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
