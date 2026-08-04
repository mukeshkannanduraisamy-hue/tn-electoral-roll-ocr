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
