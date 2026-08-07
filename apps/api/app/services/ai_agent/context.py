"""What the model is told about the corpus before it is asked anything.

Without this, the first tool call of nearly every conversation is spent
discovering that the roll covers one constituency and six files. Putting the
shape of the data in the system prompt removes a round trip from most turns.

Cached, because it is read on every message and changes only when files are
processed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Set, Tuple

from sqlalchemy.orm import Session

from .guards import permitted_numbers, permitted_percentages

#: Long enough to save the repeated queries, short enough that a finished import
#: shows up while the operator is still looking at the screen.
_TTL_SECONDS = 60.0

_cached: Optional[Tuple[float, Dict[str, Any]]] = None


def roll_profile(session: Session, *, force: bool = False) -> Dict[str, Any]:
    """Counts and coverage, straight from `roll_overview`.

    Returns a shallow copy, not the cached dict itself: every cache hit inside
    the same 60-second window would otherwise hand out the same object, and a
    caller that annotates or mutates its copy (as a system-prompt builder is
    liable to do) would silently corrupt what every other concurrent request
    sees until the cache expires.
    """
    global _cached

    now = time.monotonic()
    if not force and _cached is not None and now - _cached[0] < _TTL_SECONDS:
        return dict(_cached[1])

    from .registry import execute
    from . import tools  # noqa: F401  (registers the tools)

    profile = execute(session, "roll_overview", {})
    _cached = (now, profile)
    return dict(profile)


def invalidate() -> None:
    """Drop the cache. Call after a file finishes processing."""
    global _cached
    _cached = None


def permitted_from_profile(profile: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """The numeric guard's seed for figures the backend itself injected.

    `profile_sentence` puts real counts (electors, files, pages, records,
    part numbers) into the system prompt to save a round trip -- but those
    counts never pass through a tool call, so `permitted_numbers`/
    `permitted_percentages` over `tool_results` alone would not contain them.
    Without this, a model that faithfully echoes the figure it was handed in
    its own system prompt gets that correct sentence discarded by the guard,
    which is worse than not injecting the profile at all: it is a true
    answer replaced by "I could not produce an answer I can stand behind."

    Deliberately not folded into `tool_results` itself: that list also drives
    the tool trace and citation collection, and the profile was not returned
    by a tool call the operator can see reflected in the trace. This is a
    parallel seed, unioned in by the caller, not a fake tool result.
    """
    return permitted_numbers([profile]), permitted_percentages([profile])


def profile_sentence(profile: Dict[str, Any]) -> str:
    """The profile as prose, for the system prompt.

    Prose rather than JSON: a small model reads a sentence more reliably than it
    reads a nested object, and this text is prepended to every single turn.
    """
    parts = profile.get("parts") or []
    constituencies = profile.get("constituencies") or []

    lines = [
        f"This workspace holds {profile.get('voters', 0):,} curated electors "
        f"from {profile.get('files', 0)} uploaded roll files "
        f"({profile.get('pages', 0)} pages, {profile.get('records', 0)} OCR records)."
    ]
    if constituencies:
        lines.append("Constituencies: " + ", ".join(str(c) for c in constituencies[:5]) + ".")
    if parts:
        shown = ", ".join(str(p) for p in parts[:10])
        total = profile.get("part_count", len(parts))
        lines.append(
            f"Parts covered ({total}): {shown}" + (", …" if total > 10 else "") + "."
        )
    return " ".join(lines)
