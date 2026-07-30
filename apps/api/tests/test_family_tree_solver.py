"""Unit tests for Senior Data Engineer & Genealogy Expert Family Tree Solver Engine."""

import pytest
from app.services.family_tree_solver import (
    building_key,
    calculate_relationship_confidence,
    clean_name,
    fuzzy_match_names,
    get_confidence_level,
    is_missing_house,
    normalise_house,
    resolve_family_trees,
    validate_relationship,
)


def voter(vid, name, age=None, gender="", rel_type="", rel_name="", house="5-177", serial=None):
    """Build a voter dict with only the fields the solver reads."""
    return {
        "id": vid,
        "name": name,
        "relation_type": rel_type,
        "relation_name": rel_name,
        "age": age,
        "gender": gender,
        "house_number": house,
        "serial": serial,
        "epic": f"EPIC-{vid}",
    }


def only_family(voters):
    """Resolve and assert a single family came back, returning it."""
    trees = resolve_family_trees(voters)
    assert len(trees) == 1, [t["family_id"] for t in trees]
    return trees[0]


def find_family(trees, member_name):
    return next(t for t in trees if any(m["name"] == member_name for m in t["members"]))


def test_clean_name_normalization():
    assert clean_name("1. பெயர் : சுசீலா") == "சுசீலா"
    assert clean_name("4. கணவர் பெயர் : சண்முகம்") == "சண்முகம்"
    assert clean_name("5-177") == "5-177"


def test_fuzzy_name_matching():
    matched, score = fuzzy_match_names("சண்முகம்", "சண்முகம்")
    assert matched is True
    assert score == 1.0

    matched_ocr, score_ocr = fuzzy_match_names("சண்முகம்", "சணமுகம")
    assert matched_ocr is True
    assert score_ocr >= 0.78


def test_confidence_scoring_matrix():
    assert get_confidence_level(98) == "Confirmed"
    assert get_confidence_level(85) == "Strong"
    assert get_confidence_level(70) == "Possible"
    assert get_confidence_level(50) == "Unverified"


def test_resolve_family_trees_multi_generational():
    sample_voters = [
        voter("v1", "Muthu", 72, "Male", serial=1),
        voter("v2", "Kumar", 50, "Male", "Father", "Muthu", serial=2),
        voter("v3", "Selvam", 48, "Male", "Father", "Muthu", serial=3),
        voter("v4", "Ravi", 28, "Male", "Father", "Kumar", serial=4),
    ]

    fam = only_family(sample_voters)

    assert fam["family_head"] == "Muthu"
    assert fam["house_number"] == "5-177"
    assert fam["confidence"] >= 95
    assert fam["confidence_level"] == "Confirmed"
    assert "Muthu (72)" in fam["ascii_tree"]
    assert "Kumar (50)" in fam["ascii_tree"]
    assert "Ravi (28)" in fam["ascii_tree"]

    # Ravi hangs under Kumar, not directly under Muthu.
    assert fam["generation_count"] == 3
    by_name = {m["name"]: m for m in fam["members"]}
    assert by_name["Ravi"]["generation_level"] == 3
    assert by_name["Ravi"]["parent_ids"] == ["v2"]


# --- Hard gates: contradictions must be rejected, not scored -----------------


def test_parent_younger_than_18_year_gap_is_rejected():
    """A 'father' two years older than his child is impossible, not 90% likely."""
    trees = resolve_family_trees([
        voter("a", "Raman", 32, "Male", serial=1),
        voter("b", "Devi", 30, "Female", "Father", "Raman", serial=2),
    ])

    # No edge survives, so the household fragments into two lone residents.
    assert all(t["relationships"] == [] for t in trees)

    devi = find_family(trees, "Devi")
    assert devi["confidence"] == 0
    assert devi["confidence_level"] == "Unverified"
    assert devi["unresolved_reason"] == "contradicted"
    assert "at least 18 years older" in devi["rejected_links"][0]["reason"]


