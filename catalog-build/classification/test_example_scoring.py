"""Tests for _score_example_relevance in extract_topmed_seeds.py.

Verifies that generic variables (age, visit, etc.) are blocked as examples
for disease-specific concepts even when the concept_id contains the generic
term. E.g., "AGEBL: CALCULATED AGE AT BASELINE" should NOT be an example
for vte_followup_start_age.
"""

import pytest

from extract_topmed_seeds import _score_example_relevance


class TestGenericTermBlocking:
    """Generic terms like 'age' should be blocked unless the variable
    demonstrates the SPECIFIC kind of measurement the concept captures."""

    def test_generic_age_blocked_for_vte(self):
        """Generic 'age at baseline' is blocked for VTE followup age."""
        score = _score_example_relevance(
            "vte_followup_start_age", "AGEBL", "CALCULATED AGE AT BASELINE"
        )
        assert score == -1

    def test_generic_age_visit_blocked_for_vte(self):
        """Generic 'age at visit 1' is blocked for VTE followup age."""
        score = _score_example_relevance(
            "vte_followup_start_age", "V1AGE01", "Age at visit 1"
        )
        assert score == -1

    def test_generic_age_exam_blocked_for_vte(self):
        """Generic 'age at exam 1' is blocked for VTE followup age."""
        score = _score_example_relevance(
            "vte_followup_start_age", "age1", "Age at Exam 1"
        )
        assert score == -1

    def test_vte_specific_age_passes(self):
        """Age variable with VTE context should pass."""
        score = _score_example_relevance(
            "vte_followup_start_age", "V1AGE01",
            "Age at visit 1, start of VTE event adjudication period"
        )
        assert score > 0

    def test_generic_age_blocked_for_cad(self):
        """Generic 'age at baseline' is blocked for CAD followup age."""
        score = _score_example_relevance(
            "cad_followup_start_age", "AGEBL", "CALCULATED AGE AT BASELINE"
        )
        assert score == -1

    def test_cad_specific_age_passes(self):
        """Age variable with CAD/cardiovascular context should pass."""
        score = _score_example_relevance(
            "cad_followup_start_age", "AGEBL",
            "Calculated age at baseline, start of cardiovascular follow-up"
        )
        assert score > 0

    def test_generic_age_enrollment_blocked_for_cad(self):
        """Generic 'age at enrollment' is blocked for CAD followup age."""
        score = _score_example_relevance(
            "cad_followup_start_age", "AGE", "Age at enrollment"
        )
        assert score == -1


class TestSimpleConcepts:
    """Simple concepts (1-2 keywords like annotated_sex, race_us) should
    allow their own generic-term variables as examples."""

    def test_sex_passes_for_annotated_sex(self):
        """'SEX: Sex of participant' is fine for annotated_sex."""
        score = _score_example_relevance(
            "annotated_sex", "SEX", "Sex of participant"
        )
        assert score > 0

    def test_race_passes_for_race_us(self):
        """'RACE: Race of participant' is fine for race_us."""
        score = _score_example_relevance(
            "race_us", "RACE", "RACE (VERIFIED AT EXAM 2)"
        )
        assert score > 0


class TestNonAgeConcepts:
    """Non-age concepts should still penalize generic age variables
    and accept their own domain variables."""

    def test_age_blocked_for_bp(self):
        """Age variable is blocked for blood pressure concept."""
        score = _score_example_relevance(
            "bp_systolic", "AGE", "Age at blood pressure measurement"
        )
        assert score == -1

    def test_bp_variable_passes(self):
        """Blood pressure variable passes for bp concept."""
        score = _score_example_relevance(
            "bp_systolic", "SBPA21",
            "SITTING SYSTOLIC BLOOD PRESSURE, FIRST READING"
        )
        assert score > 0

    def test_ecg_variable_passes(self):
        """ECG variable passes for ecg concept."""
        score = _score_example_relevance(
            "ecg", "ECGAFIB", "ECG atrial fibrillation"
        )
        assert score > 0

    def test_consent_blocked_for_non_consent(self):
        """Consent variable blocked for non-consent concept."""
        score = _score_example_relevance(
            "bp_systolic", "CONSENT", "Consent group"
        )
        assert score == -1
