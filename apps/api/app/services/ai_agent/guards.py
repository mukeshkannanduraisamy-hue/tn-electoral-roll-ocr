"""What makes an answer checkable.

`infographic.py` states the principle: a number the model typed cannot be
verified, so it must not reach the operator. That module enforced it against a
single chart payload. Here the same rule is enforced against every tool result
in the turn — which is what lets the assistant finally say "412 electors"
without letting it say "roughly 400".

Record references work the same way. The model cites electors as `[[v:<id>]]`
markers; a marker naming a record the tools did not return is removed before the
reply leaves the server. There are no hallucinated electors.

**What this guard does not verify.** `strip_unverified_numbers` checks that a
*magnitude* in the reply also appears somewhere in a tool result. It does not
check that the *claim* built around that magnitude is true. In particular it
cannot verify sign direction, comparison or attribution: given a tool result
of `{"difference": -20}` (twenty fewer than declared), both "20 fewer than
declared" and the false "20 more than declared" pass, because both quote the
same permitted magnitude, `20`. Whether a magnitude is real is checked; what a
sentence claims about it is not. Treat a pass as "this number is grounded",
never as "this sentence is true".
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Set, Tuple

logger = logging.getLogger(__name__)

_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKER = re.compile(r"\[\[v:([A-Za-z0-9_-]{1,40})\]\]")

#: Tool results are ordinary JSON-shaped data, a handful of levels deep at
#: most. A cap well below Python's default recursion limit turns a
#: pathologically deep or self-referential structure into "stop descending"
#: instead of an unhandled `RecursionError` reaching the caller.
_MAX_DEPTH = 100


def _walk(value: Any, _depth: int = 0) -> Iterable[Any]:
    """Every scalar anywhere inside a tool result."""
    if _depth > _MAX_DEPTH:
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item, _depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item, _depth + 1)
    else:
        yield value


def permitted_numbers(tool_results: List[Dict[str, Any]]) -> Set[str]:
    """Every numeric string the model is allowed to echo back.

    Generous within the results and closed outside them: a count may legitimately
    be quoted rounded, and an identifier such as an EPIC or a part code contains
    digits that are not claims about quantity.

    This only ever verifies a magnitude, never the claim wrapped around it.
    Both the signed and unsigned forms of a number are permitted (`-20` and
    `20`), because `_DIGITS` extracts the unsigned run out of prose and a
    correct sentence may write either ("20 fewer than declared" or "-20").
    That also means a sentence that flips the sign -- "20 more" instead of "20
    fewer" -- is not caught here: sign *direction as a claim* is prose, not a
    digit, and this guard cannot check it. See the module docstring.
    """
    allowed: Set[str] = set()
    for scalar in _walk(tool_results):
        if scalar is None or isinstance(scalar, bool):
            continue
        if isinstance(scalar, (int, float)):
            for candidate in (f"{float(scalar):g}", str(int(scalar)), str(int(scalar) + 1)):
                allowed.add(candidate)  # signed, e.g. "-20"
                allowed.add(candidate.lstrip("-"))  # unsigned, e.g. "20"
            if isinstance(scalar, float) and 0.0 <= scalar <= 1.0:
                # Confidence scores are stored as 0-1 fractions
                # (`ocr_quality`'s and `low_confidence_records`' mean/min
                # confidence) but are naturally spoken as percentages, so the
                # x100 rendering is permitted alongside the raw fraction --
                # both the one-decimal form ("89.7") and the rounded integer
                # ("90"), with the same round-either-way slack as elsewhere.
                pct = round(scalar * 100, 1)
                allowed.add(f"{pct:g}")
                allowed.add(str(int(pct)))
                allowed.add(str(int(pct) + 1))
        else:
            for run in _DIGITS.findall(str(scalar)):
                allowed.add(run)
    return allowed


def strip_unverified_numbers(text: str, allowed: Set[str]) -> Tuple[str, int]:
    """Drop any sentence quoting a figure no tool produced.

    The sentence goes whole rather than having the number edited out of it: a
    claim with its figure removed reads as though it were still supported.
    """
    kept: List[str] = []
    dropped = 0
    for sentence in _SENTENCE.split(text or ""):
        candidate = sentence.strip()
        if not candidate:
            continue
        invented = [
            run for run in _DIGITS.findall(candidate.replace(",", "")) if run not in allowed
        ]
        if invented:
            dropped += 1
            logger.warning(
                "Discarded an assistant sentence quoting unverified figures %s: %r",
                invented, candidate,
            )
            continue
        kept.append(candidate)
    return " ".join(kept), dropped


def collect_citations(tool_results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Every elector the tools actually returned, keyed by id.

    A mapping counts as a citable record when it carries both `id` and `epic`.
    That is the contract the elector tools honour, and it means a new tool
    becomes citable simply by returning rows in the same shape.
    """
    found: Dict[str, Dict[str, Any]] = {}

    def visit(value: Any, depth: int = 0) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(value, dict):
            if "id" in value and "epic" in value:
                found[str(value["id"])] = {
                    "id": str(value["id"]),
                    "epic": value.get("epic"),
                    "name": value.get("name"),
                    "part_number": value.get("part_number"),
                }
            for item in value.values():
                visit(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, depth + 1)

    visit(tool_results)
    return found


def bind_citations(
    text: str, known: Dict[str, Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]]]:
    """Keep markers naming a returned record; delete the rest."""
    cited: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def replace(match: "re.Match[str]") -> str:
        voter_id = match.group(1)
        record = known.get(voter_id)
        if record is None:
            logger.warning("Stripped a citation to an unknown record %r", voter_id)
            return ""
        if voter_id not in seen:
            seen.add(voter_id)
            cited.append(record)
        return match.group(0)

    bound = _MARKER.sub(replace, text or "")
    return re.sub(r"[ \t]{2,}", " ", bound).strip(), cited
