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

# Why the elector was removed. Quoted from the legend the roll prints on its own
# final page:
#
#     E- Expired, S- Shifted, R-Repeated, M - Missing, Q- Disqualified
#
# Only these five. An earlier version of this map also carried `W - Withdrawn`,
# which appears nowhere on the roll; unlisted letters now fall through unnamed
# rather than being given an invented meaning.
REASON_MEANINGS = {
    "E": "Expired (இறந்தவர்)",
    "S": "Shifted (இடம் மாறியவர்)",
    "R": "Repeated (இரட்டைப் பதிவு)",
    "M": "Missing (காணாமல் போனவர்)",
    "Q": "Disqualified (தகுதியின்மை)",
}

# A trailing digit on the mark names the supplement that recorded the deletion,
# not a different reason. TAM-16 declares 226 deletions in துணைப்பட்டியல் 1 and 7
# in துணைப்பட்டியல் 2; extraction found exactly 226 `S` and 7 `S2`, so the digit
# tracks the supplement while the letter keeps its documented meaning.
_MARK_RE = re.compile(r"^([A-Z])(\d?)$")

# The whole box is the code, with no serial beside it. This is how the rolls
# usually print it, and it is the only reading under which a trailing digit is
# unambiguously part of the code rather than the serial.
_STANDALONE_RE = re.compile(r"^\s*\[?\s*([SERMQWsermqw]\d?)\s*\]?\s*$", re.UNICODE)

# A code sharing its box with the serial. The separator between them is optional
# because OCR closes it up: `S 576` comes back as `S576`.
#
# The trailing digit is only part of the code when a separator follows it. Left
# greedy it swallows the serial's first digit -- `S576` reads as code `S5`,
# serial 76, which is how elector KCY2607174 (TAM-26 page 23) came to be stored
# under a serial that appears nowhere on the card.
_CODE_RE = re.compile(
    r"^\s*\[?\s*([SERMQWsermqw](?:\d(?=[\s.\-:]))?)\s*[\.\-:\s]*\d", re.UNICODE
)

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

    A box holding nothing but the code is read first. `S2` on its own is the
    code entire; the same two characters in front of a serial are the letter
    `S` and the serial's leading digit, and only the absence of a serial tells
    the two apart.
    """
    standalone = _STANDALONE_RE.match(serial_text)
    if standalone:
        return standalone.group(1).upper()

    match = _CODE_RE.match(serial_text)
    if match is None:
        return None
    code = match.group(1).upper()
    return code


def describe_reason(code: str) -> str:
    """Why the elector was removed, and which supplement recorded it.

    A letter the legend does not list still strikes the elector off -- the stamp
    says so independently -- but naming it would put a guess in an audit trail,
    so it is reported unnamed instead.
    """
    match = _MARK_RE.match(code)
    if match is None:
        return f"{code} - Deleted (mark not recognised)"

    letter, supplement = match.group(1), match.group(2)
    meaning = REASON_MEANINGS.get(letter)
    if meaning is None:
        return f"{code} - Deleted (mark not recognised)"

    if supplement:
        return f"{code} - {meaning}, supplement {supplement}"
    return f"{code} - {meaning}"


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
