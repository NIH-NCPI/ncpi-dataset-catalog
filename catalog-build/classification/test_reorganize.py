"""Tests for reorganize_concepts.py models and longitudinal detection."""

import pytest
from pydantic import ValidationError

from longitudinal import (
    LongitudinalResult,
    detect_study_longitudinal_concepts,
    detect_table_longitudinal,
    detect_variable_longitudinal,
)
from models import (
    ConceptNode,
    ConceptPlacement,
    MidLevelReorgResult,
    SynonymMapping,
    SynonymOnlyResult,
    TreeOnlyResult,
    _is_title_case,
    build_tree_from_placements,
    find_single_child_nodes,
)


# ---------------------------------------------------------------------------
# Title Case helper
# ---------------------------------------------------------------------------


class TestIsTitleCase:
    """Tests for the _is_title_case helper."""

    def test_standard_title_case(self):
        assert _is_title_case("Systolic Blood Pressure")

    def test_lowercase_prepositions(self):
        assert _is_title_case("Age at Onset")
        assert _is_title_case("History of Diabetes")

    def test_first_word_must_be_capitalized(self):
        assert not _is_title_case("systolic Blood Pressure")

    def test_all_lowercase_fails(self):
        assert not _is_title_case("systolic blood pressure")

    def test_single_word(self):
        assert _is_title_case("Age")
        assert not _is_title_case("age")

    def test_with_numbers(self):
        assert _is_title_case("Apolipoprotein A-I")
        assert _is_title_case("FEV1 Percent Predicted")

    def test_with_hyphens(self):
        assert _is_title_case("Ankle-Brachial Index")

    def test_with_slashes(self):
        assert _is_title_case("Race/Ethnicity")

    def test_with_parentheses(self):
        assert _is_title_case("Complete Blood Count (CBC)")
        assert _is_title_case("Forced Expiratory Volume (FEV1)")


# ---------------------------------------------------------------------------
# build_tree_from_placements
# ---------------------------------------------------------------------------


class TestBuildTree:
    """Tests for the flat-to-tree builder."""

    def test_flat_list(self):
        placements = [
            ConceptPlacement(concept="Systolic Blood Pressure"),
            ConceptPlacement(concept="Diastolic Blood Pressure"),
        ]
        tree = build_tree_from_placements(placements)
        assert len(tree) == 2
        assert tree[0].concept == "Systolic Blood Pressure"
        assert tree[0].children == []

    def test_parent_child(self):
        placements = [
            ConceptPlacement(concept="Systolic Blood Pressure"),
            ConceptPlacement(
                concept="Standing Systolic Blood Pressure",
                parent="Systolic Blood Pressure",
            ),
        ]
        tree = build_tree_from_placements(placements)
        assert len(tree) == 1
        assert tree[0].concept == "Systolic Blood Pressure"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].concept == "Standing Systolic Blood Pressure"

    def test_multi_level(self):
        placements = [
            ConceptPlacement(concept="Blood Pressure"),
            ConceptPlacement(
                concept="Systolic Blood Pressure", parent="Blood Pressure"
            ),
            ConceptPlacement(
                concept="Standing Systolic Blood Pressure",
                parent="Systolic Blood Pressure",
            ),
            ConceptPlacement(
                concept="Sitting Systolic Blood Pressure",
                parent="Systolic Blood Pressure",
            ),
            ConceptPlacement(
                concept="Diastolic Blood Pressure", parent="Blood Pressure"
            ),
        ]
        tree = build_tree_from_placements(placements)
        assert len(tree) == 1
        bp = tree[0]
        assert bp.concept == "Blood Pressure"
        assert len(bp.children) == 2
        sbp = bp.children[0]
        assert sbp.concept == "Systolic Blood Pressure"
        assert len(sbp.children) == 2


# ---------------------------------------------------------------------------
# MidLevelReorgResult validators
# ---------------------------------------------------------------------------


