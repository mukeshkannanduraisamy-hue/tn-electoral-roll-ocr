"""Tests for the infographic builder.

The behaviour worth pinning down is that a language model cannot get a wrong
number in front of a user: the spec vocabulary is closed, and any figure the
model echoes back is checked against what SQL actually returned.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import VoterRow, session_scope  # noqa: E402
from app.services.infographic import (  # noqa: E402
    METRICS,
    SpecError,
    build_infographic,
    catalogue,
    validate_spec,
)
from app.services.nvidia_ai_service import (  # noqa: E402
    local_infographic_spec,
    strip_invented_numbers,
    wants_infographic,
)


#: A population with known composition, isolated in its own part so the
#: assertions stay exact whatever else is in the development database.
PART = f"TEST-{uuid.uuid4().hex[:8]}"
POPULATION = [
    # name,        age, gender,  verified
    ("Muthu",       72, "Male",   True),
    ("Kumar",       50, "Male",   False),
    ("Selvam",      48, "Male",   False),
    ("Kamala",      53, "Female", True),
    ("Divya",       25, "Female", False),
    ("Anonymous", None, "",       False),   # age never read
    ("Misread",      0, "Male",   False),   # age mis-read as zero
]
MALES = 4
FEMALES = 2
VERIFIED = 2
#: Ages a real elector could have. 0 is a mis-read, None was never read.
PLAUSIBLE_AGES = [age for _, age, _, _ in POPULATION if age is not None and age >= 18]


@pytest.fixture(scope="module")
def sample_part():
    """Insert the fixed population, yield its part number, then remove it.

    These tests run against the configured database, so they clean up after
    themselves — and sweep any rows a previously killed run left behind, which
    would otherwise skew every count asserted below.
    """
    ids = []
    with session_scope() as session:
        session.query(VoterRow).filter(
            VoterRow.part_number.like("TEST-%")
        ).delete(synchronize_session=False)
    with session_scope() as session:
        for name, age, gender, verified in POPULATION:
            row_id = uuid.uuid4().hex[:12]
            ids.append(row_id)
            session.add(
                VoterRow(
                    id=row_id,
                    epic=f"TST{uuid.uuid4().int % 10_000_000:07d}",
                    name=name,
                    age=age,
                    gender=gender,
                    verified=verified,
                    part_number=PART,
                    house_number="1-1",
                )
            )
    yield PART
    with session_scope() as session:
        session.query(VoterRow).filter(VoterRow.id.in_(ids)).delete(
            synchronize_session=False
        )


@pytest.fixture
def session():
    with session_scope() as s:
        yield s


def chart_for(session, part, **spec):
    spec.setdefault("metric", "voter_count")
    filters = dict(spec.pop("filters", {}))
    filters["part_number"] = part
    return build_infographic(session, validate_spec({**spec, "filters": filters}))


# --- Spec validation: the closed vocabulary ---------------------------------


def test_unknown_metric_is_rejected():
    with pytest.raises(SpecError) as exc:
        validate_spec({"metric": "salary"})
    assert "Unknown metric" in str(exc.value)
    # The error names the alternatives, so a retry can succeed.
    assert "voter_count" in str(exc.value)


def test_unknown_dimension_is_rejected():
    with pytest.raises(SpecError):
        validate_spec({"metric": "voter_count", "dimension": "photo_path"})


def test_missing_metric_is_rejected():
    with pytest.raises(SpecError):
        validate_spec({})
    with pytest.raises(SpecError):
        validate_spec({"dimension": "gender"})


def test_non_object_spec_is_rejected():
    with pytest.raises(SpecError):
        validate_spec("SELECT * FROM voters")


def test_unsupported_filters_are_dropped_not_honoured():
    """A model adding stray keys should still get its chart, minus the keys."""
    spec = validate_spec({
        "metric": "voter_count",
        "filters": {"gender": "Female", "notes": "x", "photo_path": "/etc/passwd"},
    })
    assert spec.filters == {"gender": "Female"}


def test_dimension_none_variants_all_mean_no_breakdown():
    for value in (None, "", "none", "null", "None"):
        assert validate_spec({"metric": "voter_count", "dimension": value}).dimension is None


def test_series_limit_is_clamped():
    assert validate_spec({"metric": "voter_count", "limit": 9999}).limit <= 12
    assert validate_spec({"metric": "voter_count", "limit": -4}).limit == 1
    assert validate_spec({"metric": "voter_count", "limit": "junk"}).limit == 12


def test_invalid_chart_type_falls_back_to_automatic():
    assert validate_spec({"metric": "voter_count", "chart_type": "pie3d"}).chart_type is None


def test_catalogue_lists_only_whitelisted_keys():
    cat = catalogue()
    assert set(m["key"] for m in cat["metrics"]) == set(METRICS)
    assert "photo_path" not in cat["filters"]


# --- Numeric guard: the model may not invent figures -----------------------


PAYLOAD = {
    "total": 3473,
    "population": 3473,
    "series": [
        {"label": "Male", "value": 1806, "share": 52.0},
        {"label": "Female", "value": 1665, "share": 47.9},
    ],
    "highlights": [{"label": "Electors in scope", "value": 3473}],
    "filters_applied": [],
}


def test_insight_quoting_a_real_figure_survives():
    kept, dropped = strip_invented_numbers(["Male electors number 1806 on this roll."], PAYLOAD)
    assert dropped == 0
    assert len(kept) == 1


def test_insight_quoting_an_invented_figure_is_discarded():
    kept, dropped = strip_invented_numbers(
        ["There are 9421 male electors, a clear majority."], PAYLOAD
    )
    assert kept == []
    assert dropped == 1


def test_thousands_separators_do_not_defeat_the_check():
    kept, _ = strip_invented_numbers(["The roll holds 3,473 electors."], PAYLOAD)
    assert len(kept) == 1
    kept, dropped = strip_invented_numbers(["The roll holds 5,000 electors."], PAYLOAD)
    assert kept == [] and dropped == 1


def test_percentages_may_be_quoted_rounded_either_way():
    for text in ("Males are 52% of the roll.", "Females are 47.9%.", "Females are 48%."):
        kept, _ = strip_invented_numbers([text], PAYLOAD)
        assert len(kept) == 1, text


def test_digits_inside_category_labels_are_allowed():
    payload = {
        "total": 3473,
        "population": 3473,
        "series": [{"label": "18-25", "value": 528, "share": 15.2}],
        "highlights": [],
        "filters_applied": [{"key": "part_number", "label": "Part", "value": "289"}],
    }
    kept, dropped = strip_invented_numbers(
        ["The 18-25 band is smallest in part 289."], payload
    )
    assert dropped == 0 and len(kept) == 1


def test_number_free_prose_always_survives():
    """The prompt asks for no figures, so the common case must never be dropped."""
    kept, dropped = strip_invented_numbers(
        ["Male electors outnumber female electors, though the gap is narrow.",
         "Verification has not started for this part and needs attention."],
        PAYLOAD,
    )
    assert dropped == 0 and len(kept) == 2


def test_blank_insights_are_skipped():
    kept, dropped = strip_invented_numbers(["", "   ", None], PAYLOAD)
    assert kept == [] and dropped == 0


# --- Routing ---------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    ["show me an infographic", "how many female voters?", "give me a summary",
     "gender breakdown please", "visual summary of part 289", "எத்தனை வாக்காளர்கள்?",
     # "X by Y" carries none of the cue words but is plainly a request for
     # figures, and it is the phrasing people reach for first.
     "voters by gender", "Voters by gender", "electors by part",
     "average age by part", "voters per constituency", "grouped by relation",
     "வாக்காளர்கள் பாலினம் வாரியாக"],
)
def test_statistical_questions_are_routed_to_a_chart(message):
    assert wants_infographic(message) is True


@pytest.mark.parametrize(
    "message",
    ["switch to dark theme", "how do I export to Excel?", "what does OCR mean?"],
)
def test_guidance_questions_are_not(message):
    assert wants_infographic(message) is False


def test_local_spec_matcher_always_yields_a_valid_spec():
    """The offline path must never produce something validate_spec rejects."""
    for message in (
        "how many voters", "gender breakdown", "average age by part",
        "verified percentage", "supplement electors", "unverified female voters",
        "something entirely unrelated", "", "சராசரி வயது",
    ):
        spec = validate_spec(local_infographic_spec(message))
        assert spec.metric in METRICS


@pytest.mark.parametrize(
    "message,expected",
    [
        ("how many voters in part 289", "289"),
        ("voters in part no. 4", "4"),
        ("summary of part number 286", "286"),
    ],
)
def test_local_matcher_filters_to_a_named_part(message, expected):
    spec = validate_spec(local_infographic_spec(message))
    assert spec.filters["part_number"] == expected
    # Naming one part and breaking down by part at once is contradictory.
    assert spec.dimension != "part_number"


@pytest.mark.parametrize(
    "message,metric,dimension",
    [
        # "age" is the measure here and "part" the breakdown; a plain word scan
        # reads the earlier "age" as the breakdown and gets it backwards.
        ("average age by part", "average_age", "part_number"),
        ("average age by gender", "average_age", "gender"),
        ("voter count by age band", "voter_count", "age_band"),
        ("verified rate per part", "verified_rate", "part_number"),
        ("voters grouped by relation", "voter_count", "relation_type"),
    ],
)
def test_local_matcher_reads_the_breakdown_not_the_measure(message, metric, dimension):
    spec = validate_spec(local_infographic_spec(message))
    assert (spec.metric, spec.dimension) == (metric, dimension)


def test_local_matcher_still_breaks_down_by_part_when_none_is_named():
    spec = validate_spec(local_infographic_spec("voter count by part"))
    assert spec.dimension == "part_number"
    assert "part_number" not in spec.filters


def test_local_matcher_defaults_to_the_headcount():
    spec = validate_spec(local_infographic_spec("tell me about the roll"))
    assert spec.metric == "voter_count"


# --- Execution against a real session --------------------------------------


def test_counts_match_the_known_population(session, sample_part):
    chart = chart_for(session, sample_part, dimension="gender")

    assert chart["population"] == len(POPULATION)
    assert chart["total"] == len(POPULATION)
    by_label = {p["label"]: p["value"] for p in chart["series"]}
    assert by_label["Male"] == MALES
    assert by_label["Female"] == FEMALES
    # An unrecorded gender is shown, not quietly dropped.
    assert by_label["(not recorded)"] == 1
    assert sum(by_label.values()) == chart["total"]
    assert chart["provenance"].startswith("Aggregated by SQL")


def test_no_dimension_renders_a_stat_tile(session, sample_part):
    chart = chart_for(session, sample_part)
    assert chart["chart_type"] == "stat"
    assert chart["series"] == []
    assert chart["total"] == len(POPULATION)


def test_verified_rate_is_computed_not_guessed(session, sample_part):
    chart = chart_for(session, sample_part, metric="verified_rate")
    assert chart["total"] == pytest.approx(100 * VERIFIED / len(POPULATION), abs=0.1)


def test_average_age_ignores_unreadable_ages(session, sample_part):
    """A missing age and an age mis-read as 0 are both absent data. Averaging a
    zero in would drag the mean below any real elector's age."""
    chart = chart_for(session, sample_part, metric="average_age")
    assert chart["total"] == pytest.approx(
        sum(PLAUSIBLE_AGES) / len(PLAUSIBLE_AGES), abs=0.1
    )
    # Everyone is still counted as in scope, including the unreadable records.
    assert chart["population"] == len(POPULATION)
    assert chart["total"] >= 18