def test_female_named_as_husband_is_rejected():
    trees = resolve_family_trees([
        voter("a", "Devi", 30, "Female", serial=1),
        voter("b", "Meena", 29, "Female", "Husband", "Devi", serial=2),
    ])

    assert all(t["relationships"] == [] for t in trees)
    meena = find_family(trees, "Meena")
    assert "female but named as a husband" in meena["rejected_links"][0]["reason"]


def test_male_declaring_a_husband_is_rejected():
    trees = resolve_family_trees([
        voter("a", "Shanmugam", 60, "Male", serial=1),
        voter("b", "Murugan", 58, "Male", "Husband", "Shanmugam", serial=2),
    ])

    assert all(t["relationships"] == [] for t in trees)
    assert "male but declares a husband" in find_family(trees, "Murugan")["rejected_links"][0]["reason"]


def test_implausible_spouse_age_gap_is_rejected():
    trees = resolve_family_trees([
        voter("a", "Shanmugam", 80, "Male", serial=1),
        voter("b", "Suseela", 22, "Female", "Husband", "Shanmugam", serial=2),
    ])

    assert all(t["relationships"] == [] for t in trees)
    assert "plausibility limit" in find_family(trees, "Suseela")["rejected_links"][0]["reason"]


def test_male_named_as_mother_is_rejected():
    valid, reason = validate_relationship(
        type("N", (), {"age": 25, "gender": "Female", "name": "Child"})(),
        type("N", (), {"age": 55, "gender": "Male", "name": "Arumugam"})(),
        "Mother",
    )
    assert valid is False
    assert "male but named as a mother" in reason


def test_unknown_age_does_not_reject():
    """Absence of evidence is not a contradiction — the edge stands, unscored."""
    fam = only_family([
        voter("p", "Arumugam", None, "Male", serial=1),
        voter("q", "Vela", None, "Male", "Father", "Arumugam", serial=2),
    ])
    assert len(fam["relationships"]) == 1


# --- Confidence must reflect evidence actually present ----------------------


def test_missing_ages_cap_below_confirmed():
    """No ages recorded means the age check never ran, so it earns no points."""
    fam = only_family([
        voter("p", "Arumugam", None, "Male", serial=1),
        voter("q", "Vela", None, "Male", "Father", "Arumugam", serial=2),
    ])

    edge = fam["relationships"][0]
    # 30 locality + 35 name + 20 relation + 0 age + 5 gender
    assert edge["confidence"] == 90
    assert edge["confidence_level"] == "Strong"
    assert edge["evidence"]["age_known"] is False
    assert edge["evidence"]["age_valid"] is False
    assert fam["confidence_level"] != "Confirmed"


def test_full_evidence_reaches_confirmed():
    fam = only_family([
        voter("p", "Arumugam", 60, "Male", serial=1),
        voter("q", "Vela", 30, "Male", "Father", "Arumugam", serial=2),
    ])
    edge = fam["relationships"][0]
    assert edge["confidence"] == 100
    assert edge["evidence"]["age_valid"] is True
    assert edge["evidence"]["gender_valid"] is True


def test_unlinked_resident_scores_zero_not_one_hundred():
    """A relative named but absent from the household proves nothing."""
    trees = resolve_family_trees([
        voter("h", "Shanmugam", 60, "Male", serial=1),
        voter("x", "Lonely", 40, "Male", "Father", "SomeoneElse", serial=2),
    ])

    lonely = find_family(trees, "Lonely")
    assert lonely["confidence"] == 0
    assert lonely["confidence_level"] == "Unverified"
    assert lonely["unresolved_reason"] == "relative_not_in_household"


def test_no_relation_recorded_is_distinguished_from_failed_lookup():
    fam = only_family([voter("solo", "Ganesan", 45, "Male", serial=1)])
    assert fam["confidence"] == 0
    assert fam["unresolved_reason"] == "no_relation_recorded"


