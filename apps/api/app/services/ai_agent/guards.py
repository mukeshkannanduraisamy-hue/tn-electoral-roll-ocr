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
cannot verify sign direction, comparison or attribution: `_DIGITS`, the
pattern used both to build the permitted set and to scan the reply, has no
minus sign in it, so it always extracts the unsigned magnitude out of prose
regardless of how the sentence is written. Given a tool result of
`{"difference": -20}` (twenty fewer than declared), both "20 fewer than
declared" and the false "20 more than declared" pass, because both quote the
same permitted magnitude, `20`. Whether a magnitude is real is checked; what a
sentence claims about it is not. Treat a pass as "this number is grounded",
never as "this sentence is true".

**How loose the "grounded" check actually is.** Every integer-valued scalar
also permits itself plus one, so a turn is not a small fixed allowlist -- it
is a moving window around every number any tool returned, and that window
compounds across every scalar in the turn. A `low_confidence_records` result
with 50 rows, each carrying a `min_confidence` and a `mean_confidence`, alone
contributes on the order of a hundred integers once each fraction's `+1`
slack is counted. Treat `permitted_numbers`/`permitted_percentages` as "not
obviously fabricated", not as "exactly matches something a tool returned" --
a model quoting an unrelated real-looking figure has a real chance of landing
on a permitted one by coincidence, especially in a turn with many rows.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Set, Tuple

logger = logging.getLogger(__name__)

_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKER = re.compile(r"\[\[v:([A-Za-z0-9_-]{1,40})\]\]")
#: A digit run counts as written-as-a-percentage only when a `%` (with
#: optional whitespace) immediately follows it in the source text -- "89.7%"
#: and "89.7 %" both qualify, "89.7" alone does not.
_PERCENT_TAIL = re.compile(r"\s*%")

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


def permitted_numbers(
    tool_results: List[Dict[str, Any]], user_prompt: str | None = None
) -> Set[str]:
    """Every plain numeric string the model is allowed to echo back.

    Generous within the results and closed outside them: a count may legitimately
    be quoted rounded, and an identifier such as an EPIC or a part code contains
    digits that are not claims about quantity. Also permits numbers explicitly
    provided in the user's prompt (e.g., part numbers, serial numbers, ages).
    """
    allowed: Set[str] = set()
    if user_prompt:
        for run in _DIGITS.findall(str(user_prompt)):
            allowed.add(run)
    for scalar in _walk(tool_results):
        if scalar is None or isinstance(scalar, bool):
            continue
        if isinstance(scalar, (int, float)):
            # `_DIGITS` (below and in `strip_unverified_numbers`) has no sign
            # in its pattern, so it only ever extracts the unsigned run out of
            # prose -- "-20" in a sentence yields "20", the same as "20"
            # alone would. Only the unsigned form needs to be permitted; a
            # signed form here could never change an accept/reject outcome.
            allowed.add(f"{float(scalar):g}".lstrip("-"))
            allowed.add(str(int(scalar)).lstrip("-"))
            allowed.add(str(int(scalar) + 1).lstrip("-"))  # a rate may round up
        else:
            for run in _DIGITS.findall(str(scalar)):
                allowed.add(run)
    return allowed


def permitted_percentages(tool_results: List[Dict[str, Any]]) -> Set[str]:
    """The x100 renderings of every 0..1 fraction, for text written as a percentage.

    `quality.py` stores confidence as a 0-1 float; a spoken answer naturally
    renders that as a percentage ("89.7%"), so the x100 form must be
    permitted somewhere. It is kept out of `permitted_numbers` and out of the
    unconditional match path in `strip_unverified_numbers` specifically
    because it is a large, coincidence-prone set -- a turn with many
    confidence scores in view permits a wide spread of integers 0-100 this
    way, and a bare count that happens to fall in that spread must not be
    let through just because a percentage would have been. Only offered as a
    candidate match when the digit run in the text is actually followed by
    `%`.
    """
    percentages: Set[str] = set()
    for scalar in _walk(tool_results):
        if isinstance(scalar, bool) or not isinstance(scalar, float):
            continue
        if 0.0 <= scalar <= 1.0:
            pct = round(scalar * 100, 1)
            percentages.add(f"{pct:g}")
            percentages.add(str(int(pct)))
            percentages.add(str(int(pct) + 1))  # rounds up too
    return percentages


def strip_unverified_numbers(
    text: str, allowed: Set[str], percentages: Set[str] = frozenset()
) -> Tuple[str, int]:
    """Drop any sentence quoting a figure no tool produced.

    The sentence goes whole rather than having the number edited out of it: a
    claim with its figure removed reads as though it were still supported.

    A digit run counts against `percentages` only when it is written in the
    text with a trailing `%` (see `_PERCENT_TAIL`) -- "89.7%" may match
    either set, but a bare "72" must match `allowed` on its own. Without that
    split, permitting every confidence score's x100 rendering unconditionally
    let a fabricated bare count survive purely because it happened to equal
    some unrelated confidence score rounded to a percentage; see
    `permitted_percentages`.
    """
    kept: List[str] = []
    dropped = 0
    for sentence in _SENTENCE.split(text or ""):
        candidate = sentence.strip()
        if not candidate:
            continue
        clean = candidate.replace(",", "")
        invented: List[str] = []
        for match in _DIGITS.finditer(clean):
            run = match.group(0)
            is_percentage = bool(_PERCENT_TAIL.match(clean, match.end()))
            permitted = (allowed | percentages) if is_percentage else allowed
            if run not in permitted:
                invented.append(run)
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
