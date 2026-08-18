"""Whether a field survived the DELETED stamp crossing it.

These checks answer "was this line damaged?", not "is this value plausible?".
The range check on age already covers plausibility, and it is exactly what a
stamped card defeats: `59` loses a digit, becomes `5`, and gets coerced to
unknown. The two other fields the stamp lands on are worse, because their
corruptions stay plausible -- `2-2` read as `22` is a perfectly valid house
number that happens to be wrong.

Confidence is no help here. The damaged age lines score 0.936-0.962, above the
0.710-0.837 the deletion marker itself scores, so a confidence gate would drop
the signal and keep the corruption.
"""

from __future__ import annotations

import re

# Tamil block. A digit butted straight against one of these is a digit the stamp
# fused into the following word.
_TAMIL_RE = re.compile(r"[஀-௿]")

_DIGIT_RUN_RE = re.compile(r"\d+")

# The gender label as OCR renders it on undamaged cards, including the variants
# the label matcher already tolerates. Absence means the stamp swallowed it.
_GENDER_LABEL_RE = re.compile(
    r"பாலினம|பாலினம்|பாலிளம்|பாலிணம்|பாலனம்|பாலின"
)


def age_gender_line_is_intact(text: str) -> bool:
    """True when the age digits and the gender label both came through clean.

    The stamp's diagonal enters this line between the digits and the label, so
    damage shows up as a digit run running straight into Tamil script.
    """
    match = _DIGIT_RUN_RE.search(text)
    if match is None:
        return False

    tail = text[match.end():]
    if tail[:1] and _TAMIL_RE.match(tail[:1]):
        return False

    return _GENDER_LABEL_RE.search(text) is not None


def house_number_is_intact(value: str) -> bool:
    """True when the value still carries the separator these rolls use.

    House numbers here look like `2-2`, `2/19`, `2-22A` or a bare `1`. The stamp
    eats the separator, turning `2-2` into `22` -- indistinguishable from a real
    `22` in isolation. So a bare multi-digit run is reported as *not verifiable*
    rather than wrong, and the stamp geometry decides whether it gets re-read.
    """
    stripped = value.strip()
    if not stripped:
        return False
    if "-" in stripped or "/" in stripped:
        return True
    return len(re.sub(r"\D", "", stripped)) <= 1