def test_confidence_helper_awards_no_points_for_unknown_data():
    src = type("N", (), {"age": None, "gender": "", "name": "A"})()
    tgt = type("N", (), {"age": None, "gender": "", "name": "B"})()
    score, evidence = calculate_relationship_confidence(src, tgt, "Father", 30, 1.0)
    assert score == 85  # 30 + 35 + 20, nothing for age or gender
    assert evidence["age_valid"] is False
    assert evidence["gender_valid"] is False


# --- Spouse handling --------------------------------------------------------


def test_married_couple_yields_one_root_and_no_duplicate_ascii_line():
    fam = only_family([
        voter("h", "Shanmugam", 60, "Male", serial=1),
        voter("w", "Suseela", 55, "Female", "Husband", "Shanmugam", serial=2),
        voter("s", "Kumar", 30, "Male", "Father", "Shanmugam", serial=3),
    ])

    assert fam["root_ids"] == ["h"]
    lines = fam["ascii_tree"].splitlines()
    assert len(lines) == 2, fam["ascii_tree"]
    assert "💍 Suseela" in lines[0]
    # Suseela appears exactly once, inline on her husband's line.
    assert fam["ascii_tree"].count("Suseela") == 1
    assert "Kumar" in lines[1]


def test_married_in_spouse_is_not_a_senior_root():
    """A daughter-in-law has no parents on the roll — only a husband — so she
    must not be mistaken for a senior-generation root and drawn twice."""
    fam = only_family([
        voter("h", "Anbu", 61, "Male", serial=1),
        voter("s", "Karthi", 32, "Male", "Father", "Anbu", serial=2),
        voter("w", "Subbulakshmi", 27, "Female", "Husband", "Karthi", serial=3),
        voter("s2", "Thanraj", 31, "Male", "Father", "Anbu", serial=4),
    ])

    assert fam["root_ids"] == ["h"]
    by_name = {m["name"]: m for m in fam["members"]}
    assert by_name["Subbulakshmi"]["generation_level"] == 2
    assert by_name["Subbulakshmi"]["spouse_id"] == "s"
    # She appears once, inline on her husband's line.
    assert fam["ascii_tree"].count("Subbulakshmi") == 1
    assert len(fam["ascii_tree"].splitlines()) == 3


def test_spouse_shares_the_head_generation():
    fam = only_family([
        voter("h", "Shanmugam", 60, "Male", serial=1),
        voter("w", "Suseela", 55, "Female", "Husband", "Shanmugam", serial=2),
        voter("s", "Kumar", 30, "Male", "Father", "Shanmugam", serial=3),
    ])
    by_name = {m["name"]: m for m in fam["members"]}
    assert by_name["Suseela"]["generation_level"] == 1
    assert by_name["Suseela"]["spouse_id"] == "h"
    assert by_name["Kumar"]["generation_level"] == 2


def test_roles_are_stable_for_a_member_who_is_both_child_and_parent():
    """Kumar is Muthu's son and Ravi's father; his role must not depend on
    which edge happened to be built last."""
    fam = only_family([
        voter("v1", "Muthu", 72, "Male", serial=1),
        voter("v2", "Kumar", 50, "Male", "Father", "Muthu", serial=2),
        voter("v4", "Ravi", 28, "Male", "Father", "Kumar", serial=3),
    ])
    by_name = {m["name"]: m for m in fam["members"]}
    assert by_name["Kumar"]["resolved_role"] == "Son"
    assert by_name["Muthu"]["resolved_role"] == "Father"
    assert by_name["Ravi"]["resolved_role"] == "Son"


def test_marriage_is_exclusive():
    """Three electors naming the same husband must not all be married to him —
    the extra claims left the spouse edge asymmetric."""
    trees = resolve_family_trees([
        voter("m", "Munusamy", 77, "Male", serial=1),
        voter("w1", "Venkatalakshmi", 63, "Female", "Husband", "Munusamy", serial=2),
        voter("w2", "Jeya", 61, "Female", "Husband", "Munusamy", serial=3),
        voter("w3", "Mari", 59, "Female", "Husband", "Munusamy", serial=4),
    ])

    spouse_edges = [
        r for t in trees for r in t["relationships"] if r["relationship_type"] == "Husband"
    ]
    assert len(spouse_edges) == 1, spouse_edges

    reasons = [r["reason"] for t in trees for r in t["rejected_links"]]
    assert sum("already recorded as married" in r for r in reasons) == 2, reasons