def test_the_unknown_age_band_reports_no_average_rather_than_zero(session, sample_part):
    banded = chart_for(session, sample_part, metric="average_age", dimension="age_band")
    assert "Unknown" not in [p["label"] for p in banded["series"]]
    assert all((p["value"] or 0) >= 18 for p in banded["series"])

    # The same band still *counts* those electors — they exist, their age does not.
    counted = chart_for(session, sample_part, dimension="age_band")
    unknown = next(p for p in counted["series"] if p["label"] == "Unknown")
    assert unknown["value"] == 2  # the ageless record and the mis-read one


def test_a_non_summable_measure_never_uses_a_part_of_whole_form(session, sample_part):
    """Slices of an average do not add up to the whole, so a donut would lie —
    even when the model explicitly asks for one."""
    chart = chart_for(
        session, sample_part, metric="average_age", dimension="gender", chart_type="donut"
    )
    assert chart["chart_type"] != "donut"
    assert all(p["share"] is None for p in chart["series"])


def test_counts_carry_shares_that_sum_to_a_hundred(session, sample_part):
    chart = chart_for(session, sample_part, dimension="gender")
    shares = [p["share"] for p in chart["series"]]
    assert all(s is not None for s in shares)
    assert abs(sum(shares) - 100) < 0.5