class TestMidLevelReorgResult:
    """Tests for the Pydantic model validators."""

    def _simple_result(self, **overrides):
        """Build a minimal valid result, with optional overrides."""
        defaults = {
            "reasoning": "SBP and DBP are distinct measurements.",
            "concepts": [
                ConceptPlacement(concept="Systolic Blood Pressure"),
                ConceptPlacement(concept="Diastolic Blood Pressure"),
            ],
            "synonyms": [],
        }
        defaults.update(overrides)
        return MidLevelReorgResult(**defaults)

    def test_valid_simple(self):
        result = self._simple_result()
        assert len(result.get_all_concepts()) == 2
        assert result.get_synonym_map() == {}

    def test_valid_with_synonyms(self):
        result = MidLevelReorgResult(
            reasoning="Seated and Sitting DBP are the same measurement.",
            concepts=[
                ConceptPlacement(concept="Systolic Blood Pressure"),
                ConceptPlacement(concept="Diastolic Blood Pressure"),
            ],
            synonyms=[
                SynonymMapping(
                    synonym="Seated Diastolic BP",
                    canonical="Diastolic Blood Pressure",
                ),
            ],
        )
        assert result.get_synonym_map() == {
            "Seated Diastolic BP": "Diastolic Blood Pressure"
        }

    def test_valid_nested_tree(self):
        result = MidLevelReorgResult(
            reasoning="Standing and Sitting SBP are specific types of SBP.",
            concepts=[
                ConceptPlacement(concept="Systolic Blood Pressure"),
                ConceptPlacement(
                    concept="Standing Systolic Blood Pressure",
                    parent="Systolic Blood Pressure",
                ),
                ConceptPlacement(
                    concept="Sitting Systolic Blood Pressure",
                    parent="Systolic Blood Pressure",
                ),
            ],
            synonyms=[],
        )
        assert len(result.get_all_concepts()) == 3
        tree = result.build_tree()
        assert len(tree) == 1
        assert len(tree[0].children) == 2

    def test_accepts_any_casing(self):
        """Input names pass through as-is, no casing enforcement."""
        result = MidLevelReorgResult(
            reasoning="Test.",
            concepts=[
                ConceptPlacement(concept="systolic blood pressure"),
            ],
            synonyms=[],
        )
        assert len(result.concepts) == 1

    def test_rejects_synonym_target_not_in_concepts(self):
        with pytest.raises(ValidationError, match="not found in concepts"):
            MidLevelReorgResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(concept="Systolic Blood Pressure"),
                ],
                synonyms=[
                    SynonymMapping(
                        synonym="SBP",
                        canonical="Nonexistent Concept",
                    ),
                ],
            )

    def test_rejects_concept_in_both_concepts_and_synonyms(self):
        with pytest.raises(ValidationError, match="both as synonym sources"):
            MidLevelReorgResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(concept="Systolic Blood Pressure"),
                    ConceptPlacement(concept="SBP"),
                ],
                synonyms=[
                    SynonymMapping(
                        synonym="SBP",
                        canonical="Systolic Blood Pressure",
                    ),
                ],
            )

    def test_rejects_duplicate_synonym_sources(self):
        with pytest.raises(ValidationError, match="Duplicate synonym"):
            MidLevelReorgResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(concept="Systolic Blood Pressure"),
                    ConceptPlacement(concept="Diastolic Blood Pressure"),
                ],
                synonyms=[
                    SynonymMapping(
                        synonym="SBP",
                        canonical="Systolic Blood Pressure",
                    ),
                    SynonymMapping(
                        synonym="SBP",
                        canonical="Diastolic Blood Pressure",
                    ),
                ],
            )

    def test_allows_lowercase_prepositions_in_title_case(self):
        result = MidLevelReorgResult(
            reasoning="Both use valid preposition casing.",
            concepts=[
                ConceptPlacement(concept="Age at Onset"),
                ConceptPlacement(concept="History of Diabetes"),
            ],
            synonyms=[],
        )
        assert len(result.get_all_concepts()) == 2

    def test_deeply_nested_tree(self):
        result = MidLevelReorgResult(
            reasoning="Multi-level hierarchy.",
            concepts=[
                ConceptPlacement(concept="Blood Pressure"),
                ConceptPlacement(
                    concept="Systolic Blood Pressure", parent="Blood Pressure"
                ),
                ConceptPlacement(
                    concept="Standing Systolic Blood Pressure",
                    parent="Systolic Blood Pressure",
                ),
                ConceptPlacement(
                    concept="Sitting Systolic Blood Pressure",
                    parent="Systolic Blood Pressure",
                ),
                ConceptPlacement(
                    concept="Diastolic Blood Pressure", parent="Blood Pressure"
                ),
            ],
            synonyms=[],
        )
        concepts = result.get_all_concepts()
        assert concepts == {
            "Blood Pressure",
            "Systolic Blood Pressure",
            "Standing Systolic Blood Pressure",
            "Sitting Systolic Blood Pressure",
            "Diastolic Blood Pressure",
        }

    def test_single_child_parent_is_soft_warning(self):
        """A parent with only one child is allowed (soft warning, not rejected)."""
        result = MidLevelReorgResult(
            reasoning="Single child case.",
            concepts=[
                ConceptPlacement(concept="Blood Pressure"),
                ConceptPlacement(
                    concept="Systolic Blood Pressure", parent="Blood Pressure"
                ),
            ],
            synonyms=[],
        )
        tree = result.build_tree()
        violations = find_single_child_nodes(tree)
        assert violations == ["Blood Pressure"]

    def test_allows_invented_parent_with_multiple_children(self):
        """Invented parent nodes are fine with 2+ children."""
        result = MidLevelReorgResult(
            reasoning="Cranial Measurements groups two concepts.",
            concepts=[
                ConceptPlacement(concept="Cranial Measurements"),
                ConceptPlacement(
                    concept="Head Circumference", parent="Cranial Measurements"
                ),
                ConceptPlacement(
                    concept="Cranial Length", parent="Cranial Measurements"
                ),
            ],
            synonyms=[],
        )
        assert "Cranial Measurements" in result.get_all_concepts()

    def test_rejects_self_parent(self):
        """A concept cannot be its own parent."""
        with pytest.raises(ValidationError, match="itself as its own parent"):
            MidLevelReorgResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(
                        concept="Blood Pressure", parent="Blood Pressure"
                    ),
                ],
                synonyms=[],
            )

    def test_rejects_invalid_parent_ref(self):
        """Parent must reference an existing concept."""
        with pytest.raises(ValidationError, match="not found in concepts"):
            MidLevelReorgResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(
                        concept="Standing SBP", parent="Nonexistent"
                    ),
                ],
                synonyms=[],
            )

    def test_rejects_duplicate_concepts(self):
        """No duplicate concept names."""
        with pytest.raises(ValidationError, match="Duplicate concept"):
            MidLevelReorgResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(concept="Blood Pressure"),
                    ConceptPlacement(concept="Blood Pressure"),
                ],
                synonyms=[],
            )


