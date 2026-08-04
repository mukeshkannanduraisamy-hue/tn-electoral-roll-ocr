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

#: A small, unambiguous set of cues that name a count or figure. Checked
#: *before* the how-to scan below: a message asking "how many X" wants a
#: number regardless of what else it mentions. This exists because phrase-
#: narrowing `_HOWTO_CUES`' export cue (see its docstring) only ever chases
#: the specific substring that happened to be reported broken -- "export to"
#: still matches mid-sentence in "how many voters are there in the export to
#: be reviewed", a count question that happens to say "export to", not a
#: how-to question that happens to count. A precedence rule closes the whole
#: class instead of the one substring: whatever _HOWTO_CUES grows to contain
#: in the future, a strong count cue still wins.
#:
#: Kept deliberately small and separate from the full _DATA_CUES scan below:
#: these are cues that essentially never appear in a genuine how-to question,
#: unlike _DATA_CUES' ordinary nouns ("voter", "part", "job", ...), which a
#: how-to phrasing could plausibly also use -- that is still why howto is
#: checked before the *full* _DATA_CUES scan, just not before this narrower
#: one.
_COUNT_CUES = (
    "how many", "count of", "total number",
    # Tamil: "how many"
    "எத்தனை",
)

#: Asking how to operate the workspace. Answered from the guide, not the data.
#:
#: "export" is deliberately a *phrase* here, not the bare word: "can i
#: export" / "export to" name an application action, but "how many verified
#: records would export?" and "how many voters are there in the export" are
#: count questions that merely mention the word -- the analytics tools can
#: answer those and the static guide cannot. A bare "export" cue outranked
#: the data-cue scan (this list is checked first) and sent all three of
#: those count questions to the canned guide. The phrase form still catches
#: "help me export to excel" (via "export to") without also catching a data
#: question that happens to use the word -- except mid-sentence, which is
#: what _COUNT_CUES above now closes instead of a further phrase tweak.
_HOWTO_CUES = (
    "how do i", "how to", "how can i", "where is", "where do i", "what does the",
    "can i export", "export to", "keyboard shortcut", "which button",
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

#: Closed vocabulary of words that, on their own, say nothing about the roll
#: or the app: greetings, acknowledgements, and the small grammatical words
#: that glue them together ("a lot", "to you", "very much"). Deliberately
#: small and closed: a word not in it is assumed to matter, which is what
#: keeps this from being a second, looser cue list.
#:
#: This replaces an earlier "opens with a greeting" prefix pattern, which was
#: itself wrong: reaching this point in `_heuristic` only means no cue word
#: matched anywhere in the message, and a real question can easily contain
#: none of the words in `_DATA_CUES`/`_HOWTO_CUES` — "hi, what's up with
#: 289?", "hi, tell me about the roll", "hi, is 289 done yet" all matched
#: the old prefix pattern on "hi" and returned smalltalk for a real question
#: about the corpus, wearing a courtesy opener, with nothing to tell the
#: operator it happened. Requiring *every* token to be a known pleasantry
#: routes all of those to `_is_pure_pleasantry` returning False instead, so
#: `_heuristic` returns `None` and `classify()` hands the message to the
#: model classifier (or the `data` default with no model configured) — the
#: safe direction, since an unclassifiable message becomes a slow, correct
#: answer, not a canned, fast, wrong one.
_PLEASANTRY_WORDS = frozenset(
    {
        "hi", "hii", "hello", "hey", "heyy", "yo", "greetings", "howdy", "sup",
        "thanks", "thank", "you", "thx", "ok", "okay", "k", "cool", "nice",
        "great", "awesome", "bye", "goodbye", "cheers", "good", "morning",
        "evening", "afternoon", "night", "day", "there", "a", "lot", "very",
        "much", "please", "welcome", "no", "worries", "to", "and", "my",
        "friend",
        # Tamil
        "வணக்கம்", "நன்றி",
    }
)

#: Punctuation stripped from each token's *edges* before the vocabulary
#: check — never characters internal to a token, which is what keeps a
#: Tamil word's combining marks attached to their base letter.
_TOKEN_EDGE_CHARS = " \t,.!?;:'\"()-"


def _tokenize(msg: str) -> tuple[str, ...]:
    """Split on whitespace and trim edge punctuation from each token.

    Not a `\\w+`-based tokenizer on purpose: `\\w` excludes combining marks
    (Unicode category Mn/Mc), so splitting a Tamil word like "வணக்கம்" on
    `\\w`/non-`\\w` boundaries would fragment it at its own internal virama
    and it would never match the whole-word vocabulary entry. Splitting on
    whitespace first and trimming only known punctuation from each token's
    edges leaves the combining marks exactly where they belong, wherever
    they land inside the word.
    """
    return tuple(t for t in (tok.strip(_TOKEN_EDGE_CHARS) for tok in msg.split()) if t)


def _is_pure_pleasantry(msg: str) -> bool:
    """True only if every token in the message is a known pleasantry."""
    tokens = _tokenize(msg)
    return bool(tokens) and all(tok in _PLEASANTRY_WORDS for tok in tokens)


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

    # A strong counting cue wins over the how-to scan below, unconditionally:
    # "how many voters are there in the export to be reviewed" is a count
    # question that happens to say "export to" (a howto cue), not a how-to
    # question that happens to count. See _COUNT_CUES for why this is a
    # separate, narrower check rather than another _HOWTO_CUES phrase tweak.
    if any(cue in msg for cue in _COUNT_CUES):
        return "data"

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
    # already returned if it did. Only treat this as smalltalk if the
    # message consists of nothing *but* pleasantries; a real question that
    # simply didn't happen to use a recognised cue word must fall through to
    # the model classifier below rather than be swallowed by a greeting.
    if _is_pure_pleasantry(msg):
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
