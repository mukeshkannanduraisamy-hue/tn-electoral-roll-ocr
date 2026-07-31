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