# ---------------------------------------------------------------------------
# SynonymOnlyResult validators
# ---------------------------------------------------------------------------


class TestSynonymOnlyResult:
    """Tests for the synonym-only output model (two-pass pipeline)."""

    def test_valid_empty(self):
        result = SynonymOnlyResult(
            reasoning="No synonyms found.", synonyms=[]
        )
        assert result.synonyms == []

    def test_valid_with_synonyms(self):
        result = SynonymOnlyResult(
            reasoning="Seated and Sitting are the same posture.",
            synonyms=[
                SynonymMapping(
                    synonym="Seated Diastolic BP",
                    canonical="Sitting Diastolic Blood Pressure",
                ),
            ],
        )
        assert len(result.synonyms) == 1

    def test_rejects_self_mapping(self):
        with pytest.raises(ValidationError, match="maps to itself"):
            SynonymOnlyResult(
                reasoning="Test.",
                synonyms=[
                    SynonymMapping(
                        synonym="Systolic Blood Pressure",
                        canonical="Systolic Blood Pressure",
                    ),
                ],
            )

    def test_rejects_duplicate_sources(self):
        with pytest.raises(ValidationError, match="Duplicate synonym"):
            SynonymOnlyResult(
                reasoning="Test.",
                synonyms=[
                    SynonymMapping(
                        synonym="SBP", canonical="Systolic Blood Pressure"
                    ),
                    SynonymMapping(
                        synonym="SBP", canonical="Diastolic Blood Pressure"
                    ),
                ],
            )


# ---------------------------------------------------------------------------
# TreeOnlyResult validators
# ---------------------------------------------------------------------------