def test_age_bands_keep_their_ordinal_order(session, sample_part):
    chart = chart_for(session, sample_part, dimension="age_band")
    labels = [p["label"] for p in chart["series"]]
    assert labels == sorted(labels, key=["18-25", "26-40", "41-60", "60+", "Unknown"].index)
    assert chart["chart_type"] == "column"


def test_filters_narrow_the_population(session, sample_part):
    everyone = chart_for(session, sample_part)
    females = chart_for(session, sample_part, filters={"gender": "Female"})

    assert everyone["population"] == len(POPULATION)
    assert females["population"] == FEMALES
    assert sorted(f["key"] for f in females["filters_applied"]) == ["gender", "part_number"]


def test_highlights_are_computed_from_the_series(session, sample_part):
    chart = chart_for(session, sample_part, dimension="gender")
    labels = [h["label"] for h in chart["highlights"]]
    assert "Electors in scope" in labels
    assert any(l.startswith("Largest:") for l in labels)
    largest = next(h for h in chart["highlights"] if h["label"].startswith("Largest:"))
    assert largest["value"] == MALES


def test_every_figure_in_the_payload_passes_its_own_numeric_guard(session, sample_part):
    """The guard must accept the payload it was built from, or honest commentary
    would be discarded as invented."""
    chart = chart_for(session, sample_part, dimension="gender")
    quoted = [f"There are {p['value']} in {p['label']}." for p in chart["series"]]
    kept, dropped = strip_invented_numbers(quoted, chart)
    assert dropped == 0
    assert len(kept) == len(quoted)
