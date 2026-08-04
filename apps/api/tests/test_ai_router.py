"""Routing decides which model answers, and therefore how fast the reply is.

The fast path exists because commit 1784600 measured it at 0.44s. A router that
sends "hi" into the agent loop throws that away, so the heuristics are tested
without any model configured — they must stand on their own.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.services.ai_agent import context, router  # noqa: E402


@pytest.mark.parametrize(
    "message",
    [
        "hello",
        "thanks!",
        "who are you",
        "வணக்கம்",
    ],
)
def test_conversational_messages_take_the_fast_path(message):
    assert router.classify(message) == "smalltalk"


@pytest.mark.parametrize(
    "message",
    [
        "how do I export to Excel?",
        "where is the column chooser",
        "how to mark a record verified",
    ],
)
def test_application_questions_take_the_fast_path(message):
    assert router.classify(message) == "howto"


@pytest.mark.parametrize(
    "message",
    [
        "how many voters are in part 289?",
        "voters by gender",
        "find electors named Muthu",
        "which pages failed OCR",
        "show me the household at house 12",
        "what is the average age",
        "list low confidence records",
        "எத்தனை வாக்காளர்கள் உள்ளனர்",
        "பாலினம் வாரியாக",
    ],
)
def test_data_questions_enter_the_agent_loop(message):
    assert router.classify(message) == "data"


def test_an_empty_message_is_not_a_data_question():
    assert router.classify("") == "smalltalk"


@pytest.mark.parametrize(
    "message",
    [
        # A bare Tamil greeting/thanks: the trailing character is a combining
        # virama or vowel sign (Unicode category Mn/Mc), which \b does not
        # treat as a word character, so a naive \b-anchored regex silently
        # fails to match here even though it matches the same words tested
        # above via test_conversational_messages_take_the_fast_path.
        "நன்றி!",
        "வணக்கம்.",
    ],
)
def test_tamil_greetings_match_with_trailing_punctuation(message):
    assert router.classify(message) == "smalltalk"


def test_bare_help_request_is_smalltalk():
    assert router.classify("help me") == "smalltalk"


def test_help_naming_an_application_action_is_not_smalltalk():
    # An operator asking for help doing something names the action, and that
    # should not be swallowed by the bare "help" greeting cue -- it is closer
    # to a how-to question than a request for the assistant's own capabilities.
    assert router.classify("help me export to excel") != "smalltalk"


@pytest.mark.parametrize(
    "message",
    [
        # A courtesy greeting in front of a real question is routine, and a
        # prefix-only smalltalk match let "hi" swallow the rest of the
        # message -- these all have to reach the data-cue scan, not stop at
        # the greeting.
        "hi, how many voters are there?",
        "hello, how many voters are there?",
        "hey how many parts are covered",
        "thanks, now show me duplicate records",
        "ok list low confidence records",
        "வணக்கம், எத்தனை வாக்காளர்கள் உள்ளனர்?",
    ],
)
def test_greeting_prefixed_data_questions_still_enter_the_agent_loop(message):
    assert router.classify(message) == "data"


@pytest.mark.parametrize(
    "message",
    [
        "எக்செல் ஏற்றுமதி செய்வது எப்படி",  # how to export to excel
        "பதிவை சரிபார்க்கப்பட்டதாக குறிக்க எப்படி",  # how to mark a record verified
        "பட்டன் எங்கே இருக்கிறது",  # where is the button
    ],
)
def test_tamil_application_questions_take_the_fast_path(message):
    assert router.classify(message) == "howto"


@pytest.mark.parametrize(
    "message, expected",
    [
        # --- data: a courtesy opener must not swallow a real question. ---
        # These two are exactly the round-1 regression: an end-anchored
        # smalltalk pattern let "hi"/"hello" match on their own and never
        # reached the data-cue scan for the rest of the message.
        ("hi, how many voters are there?", "data"),
        ("hello, how many voters are there?", "data"),
        ("hey how many parts are covered", "data"),
        ("thanks, now show me duplicate records", "data"),
        ("ok list low confidence records", "data"),
        ("வணக்கம், எத்தனை வாக்காளர்கள் உள்ளனர்?", "data"),
        ("how many voters are in part 289?", "data"),
        ("voters by gender", "data"),
        ("find electors named Muthu", "data"),
        ("which pages failed OCR", "data"),
        ("show me the household at house 12", "data"),
        ("what is the average age", "data"),
        ("list low confidence records", "data"),
        ("எத்தனை வாக்காளர்கள் உள்ளனர்", "data"),
        ("பாலினம் வாரியாக", "data"),
        # --- data: this is the round-3 "export" finding -- a bare "export"
        # cue in _HOWTO_CUES outranked the data-cue scan (howto is checked
        # first), so every one of these count questions that merely mentions
        # "export" was routed to the canned guide instead of the analytics
        # tools. Fixed by making the how-to cue a phrase ("can i export" /
        # "export to") instead of the bare word.
        ("how many verified records would export?", "data"),
        ("how many records are ready to export", "data"),
        ("how many voters are there in the export", "data"),
        # --- data: control group for the round-3 pure-pleasantry fix -- each
        # of these carries a greeting prefix but also a cue word (family,
        # part , job, part ), so they already routed correctly at review
        # time. Pinned here anyway: they prove the cue-scan path still works
        # for a greeting-prefixed message, so a future change that broke cue
        # matching in that position would be caught here, not just in the
        # "not smalltalk" list below.
        ("hey, what's going on with the Muthu family?", "data"),
        ("hi, what's the story with part 289", "data"),
        ("hi, is everything ok with the OCR job?", "data"),
        ("hi, anything odd about part 289", "data"),
        # --- data: round-4 finding -- "export to" (added in round 3 to fix
        # the bare-"export" bug) is a substring test, so it still matched
        # mid-sentence in a count question that happens to mention it. Fixed
        # with a precedence rule (_COUNT_CUES, checked before the how-to
        # scan) rather than narrowing the phrase again -- these two are the
        # exact messages that failed before that rule existed.
        ("how many voters are there in the export to be reviewed", "data"),
        ("how many records are in the export to Excel", "data"),
        # --- round-4 verification set from the coordinator, confirming the
        # new _COUNT_CUES precedence doesn't disturb genuine how-to intent
        # even when it's adjacent to an export phrase, and that a bare count
        # question with no export wording still lands on data. ("help me
        # export to excel" and "எத்தனை வாக்காளர்கள் உள்ளனர்" are already
        # pinned above under round 2/round 0->1 respectively, so they are
        # not repeated here.)
        ("how do i export to excel", "howto"),
        ("can i export the duplicates", "howto"),
        ("how many verified records", "data"),
        ("how many records would export", "data"),
        # --- smalltalk: the round-2 overshoot list -- a greeting or
        # acknowledgement with a tail must still land as smalltalk once the
        # pattern stopped being end-anchored. ---
        ("hi there", "smalltalk"),
        ("hi, thanks", "smalltalk"),
        ("hi. thanks.", "smalltalk"),
        ("hi hi", "smalltalk"),
        ("hello hello", "smalltalk"),
        ("thanks a lot", "smalltalk"),
        ("thank you very much", "smalltalk"),
        ("ok thanks", "smalltalk"),
        ("bye bye", "smalltalk"),
        ("good morning to you", "smalltalk"),
        # --- smalltalk: this is the round-0 regression -- "who are" is a
        # data cue, so this only stays smalltalk because the about-the-
        # assistant pattern is checked first and unconditionally. ---
        ("who are you", "smalltalk"),
        ("what can you do", "smalltalk"),
        ("help", "smalltalk"),
        ("வணக்கம்", "smalltalk"),
        ("நன்றி", "smalltalk"),
        ("வணக்கம்.", "smalltalk"),
        ("நன்றி!", "smalltalk"),
        ("வணக்கம் ", "smalltalk"),
        ("நன்றி ", "smalltalk"),
        # --- howto ---
        ("how do I export to Excel?", "howto"),
        ("where is the column chooser", "howto"),
        ("how to mark a record verified", "howto"),
        ("எக்செல் ஏற்றுமதி செய்வது எப்படி", "howto"),
        ("பதிவை சரிபார்க்கப்பட்டதாக குறிக்க எப்படி", "howto"),
        ("பட்டன் எங்கே இருக்கிறது", "howto"),
        ("help me export to excel", "howto"),
    ],
)
def test_router_precedence_handles_both_directions_at_once(message, expected):
    # Round 0->1 and round 1->2 each fixed one direction and broke the other.
    # This table holds every message that mattered to either regression, plus
    # the original data/howto rows, so a future change has to satisfy all of
    # them together.
    assert router.classify(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        # Round 3: the round-2 fix used an "opens with a greeting" prefix
        # check for step 4, but reaching step 4 only means no cue word
        # matched -- which is routine for a real question phrased without
        # one. Every one of these is a genuine question about the corpus
        # wearing a courtesy opener, with no _DATA_CUES/_HOWTO_CUES word in
        # it, so the prefix check swallowed all of them as smalltalk. Fixed
        # by requiring the *whole* message to be nothing but pleasantries
        # (_is_pure_pleasantry) rather than merely opening with one.
        #
        # These assert != "smalltalk" rather than a specific intent: with no
        # credentials configured in this test module, an unclassified
        # message falls through _heuristic's None to classify()'s "data"
        # default -- pinning that exact fallback value would make the test
        # about classify()'s fallback behaviour instead of about the router
        # never mistaking these for smalltalk, which is the actual bug.
        "hi, what's up with 289?",
        "hello, anything strange in the last upload?",
        "hi, can you tell me about record 4521?",
        "thanks, and what about house 12?",
        "hi, tell me about the roll",
        "hi, can you check on Muthu for me",
        "hi, is 289 done yet",
        # These three arrived after the coordinator noticed their message
        # said "10 of 14" but only pasted 7 rows -- same failure mode as the
        # rows above (a real question, no cue word, greeting prefix).
        "hello, what's in this workspace",
        "hey what's wrong with the last file",
        "hello there, what's new",
    ],
)
def test_courtesy_prefixed_real_questions_are_not_smalltalk(message):
    assert router.classify(message) != "smalltalk"


def test_roll_profile_reports_the_shape_of_the_corpus():
    with session_scope() as s:
        profile = context.roll_profile(s)
    for key in ("voters", "files", "parts", "constituencies"):
        assert key in profile


def test_roll_profile_cache_hits_do_not_share_a_mutable_object():
    # Task 11 will annotate/build on top of this dict; if two calls inside
    # the same 60s window returned the identical object, a caller mutating
    # its copy would corrupt what every other concurrent request sees.
    with session_scope() as s:
        first = context.roll_profile(s)
        first["voters"] = "tampered"
        second = context.roll_profile(s)
    assert second["voters"] != "tampered"


def test_profile_sentence_is_prose_not_json():
    sentence = context.profile_sentence(
        {"voters": 3473, "files": 6, "parts": ["289"], "constituencies": ["Test"], "part_count": 1}
    )
    assert "3473" in sentence or "3,473" in sentence
    assert "{" not in sentence
