"""Which tier answers this message.

Commit 1784600 bought a 0.44s reply by moving to a small model. That is worth
keeping, so a greeting or a "how do I export" never pays for a tool-calling
round trip. Only questions about the *data* enter the agent loop.

Heuristics decide first and decide most messages. A model call is spent only
when the heuristics are genuinely unsure, and if that call fails the message is
treated as a data question — answering slowly beats answering wrongly.
"""

from __future__ import annotations

import logging
import re
from typing import Literal, Optional

from ..app_settings import AiCredentials

logger = logging.getLogger(__name__)

Intent = Literal["smalltalk", "howto", "data"]


#: Asking about the roll's contents, its quality, or the pipeline's state.
_DATA_CUES = (
    "how many", "count", "total", "average", "percentage", "percent", "share",
    "breakdown", "distribution", "compare", "statistic", "stats", "summary",
    "chart", "graph", "infographic", "list", "find", "search", "show me",
    "who is", "who are", "which", "epic", "part ", "constituency", "household",
    "family", "house number", "verified", "unverified", "supplement",
    "confidence", "anomal", "duplicate", "failed", "error", "job", "page ",
    "polling station", "voter", "elector",
    # Tamil
    "எத்தனை", "சராசரி", "விளக்கப்படம்", "சுருக்கம்", "புள்ளிவிவரம்", "மொத்தம்",
    "வாரியாக", "வாரியான", "அடிப்படையில்", "வாக்காளர்", "பகுதி",
)

#: Asking how to operate the workspace. Answered from the guide, not the data.
_HOWTO_CUES = (
    "how do i", "how to", "how can i", "where is", "where do i", "what does the",
    "export", "keyboard shortcut", "which button",
    # Tamil. "எப்படி" is "how" and "எங்கே"/"எங்கு" is "where"; the roll's own
    # data cues never use these words (they use எத்தனை "how many", பகுதி
    # "part", etc.), so there is no overlap to arbitrate.
    "எப்படி", "எங்கே", "எங்கு",
)

#: A question about the assistant itself: what it is, what it can do, or a
#: bare request for help. Anchored at *both* ends, modulo trailing
#: whitespace/punctuation: the whole message has to be this question, not
#: merely mention it.
#:
#: This is checked first and unconditionally, ahead of every cue list,
#: because "who are you" is a smalltalk phrase in full while "who are" alone
#: is also a data cue ("who are the electors named..."); a substring check
#: would otherwise win on every greeting phrased as a question about the
#: assistant. Anchoring keeps the match narrow enough that it never eats a
#: real question merely because it opens with "who" or "what".
#:
#: "help" is its own alternative for the same reason it always was: "help",
#: "help me", and "help please" are a bare request for what the assistant can
#: do, but "help me export to excel" names an application action — this
#: pattern's end-anchor is exactly what keeps that message from matching
#: here, so it falls through to the how-to cues instead.
_SMALLTALK_SELF = re.compile(
    r"^\s*(who are you|what are you|what can you do|help(\s+me)?(\s+please)?)"
    r"[\s,.!?]*$",
    re.IGNORECASE,
)

#: A message that *opens* with a greeting or acknowledgement — "hi", "thanks",
#: "ok", a Tamil greeting — regardless of what follows.
#:
#: Deliberately *not* end-anchored. It only runs after both cue scans below
#: have already had a chance to claim the message, so by the time this is
#: reached the message contains no how-to or data cue; a courtesy opener
#: attached to nothing in particular ("hi there", "thanks a lot", "hi.
#: thanks.", "bye bye") is smalltalk regardless of its tail. Matching prefix-
#: only is what makes that correct; the previous end-anchored version treated
#: "hi there" as a failed match for a smalltalk pattern instead of a
#: successful match for "opens with a greeting", which is the actual rule.
#:
#: The lookahead after each alternative — end of string, or whitespace/
#: punctuation — stands in for `\b` on purpose. `\b` never worked for Tamil:
#: a word like "வணக்கம்" ends in a combining virama (Unicode category Mn),
#: which `\w` does not match, so the transition `\b` looks for right after
#: the word never exists and the Tamil alternatives would silently fail to
#: match at that boundary. Checking the literal next character instead of a
#: `\w`/non-`\w` transition sidesteps that: the virama is simply part of the
#: literal alternative text, and whatever comes after it (space, punctuation,
#: end of string) is what the lookahead inspects.
_GREETING_OPEN = re.compile(
    r"^\s*(good (morning|evening)|thank you|hi|hey|hello|yo|thanks|ok|okay|cool|"
    r"bye|வணக்கம்|நன்றி)(?=$|[\s,.!?])",
    re.IGNORECASE,
)

_CLASSIFY_PROMPT = (
    "Classify the user's message for an electoral-roll OCR workspace. Reply with "
    "exactly one word and nothing else:\n"
    "data — asks about the contents of the roll, record quality, or processing state\n"
    "howto — asks how to use the application\n"
    "smalltalk — a greeting, thanks, or a question about you\n"
)


def _heuristic(message: str) -> Optional[Intent]:
    msg = (message or "").strip().lower()
    if not msg:
        return "smalltalk"

    # Whether this message is a question about the assistant itself is
    # answered first and unconditionally — see _SMALLTALK_SELF for why it has
    # to run before the cue scans rather than after.
    if _SMALLTALK_SELF.match(msg):
        return "smalltalk"

    # "how do I filter by gender" is about the application even though it names
    # a dimension, so a how-to phrasing is checked, and wins, before data cues.
    if any(cue in msg for cue in _HOWTO_CUES):
        return "howto"

    # A data cue anywhere in the message wins next, regardless of how the
    # message opens: "hi, how many voters are there?" is a data question
    # wearing a courtesy greeting, not smalltalk. Ordering this ahead of the
    # greeting-open check below — rather than trying to out-anchor it — is
    # what keeps that message on the slow, correct path without also forcing
    # "hi there" onto it.
    if any(cue in msg for cue in _DATA_CUES):
        return "data"

    # Nothing here asked about the app or the data — both checks above
    # already returned if it did. A message that merely opens with a greeting
    # or acknowledgement is smalltalk regardless of what follows.
    if _GREETING_OPEN.match(msg):
        return "smalltalk"

    return None


def classify(message: str, creds: Optional[AiCredentials] = None) -> Intent:
    """Route one message. Falls back to the slow, correct path when unsure."""
    decided = _heuristic(message)
    if decided is not None:
        return decided

    if creds is None or not creds.configured:
        return "data"

    from ..nvidia_ai_service import _chat

    outcome = _chat(
        [
            {"role": "system", "content": _CLASSIFY_PROMPT},
            {"role": "user", "content": (message or "").strip()[:400]},
        ],
        creds,
        temperature=0.0,
        max_tokens=8,
    )
    word = (outcome.content or "").strip().lower()
    for intent in ("data", "howto", "smalltalk"):
        if intent in word:
            return intent  # type: ignore[return-value]

    logger.info("Router could not classify %r; treating as a data question", message[:60])
    return "data"