class TestTreeOnlyResult:
    """Tests for the tree-only output model (two-pass pipeline)."""

    def test_valid_flat(self):
        result = TreeOnlyResult(
            reasoning="All concepts are peers.",
            concepts=[
                ConceptPlacement(concept="Systolic Blood Pressure"),
                ConceptPlacement(concept="Diastolic Blood Pressure"),
            ],
        )
        assert len(result.get_all_concepts()) == 2

    def test_valid_nested(self):
        result = TreeOnlyResult(
            reasoning="BP groups SBP and DBP.",
            concepts=[
                ConceptPlacement(concept="Blood Pressure"),
                ConceptPlacement(
                    concept="Systolic Blood Pressure", parent="Blood Pressure"
                ),
                ConceptPlacement(
                    concept="Diastolic Blood Pressure", parent="Blood Pressure"
                ),
            ],
        )
        assert len(result.get_all_concepts()) == 3
        tree = result.build_tree()
        assert len(tree) == 1
        assert len(tree[0].children) == 2

    def test_accepts_any_casing(self):
        """Input names pass through as-is, no casing enforcement."""
        result = TreeOnlyResult(
            reasoning="Test.",
            concepts=[
                ConceptPlacement(concept="systolic blood pressure"),
            ],
        )
        assert len(result.get_all_concepts()) == 1

    def test_single_child_is_soft_warning(self):
        """Single-child parent is allowed (detected by find_single_child_nodes)."""
        result = TreeOnlyResult(
            reasoning="Test.",
            concepts=[
                ConceptPlacement(concept="Blood Pressure"),
                ConceptPlacement(
                    concept="Systolic Blood Pressure", parent="Blood Pressure"
                ),
            ],
        )
        tree = result.build_tree()
        assert find_single_child_nodes(tree) == ["Blood Pressure"]

    def test_accepts_casing_variants(self):
        """Casing variants are treated as distinct concepts (no normalization)."""
        result = TreeOnlyResult(
            reasoning="Test.",
            concepts=[
                ConceptPlacement(concept="Age at Onset"),
                ConceptPlacement(concept="Age At Onset"),
            ],
        )
        assert len(result.get_all_concepts()) == 2

    def test_rejects_self_parent(self):
        with pytest.raises(ValidationError, match="itself as its own parent"):
            TreeOnlyResult(
                reasoning="Test.",
                concepts=[
                    ConceptPlacement(
                        concept="Blood Pressure", parent="Blood Pressure"
                    ),
                ],
            )


# ---------------------------------------------------------------------------
# Longitudinal detection
# ---------------------------------------------------------------------------


class TestTableLongitudinal:
    """Tests for detect_table_longitudinal."""

    def test_exam_pattern(self):
        r = detect_table_longitudinal("e_exam_ex01_2_0813s")
        assert r.is_longitudinal
        assert r.pattern == "exam"

    def test_visit_pattern(self):
        r = detect_table_longitudinal("visit3_ecg_results")
        assert r.is_longitudinal
        assert r.pattern == "visit"

    def test_baseline_pattern(self):
        r = detect_table_longitudinal("baseline_demographics")
        assert r.is_longitudinal
        assert r.pattern == "study-phase"

    def test_not_longitudinal(self):
        r = detect_table_longitudinal("ALS_Subject_Phenotypes")
        assert not r.is_longitudinal

    def test_cases_controls_override(self):
        r = detect_table_longitudinal("ALS_Follow_Up_Cases_Controls")
        assert not r.is_longitudinal

    def test_stage_override(self):
        r = detect_table_longitudinal("ALS_First_Stage_Cases")
        assert not r.is_longitudinal

    def test_plain_table_name(self):
        r = detect_table_longitudinal("blood_pressure_data")
        assert not r.is_longitudinal


class TestVariableLongitudinal:
    """Tests for detect_variable_longitudinal."""

    def test_exam_prefix(self):
        r = detect_variable_longitudinal("exam1_sbp", "Systolic BP, Exam 1")
        assert r.is_longitudinal
        assert r.time_point == "Exam 1"

    def test_visit_in_description(self):
        r = detect_variable_longitudinal("v01_age", "Age at Visit 1")
        assert r.is_longitudinal
        assert r.time_point == "Visit 1"

    def test_not_longitudinal(self):
        r = detect_variable_longitudinal("sbp", "Systolic Blood Pressure")
        assert not r.is_longitudinal

    def test_no_description(self):
        r = detect_variable_longitudinal("bmi", "")
        assert not r.is_longitudinal


class TestStudyLongitudinalConcepts:
    """Tests for detect_study_longitudinal_concepts."""

    def test_concept_in_multiple_longitudinal_tables(self):
        tables = [
            {
                "isLongitudinal": True,
                "concepts": ["Systolic Blood Pressure", "Age"],
            },
            {
                "isLongitudinal": True,
                "concepts": ["Systolic Blood Pressure", "Weight"],
            },
            {
                "isLongitudinal": False,
                "concepts": ["Age", "Sex"],
            },
        ]
        result = detect_study_longitudinal_concepts(tables)
        assert "Systolic Blood Pressure" in result
        assert "Age" not in result  # only in 1 longitudinal table
        assert "Sex" not in result

    def test_no_longitudinal_tables(self):
        tables = [
            {"isLongitudinal": False, "concepts": ["Age", "Sex"]},
        ]
        result = detect_study_longitudinal_concepts(tables)
        assert len(result) == 0
