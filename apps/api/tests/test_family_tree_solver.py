"""Unit tests for Senior Data Engineer & Genealogy Expert Family Tree Solver Engine."""

import pytest
from app.services.family_tree_solver import (
    calculate_relationship_confidence,
    clean_name,
    fuzzy_match_names,
    get_confidence_level,
    resolve_family_trees,
)


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
        {
            "id": "v1",
            "name": "Muthu",
            "relation_type": "",
            "relation_name": "",
            "age": 72,
            "gender": "Male",
            "house_number": "5-177",
            "serial": 1,
            "epic": "EPIC001",
        },
        {
            "id": "v2",
            "name": "Kumar",
            "relation_type": "Father",
            "relation_name": "Muthu",
            "age": 50,
            "gender": "Male",
            "house_number": "5-177",
            "serial": 2,
            "epic": "EPIC002",
        },
        {
            "id": "v3",
            "name": "Selvam",
            "relation_type": "Father",
            "relation_name": "Muthu",
            "age": 48,
            "gender": "Male",
            "house_number": "5-177",
            "serial": 3,
            "epic": "EPIC003",
        },
        {
            "id": "v4",
            "name": "Ravi",
            "relation_type": "Father",
            "relation_name": "Kumar",
            "age": 28,
            "gender": "Male",
            "house_number": "5-177",
            "serial": 4,
            "epic": "EPIC004",
        },
    ]

    trees = resolve_family_trees(sample_voters)
    assert len(trees) == 1
    fam = trees[0]

    assert fam["family_head"] == "Muthu"
    assert fam["house_number"] == "5-177"
    assert fam["confidence"] >= 95
    assert fam["confidence_level"] == "Confirmed"
    assert "Muthu (72)" in fam["ascii_tree"]
    assert "Kumar (50)" in fam["ascii_tree"]
    assert "Ravi (28)" in fam["ascii_tree"]