def test_overlapping_claims_do_not_duplicate_members_across_families():
    """Regression for a real household: three wives plus three children all
    naming one man produced overlapping components that re-listed the same
    people, so the UI reported more residents than the address had."""
    voters = [
        voter("m", "Munusamy", 77, "Male", "Father", "Mariyappan", serial=1),
        voter("w1", "Venkatalakshmi", 63, "Female", "Husband", "Munusamy", serial=2),
        voter("w2", "Jeya", 61, "Female", "Husband", "Munusamy", serial=3),
        voter("w3", "Mari", 59, "Female", "Husband", "Munusamy", serial=4),
        voter("c1", "Saravanan", 44, "Male", "Father", "Munusamy", serial=5),
        voter("c2", "Nagaraj", 38, "Male", "Father", "Munusamy", serial=6),
        voter("c3", "Murugammal", 37, "Female", "Father", "Munusamy", serial=7),
    ]
    trees = resolve_family_trees(voters)

    slots = [m["id"] for t in trees for m in t["members"]]
    assert len(slots) == len(voters), f"{len(slots)} slots for {len(voters)} electors"
    assert sorted(slots) == sorted(v["id"] for v in voters)


def test_every_household_member_appears_exactly_once_in_the_payload():
    """The flat member graph must not drop anyone the tree walk cannot reach."""
    voters = [
        voter("h", "Shanmugam", 60, "Male", serial=1),
        voter("w", "Suseela", 55, "Female", "Husband", "Shanmugam", serial=2),
        voter("s", "Kumar", 30, "Male", "Father", "Shanmugam", serial=3),
        voter("x", "Lonely", 40, "Male", serial=4),
    ]
    trees = resolve_family_trees(voters)
    seen = [m["id"] for t in trees for m in t["members"]]
    assert sorted(seen) == ["h", "s", "w", "x"]


# --- Grouping ---------------------------------------------------------------


def test_serial_window_fallback_scores_lower_than_an_exact_house_match():
    """Adjacent serials are weaker evidence of a shared address than a house
    number, so the same relationship must not score identically."""
    housed = only_family([
        voter("p", "Arumugam", 60, "Male", serial=1),
        voter("q", "Vela", 30, "Male", "Father", "Arumugam", serial=2),
    ])
    windowed = only_family([
        voter("p", "Arumugam", 60, "Male", "", "", house="", serial=1),
        voter("q", "Vela", 30, "Male", "Father", "Arumugam", house="", serial=2),
    ])

    assert windowed["confidence"] < housed["confidence"]
    assert windowed["locality"] == "serial_window"
    assert housed["locality"] == "house"


def test_serial_window_chunks_do_not_span_parts():
    """Serial 5 of part 1 and serial 6 of part 2 are not neighbours."""
    voters = [
        {**voter("a", "Arumugam", 60, "Male", house="", serial=5), "part_number": "1"},
        {**voter("b", "Arumugam", 34, "Male", house="", serial=6), "part_number": "2"},
    ]
    trees = resolve_family_trees(voters)
    # Two different parts cannot form one household, so no shared family.
    assert len(trees) == 2


@pytest.mark.parametrize(
    "raw,house,building",
    [
        ("2-332", "2-332", "2-332"),
        ("2/332", "2-332", "2-332"),
        ("2/332-1", "2-332-1", "2-332"),
        ("2/332/1", "2-332-1", "2-332"),
        ("2-332A", "2-332A", "2-332"),
        ("2-332ஏ", "2-332ஏ", "2-332"),
        ("  2 / 332  ", "2-332", "2-332"),
        ("2--332", "2-332", "2-332"),
        ("301A", "301A", "301"),
        ("5-177", "5-177", "5-177"),
        ("", "", ""),
        (None, "", ""),
    ],
)
def test_house_number_normalisation(raw, house, building):
    """The roll spells one address several ways; the key must not care."""
    assert normalise_house(raw) == house
    assert building_key(raw) == building


