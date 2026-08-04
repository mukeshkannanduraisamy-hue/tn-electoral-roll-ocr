"""What makes an answer checkable.

`infographic.py` states the principle: a number the model typed cannot be
verified, so it must not reach the operator. That module enforced it against a
single chart payload. Here the same rule is enforced against every tool result
in the turn — which is what lets the assistant finally say "412 electors"
without letting it say "roughly 400".

Record references work the same way. The model cites electors as `[[v:<id>]]`
markers; a marker naming a record the tools did not return is removed before the
reply leaves the server. There are no hallucinated electors.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Set, Tuple

logger = logging.getLogger(__name__)

_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKER = re.compile(r"\[\[v:([A-Za-z0-9_-]{1,40})\]\]")


def _walk(value: Any) -> Iterable[Any]:
    """Every scalar anywhere inside a tool result."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
    else:
        yield value


def permitted_numbers(tool_results: List[Dict[str, Any]]) -> Set[str]:
    """Every numeric string the model is allowed to echo back.

    Generous within the results and closed outside them: a count may legitimately
    be quoted rounded, and an identifier such as an EPIC or a part code contains
    digits that are not claims about quantity.
    """
    allowed: Set[str] = set()
    for scalar in _walk(tool_results):
        if scalar is None or isinstance(scalar, bool):
            continue
        if isinstance(scalar, (int, float)):
            # `_DIGITS` (used below and in `strip_unverified_numbers`) has no
            # sign in its pattern, so it only ever extracts the unsigned run
            # out of prose -- "-20" in a sentence yields "20". A field that is
            # legitimately negative (`polling_station`'s and `count_mismatch`'s
            # `difference`) must therefore be permitted unsigned too, or a
            # correct sentence quoting it gets dropped as if invented.
            allowed.add(f"{float(scalar):g}".lstrip("-"))
            allowed.add(str(int(scalar)).lstrip("-"))
            allowed.add(str(int(scalar) + 1).lstrip("-"))  # a rate may round either way
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

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "id" in value and "epic" in value:
                found[str(value["id"])] = {
                    "id": str(value["id"]),
                    "epic": value.get("epic"),
                    "name": value.get("name"),
                    "part_number": value.get("part_number"),
                }
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

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
