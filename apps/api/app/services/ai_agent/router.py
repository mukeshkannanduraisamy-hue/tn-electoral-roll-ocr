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
    "can i export", "keyboard shortcut", "which button",
    # Tamil. "எப்படி" is "how" and "எங்கே"/"எங்கு" is "where"; the roll's own
    # data cues never use these words (they use எத்தனை "how many", பகுதி
    # "part", etc.), so there is no overlap to arbitrate.
    "எப்படி", "எங்கே", "எங்கு",
)

#: A greeting, thanks, or a question about the assistant itself.
#:
#: Anchored at *both* ends, modulo trailing whitespace/punctuation: the whole
#: message has to be the greeting, not merely start with one. A prefix-only
#: match let "hi, how many voters are there?" match on "hi" and return
#: smalltalk for what is really a data question with a courtesy opener —
#: exactly the failure mode this router exists to avoid, since it would
#: answer a real question from the canned offline guide with no sign to the
#: operator that it happened. Requiring the full message (sans trailing
#: punctuation) keeps "hi"/"hi!"/"who are you?" matching while "hi, how many
#: voters are there?" falls through to the data-cue scan below.
#:
#: This also replaces the old `\b`-based boundary, which never worked for
#: Tamil in the first place: a word like "வணக்கம்" ends in a combining virama
#: (Unicode category Mn), which `\w` does not match, so `\b` never found a
#: word/non-word transition there and the Tamil alternatives silently never
#: matched. End-anchoring against literal trailing punctuation/whitespace
#: sidesteps that; it never needs to ask whether a character is "a word
#: character".
#:
#: "help" is its own alternative for the same reason it always was: "help",
#: "help me", and "help please" are a bare request for what the assistant can
#: do, but "help me export to excel" names an application action and must
#: fall through to the how-to cues instead of being swallowed here.
_SMALLTALK = re.compile(
    r"^\s*(hi|hey|hello|yo|thanks|thank you|ok|okay|cool|bye|good (morning|evening)|"
    r"who are you|what are you|what can you do|வணக்கம்|நன்றி)[\s,.!?]*$"
    r"|^\s*help\s*(me)?\s*(please)?\s*[!.?]*\s*$",
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

    # "how do I filter by gender" is about the application even though it names
    # a dimension, so a how-to phrasing is checked, and wins, before data cues.
    if any(cue in msg for cue in _HOWTO_CUES):
        return "howto"

    # Checked before the data cues, not after: "who are you" is a smalltalk
    # phrase in full, but "who are" alone is also a data cue ("who are the
    # electors named..."), and the substring check would otherwise win on
    # every greeting phrased as a question about the assistant.
    if _SMALLTALK.match(msg):
        return "smalltalk"

    if any(cue in msg for cue in _DATA_CUES):
        return "data"

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
