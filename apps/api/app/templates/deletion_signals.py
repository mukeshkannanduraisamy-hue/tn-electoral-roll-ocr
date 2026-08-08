"""The two signals that mark an elector struck off, and how they combine.

A Special Intensive Revision roll records a deletion twice: a reason-code letter
prefixing the serial number, and a diagonal DELETED stamp across the card. On the
page this was built against the two agreed on every card, which is what makes
them worth keeping separate -- a disagreement is a defect in one of the readers,
and collapsing them into a single boolean throws that evidence away.

Either signal alone is sufficient. That choice favours recall over precision, so
a misread letter can strike off a living elector; `signals` exists so such a case
can be found after the fact rather than being indistinguishable from a real one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Codes the Election Commission documents for a Special Intensive Revision.
REASON_MEANINGS = {
    "S": "S - Shifted (இடம் மாறியவர்)",
    "E": "E - Expired (இறந்தவர்)",
    "R": "R - Repeated (இரட்டைப் பதிவு)",
    "M": "M - Missing (காணாமல் போனவர்)",
    "Q": "Q - Disqualified (தகுதியின்மை)",
    "W": "W - Withdrawn (விலக்கப்பட்டவர்)",
}

# A code is a documented letter, optionally carrying a digit -- serial 25 reads
# `S2`, the only such case observed, and its meaning is not known.
_CODE_RE = re.compile(r"^\s*\[?\s*([SERMQWsermqw]\d?)\s*[\.\-:\s]+\d", re.UNICODE)

_DELETIONS_PAGE_REASON = "நீக்கல் பட்டியல் (Deletions List)"
_STAMP_REASON = "DELETED (stamp)"


@dataclass(frozen=True)
class DeletionVerdict:
    is_deleted: bool
    reason: str
    signals: tuple[str, ...]
    """Which readers fired: `reason_code`, `stamp`, `deletions_page`."""

    @property
    def flag(self) -> str:
        """The stored value.

        Always written, including `"No"`. Writing only on `"Yes"` -- what the
        template used to do -- makes an evaluated live elector and a cell nothing
        ever looked at indistinguishable, and every one of the 632 records in the
        historical database sits in that ambiguous state.
        """
        return "Yes" if self.is_deleted else "No"


def parse_reason_code(serial_text: str) -> str | None:
    """The reason code prefixing a serial, or None when there is none.

    Case is not evidence: this is the lowest-confidence line on a stamped card
    (0.710-0.837), so a lowercase read is a recognition artefact, not a different
    code.
    """
    match = _CODE_RE.match(serial_text)
    if match is None:
        return None
    code = match.group(1).upper()
    return code


def describe_reason(code: str) -> str:
    """The code's documented meaning, or the code itself when unmapped.

    An unknown code still marks the elector deleted -- the stamp says so too --
    but inventing a meaning for it would put a guess in an audit trail.
    """
    known = REASON_MEANINGS.get(code)
    if known:
        return known
    return f"{code} - Deleted (code not documented)"


def assess_deletion(
    reason_code: str | None,
    stamp_found: bool,
    on_deletions_page: bool = False,
) -> DeletionVerdict:
    """Combine the signals for one cell.

    `on_deletions_page` is context, never a verdict of its own: a page can carry
    deleted and live electors side by side (15 of 30 on the page measured), so a
    page-level flag that decided the outcome would strike off every live elector
    sharing it.
    """
    signals: list[str] = []
    if reason_code:
        signals.append("reason_code")
    if stamp_found:
        signals.append("stamp")

    is_deleted = bool(reason_code) or stamp_found
    if is_deleted and on_deletions_page:
        signals.append("deletions_page")

    if reason_code:
        reason = describe_reason(reason_code)
    elif stamp_found:
        reason = _STAMP_REASON
    elif on_deletions_page:
        reason = ""
    else:
        reason = ""

    if is_deleted and on_deletions_page and not reason:
        reason = _DELETIONS_PAGE_REASON

    return DeletionVerdict(
        is_deleted=is_deleted, reason=reason, signals=tuple(signals)
    )
