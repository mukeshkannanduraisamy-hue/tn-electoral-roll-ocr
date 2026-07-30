"""Infographic builder: real aggregates over the voter table.

The point of this module is that **the language model never produces a number.**

A model asked for "a summary of the roll" will happily write plausible counts,
and no amount of "never invent numbers" in a system prompt prevents it. For an
electoral roll — a legal record — a confident wrong figure is worse than no
figure. So the division of labour is:

    the model  ->  picks a *spec* from the closed vocabulary below
                   ("voter_count", broken down by "gender", filtered to part 289")
    this module ->  validates that spec and runs the SQL that produces the values

Anything the model asks for that is not in ``METRICS``, ``DIMENSIONS`` or
``FILTERS`` is rejected rather than guessed at, so the payload the frontend
charts is always something SQLite actually counted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import Integer, case, func, select
from sqlalchemy.orm import Session

from ..db import VoterRow

logger = logging.getLogger(__name__)

#: Beyond this a bar chart stops being readable; the tail folds into "Other".
MAX_SERIES_POINTS = 12


class SpecError(ValueError):
    """The requested spec is not in the whitelist."""


# ---------------------------------------------------------------------------
# Metrics — what is being measured
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    #: "count" renders as an integer, "percent" as 0-100, "years" as a decimal.
    unit: str
    #: Builds the SQLAlchemy aggregate expression.
    expression: Callable[[], Any]
    description: str


#: No elector can be younger than this, so a lower figure is a mis-read rather
#: than a real age. Averaging it in drags the mean down and makes the "Unknown"
#: age band report a meaningless average, so it counts as unrecorded.
MIN_PLAUSIBLE_AGE = 18


def _verified_rate():
    # verified is stored as 0/1, so the mean is the rate.
    return func.round(func.avg(func.cast(VoterRow.verified, Integer)) * 100, 1)


def _plausible_age():
    return case((VoterRow.age >= MIN_PLAUSIBLE_AGE, VoterRow.age), else_=None)


METRICS: Dict[str, MetricDef] = {
    "voter_count": MetricDef(
        "voter_count", "Electors", "count", lambda: func.count(),
        "How many electors are on the roll.",
    ),
    "verified_count": MetricDef(
        "verified_count", "Verified electors", "count",
        lambda: func.sum(func.cast(VoterRow.verified, Integer)),
        "How many records a human has confirmed.",
    ),
    "unverified_count": MetricDef(
        "unverified_count", "Awaiting verification", "count",
        lambda: func.sum(1 - func.cast(VoterRow.verified, Integer)),
        "How many records still need review.",
    ),
    "verified_rate": MetricDef(
        "verified_rate", "Verified", "percent", _verified_rate,
        "Share of records confirmed by a human.",
    ),
    "average_age": MetricDef(
        "average_age", "Average age", "years",
        lambda: func.round(func.avg(_plausible_age()), 1),
        f"Mean age. Records with no age, or an age below {MIN_PLAUSIBLE_AGE}, "
        "are excluded as unreadable.",
    ),
    "supplement_count": MetricDef(
        "supplement_count", "Supplement electors", "count",
        lambda: func.sum(func.cast(VoterRow.is_supplement, Integer)),
        "Electors added by a supplement rather than the base roll.",
    ),
}


# ---------------------------------------------------------------------------
# Dimensions — how the measure is broken down
# ---------------------------------------------------------------------------

#: Matches the age bands already offered in the voters table UI, so a chart and
#: the quick filters above it never disagree about where 40 belongs.
AGE_BANDS: Tuple[Tuple[str, int, Optional[int]], ...] = (
    ("18-25", 18, 25),
    ("26-40", 26, 40),
    ("41-60", 41, 60),
    ("60+", 61, None),
)


def _age_band_expression():
    branches = []
    for label, low, high in AGE_BANDS:
        if high is None:
            branches.append((VoterRow.age >= low, label))
        else:
            branches.append(((VoterRow.age >= low) & (VoterRow.age <= high), label))
    return case(*branches, else_="Unknown")


@dataclass(frozen=True)
class DimensionDef:
    key: str
    label: str
    expression: Callable[[], Any]
    #: Fixed display order, when the categories are ordinal rather than ranked.
    order: Optional[Tuple[str, ...]] = None


DIMENSIONS: Dict[str, DimensionDef] = {
    "gender": DimensionDef("gender", "Gender", lambda: VoterRow.gender),
    "age_band": DimensionDef(
        "age_band", "Age band", _age_band_expression,
        order=tuple(b[0] for b in AGE_BANDS) + ("Unknown",),
    ),
    "part_number": DimensionDef("part_number", "Part", lambda: VoterRow.part_number),
    "constituency": DimensionDef("constituency", "Constituency", lambda: VoterRow.constituency),
    "relation_type": DimensionDef("relation_type", "Relation type", lambda: VoterRow.relation_type),
    "verified": DimensionDef(
        "verified", "Verification",
        lambda: case((VoterRow.verified.is_(True), "Verified"), else_="Unverified"),
        order=("Verified", "Unverified"),
    ),
    "is_supplement": DimensionDef(
        "is_supplement", "Roll type",
        lambda: case((VoterRow.is_supplement.is_(True), "Supplement"), else_="Main roll"),
        order=("Main roll", "Supplement"),
    ),
}


# ---------------------------------------------------------------------------
# Filters — narrowing the population. Mirrors the list endpoint's whitelist.
# ---------------------------------------------------------------------------

FILTERS: Dict[str, Callable[[Any], Any]] = {
    "gender": lambda v: VoterRow.gender == str(v),
    "relation_type": lambda v: VoterRow.relation_type == str(v),
    "part_number": lambda v: VoterRow.part_number == str(v),
    "constituency": lambda v: VoterRow.constituency == str(v),
    "house_number": lambda v: VoterRow.house_number.like(f"%{str(v).strip()}%"),
    "verified": lambda v: VoterRow.verified.is_(_as_bool(v)),
    "is_supplement": lambda v: VoterRow.is_supplement.is_(_as_bool(v)),
    "min_age": lambda v: VoterRow.age >= int(v),
    "max_age": lambda v: VoterRow.age <= int(v),
}

FILTER_LABELS: Dict[str, str] = {
    "gender": "Gender",
    "relation_type": "Relation type",
    "part_number": "Part",
    "constituency": "Constituency",
    "house_number": "House number",
    "verified": "Verified",
    "is_supplement": "Supplement",
    "min_age": "Age from",
    "max_age": "Age to",
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "y")


CHART_TYPES = ("stat", "bar", "column", "donut")


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


@dataclass
class InfographicSpec:
    metric: str
    dimension: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    chart_type: Optional[str] = None
    title: Optional[str] = None
    limit: int = MAX_SERIES_POINTS


def validate_spec(raw: Dict[str, Any]) -> InfographicSpec:
    """Coerce an untrusted spec into a known-safe one.

    Unknown filter keys are dropped with a warning rather than failing the whole
    request: a model that adds a stray key should still get its chart. An unknown
    *metric* is fatal, because there is no sensible substitute.
    """
    if not isinstance(raw, dict):
        raise SpecError("Specification must be an object")

    metric = str(raw.get("metric") or "").strip()
    if metric not in METRICS:
        raise SpecError(
            f"Unknown metric {metric!r}. Available: {', '.join(sorted(METRICS))}"
        )

    dimension = raw.get("dimension")
    dimension = str(dimension).strip() if dimension else None
    if dimension in ("", "none", "null", "None"):
        dimension = None
    if dimension is not None and dimension not in DIMENSIONS:
        raise SpecError(
            f"Unknown dimension {dimension!r}. Available: {', '.join(sorted(DIMENSIONS))}"
        )

    filters: Dict[str, Any] = {}
    for key, value in (raw.get("filters") or {}).items():
        if value in (None, "", "any", "all"):
            continue
        if key not in FILTERS:
            logger.info("Dropping unsupported infographic filter %r", key)
            continue
        filters[key] = value

    chart_type = str(raw.get("chart_type") or "").strip().lower() or None
    if chart_type not in CHART_TYPES:
        chart_type = None

    try:
        limit = int(raw.get("limit") or MAX_SERIES_POINTS)
    except (TypeError, ValueError):
        limit = MAX_SERIES_POINTS
    limit = max(1, min(limit, MAX_SERIES_POINTS))

    title = raw.get("title")
    return InfographicSpec(
        metric=metric,
        dimension=dimension,
        filters=filters,
        chart_type=chart_type,
        title=str(title).strip() if title else None,
        limit=limit,
    )


def _is_part_of_whole(metric: MetricDef) -> bool:
    """Whether the breakdown's parts sum to the total.

    Counts do. An average or a percentage does not — a donut of average ages
    implies the slices add up to something, which is false. Only a summable
    measure may use a part-of-whole form.
    """
    return metric.unit == "count"


def _default_chart_type(
    metric: MetricDef, dimension: Optional[str], point_count: int
) -> str:
    """Pick the form from the data's job, not from preference.

    No breakdown is a single headline, so it is a stat tile rather than a
    one-bar chart. An ordinal dimension reads left-to-right as columns. A small
    part-of-whole reads as a donut. Everything else is a ranked comparison,
    which is a horizontal bar — the labels here are Tamil names and part codes,
    and horizontal bars give them room without rotating text.
    """
    if dimension is None:
        return "stat"
    ordinal = DIMENSIONS[dimension].order is not None
    if not _is_part_of_whole(metric):
        return "column" if ordinal else "bar"
    if dimension == "age_band":
        return "column"
    if ordinal or point_count <= 3:
        return "donut"
    return "bar"


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _apply_filters(stmt, filters: Dict[str, Any]):
    for key, value in filters.items():
        try:
            stmt = stmt.where(FILTERS[key](value))
        except (TypeError, ValueError):
            logger.info("Ignoring infographic filter %r=%r: unusable value", key, value)
    return stmt


def build_infographic(session: Session, spec: InfographicSpec) -> Dict[str, Any]:
    """Run the spec and return a chart-ready payload of real values."""
    metric = METRICS[spec.metric]
    filters = spec.filters or {}

    # Population the figures describe, before any grouping.
    population = session.execute(
        _apply_filters(select(func.count()).select_from(VoterRow), filters)
    ).scalar_one()

    total_value = session.execute(
        _apply_filters(select(metric.expression()).select_from(VoterRow), filters)
    ).scalar_one()
    total_value = _clean_number(total_value)

    series: List[Dict[str, Any]] = []
    truncated_groups = 0

    if spec.dimension:
        dim = DIMENSIONS[spec.dimension]
        label_col = dim.expression()
        stmt = _apply_filters(
            select(label_col, metric.expression()).select_from(VoterRow), filters
        ).group_by(label_col)

        rows = session.execute(stmt).all()
        points = [
            {"label": _clean_label(label), "value": _clean_number(value)}
            for label, value in rows
            if _clean_number(value) is not None
        ]

        if dim.order:
            rank = {name: i for i, name in enumerate(dim.order)}
            points.sort(key=lambda p: (rank.get(p["label"], len(rank)), p["label"]))
        else:
            points.sort(key=lambda p: (-(p["value"] or 0), p["label"]))
            if len(points) > spec.limit:
                tail = points[spec.limit:]
                truncated_groups = len(tail)
                points = points[: spec.limit]
                # A count can be summed into "Other"; an average or a rate
                # cannot, so the tail is reported rather than mis-aggregated.
                if metric.unit == "count":
                    points.append(
                        {"label": "Other", "value": sum(p["value"] or 0 for p in tail)}
                    )

        # Shares only mean something when the parts add to the whole.
        share_base = sum(p["value"] or 0 for p in points) if metric.unit == "count" else 0
        for p in points:
            p["share"] = (
                round(100 * (p["value"] or 0) / share_base, 1) if share_base else None
            )
        series = points

    chart_type = spec.chart_type or _default_chart_type(metric, spec.dimension, len(series))
    # A stat tile cannot show a breakdown, and a breakdown chart needs one.
    if spec.dimension is None:
        chart_type = "stat"
    elif chart_type == "stat":
        chart_type = _default_chart_type(metric, spec.dimension, len(series))
    # Never honour a part-of-whole form for a measure whose parts do not sum.
    if chart_type == "donut" and not _is_part_of_whole(metric):
        chart_type = _default_chart_type(metric, spec.dimension, len(series))

    return {
        "title": spec.title or _default_title(metric, spec.dimension),
        "chart_type": chart_type,
        "metric": {
            "key": metric.key,
            "label": metric.label,
            "unit": metric.unit,
            "description": metric.description,
        },
        "dimension": (
            {"key": spec.dimension, "label": DIMENSIONS[spec.dimension].label}
            if spec.dimension
            else None
        ),
        "series": series,
        "total": total_value,
        "population": population,
        "highlights": _highlights(metric, series, total_value, population),
        "filters_applied": [
            {"key": k, "label": FILTER_LABELS.get(k, k), "value": str(v)}
            for k, v in filters.items()
        ],
        "truncated_groups": truncated_groups,
        "insights": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": (
            f"Aggregated by SQL over {population:,} elector "
            f"{'record' if population == 1 else 'records'}."
        ),
    }


def _clean_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number == int(number) else round(number, 1)


def _clean_label(label: Any) -> str:
    text = "" if label is None else str(label).strip()
    return text or "(not recorded)"


def _default_title(metric: MetricDef, dimension: Optional[str]) -> str:
    if dimension is None:
        return metric.label
    return f"{metric.label} by {DIMENSIONS[dimension].label.lower()}"


def _highlights(
    metric: MetricDef,
    series: List[Dict[str, Any]],
    total: Optional[float],
    population: int,
) -> List[Dict[str, Any]]:
    """The two or three figures worth reading first — computed, never written."""
    out: List[Dict[str, Any]] = [
        {"label": "Electors in scope", "value": population, "unit": "count"}
    ]
    if total is not None:
        out.append({"label": metric.label, "value": total, "unit": metric.unit})

    ranked = [p for p in series if p["value"] is not None]
    if ranked:
        top = max(ranked, key=lambda p: p["value"])
        out.append(
            {
                "label": f"Largest: {top['label']}",
                "value": top["value"],
                "unit": metric.unit,
                "share": top.get("share"),
            }
        )
    return out


def catalogue() -> Dict[str, Any]:
    """The vocabulary a model may choose from. Injected into its prompt."""
    return {
        "metrics": [
            {"key": m.key, "label": m.label, "unit": m.unit, "about": m.description}
            for m in METRICS.values()
        ],
        "dimensions": [{"key": d.key, "label": d.label} for d in DIMENSIONS.values()],
        "filters": sorted(FILTERS),
        "chart_types": list(CHART_TYPES),
    }