def test_is_missing_house():
    assert is_missing_house("") is True
    assert is_missing_house("-") is True
    assert is_missing_house("0") is True
    assert is_missing_house(None) is True
    assert is_missing_house("2-332") is False


def test_family_split_across_house_number_spellings_is_reunited():
    """Regression for a real household: a father and wife recorded at "2-332"
    with his two children at "2/332-1". Grouping on the literal string split the
    children from their own father."""
    fam = only_family([
        voter("f", "Sivaji", 60, "Male", "Father", "Gopal", house="2-332", serial=580),
        voter("w", "Kamala", 53, "Female", "Husband", "Sivaji", house="2-332", serial=582),
        voter("s", "Tamilarasan", 27, "Male", "Father", "Sivaji", house="2/332-1", serial=581),
        voter("d", "Divya", 25, "Female", "Father", "Sivaji", house="2/332-1", serial=583),
    ])

    assert fam["root_ids"] == ["f"]
    by_name = {m["name"]: m for m in fam["members"]}
    assert by_name["Kamala"]["resolved_role"] == "Wife"
    assert sorted(by_name["Sivaji"]["child_ids"]) == ["d", "s"]
    assert by_name["Divya"]["generation_level"] == 2
    assert by_name["Tamilarasan"]["generation_level"] == 2


def test_sub_door_link_scores_below_an_exact_door_match():
    """Same building but a different sub-door is real evidence, just weaker."""
    fam = only_family([
        voter("f", "Sivaji", 60, "Male", house="2-332", serial=1),
        voter("w", "Kamala", 53, "Female", "Husband", "Sivaji", house="2-332", serial=2),
        voter("d", "Divya", 25, "Female", "Father", "Sivaji", house="2/332-1", serial=3),
    ])
    by_source = {r["source_name"]: r for r in fam["relationships"]}

    assert by_source["Kamala"]["evidence"]["locality_score"] == 30
    assert by_source["Divya"]["evidence"]["locality_score"] == 22
    assert by_source["Divya"]["confidence"] < by_source["Kamala"]["confidence"]


def test_neighbouring_sub_doors_with_no_shared_names_stay_separate():
    """Widening the candidate pool must not invent relationships: unrelated
    occupants of another sub-door simply never link."""
    trees = resolve_family_trees([
        voter("a", "Sivaji", 60, "Male", house="2-332", serial=1),
        voter("b", "Kamala", 53, "Female", "Husband", "Sivaji", house="2-332", serial=2),
        voter("c", "Rajendran", 45, "Male", "Father", "Perumal", house="2-332-2", serial=3),
        voter("d", "Lakshmi", 40, "Female", "Husband", "Rajendran", house="2-332-2", serial=4),
    ])

    assert len(trees) == 2
    families = {t["family_head"] for t in trees}
    assert families == {"Sivaji", "Rajendran"}


def test_different_houses_do_not_merge():
    trees = resolve_family_trees([
        voter("a", "Muthu", 70, "Male", house="10", serial=1),
        voter("b", "Kumar", 40, "Male", "Father", "Muthu", house="11", serial=2),
    ])
    assert len(trees) == 2
    assert all(t["relationships"] == [] for t in trees)


def test_cycle_is_rejected_when_names_repeat_across_generations():
    """Reusing a name down the generations must not make anyone their own
    ancestor, which would recurse forever in the tree walk."""
    trees = resolve_family_trees([
        voter("a", "Muthu", 70, "Male", "Father", "Kumar", serial=1),
        voter("b", "Kumar", 45, "Male", "Father", "Muthu", serial=2),
    ])
    # One direction resolves; the reciprocal edge would close the loop.
    total_edges = sum(len(t["relationships"]) for t in trees)
    assert total_edges == 1
    for t in trees:
        assert t["generation_count"] <= 2
