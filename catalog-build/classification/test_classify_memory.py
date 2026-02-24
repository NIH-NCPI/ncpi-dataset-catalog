"""Tests for classify_with_memory.py models and ConceptBank."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from classify_with_memory import (
    ClassifyDeps,
    ConceptBank,
    _build_bank_lookup,
    _normalize_concept,
    format_table_prompt,
    write_study_output,
)
from models import ClassifiedBatch, ClassifiedVariable, ParsedTable


# ---------------------------------------------------------------------------
# ClassifiedVariable
# ---------------------------------------------------------------------------


class TestClassifiedVariable:
    """Tests for the ClassifiedVariable model."""

    def test_valid_title_case(self):
        v = ClassifiedVariable(
            concept="Systolic Blood Pressure", variable_name="SBP"
        )
        assert v.concept == "Systolic Blood Pressure"

    def test_lowercase_prepositions_allowed(self):
        v = ClassifiedVariable(
            concept="Age at Onset", variable_name="AGE_ONSET"
        )
        assert v.concept == "Age at Onset"

    def test_rejects_all_lowercase(self):
        with pytest.raises(ValidationError, match="Title Case"):
            ClassifiedVariable(
                concept="systolic blood pressure", variable_name="SBP"
            )

    def test_rejects_first_word_lowercase(self):
        with pytest.raises(ValidationError, match="Title Case"):
            ClassifiedVariable(
                concept="systolic Blood Pressure", variable_name="SBP"
            )

    def test_rejects_non_exempt_lowercase(self):
        with pytest.raises(ValidationError, match="Title Case"):
            ClassifiedVariable(
                concept="Systolic blood Pressure", variable_name="SBP"
            )

    def test_with_numbers(self):
        v = ClassifiedVariable(
            concept="FEV1 Percent Predicted", variable_name="FEV1PP"
        )
        assert v.concept == "FEV1 Percent Predicted"

    def test_with_parentheses(self):
        v = ClassifiedVariable(
            concept="Complete Blood Count (CBC)", variable_name="CBC"
        )
        assert v.concept == "Complete Blood Count (CBC)"

    def test_with_hyphens(self):
        v = ClassifiedVariable(
            concept="Ankle-Brachial Index", variable_name="ABI"
        )
        assert v.concept == "Ankle-Brachial Index"


# ---------------------------------------------------------------------------
# ClassifiedBatch
# ---------------------------------------------------------------------------


class TestClassifiedBatch:
    """Tests for the ClassifiedBatch model."""

    def test_valid_batch(self):
        batch = ClassifiedBatch(
            reasoning="Reused existing bank concepts for blood pressure vars",
            variables=[
                ClassifiedVariable(
                    concept="Systolic Blood Pressure", variable_name="SBP"
                ),
                ClassifiedVariable(
                    concept="Diastolic Blood Pressure", variable_name="DBP"
                ),
            ],
        )
        assert len(batch.variables) == 2
        assert batch.reasoning.startswith("Reused")

    def test_empty_variables(self):
        batch = ClassifiedBatch(reasoning="No variables", variables=[])
        assert len(batch.variables) == 0

    def test_rejects_invalid_concept_in_batch(self):
        with pytest.raises(ValidationError, match="Title Case"):
            ClassifiedBatch(
                reasoning="test",
                variables=[
                    ClassifiedVariable(
                        concept="bad concept", variable_name="X"
                    ),
                ],
            )

    def test_rejects_duplicate_variable_names(self):
        with pytest.raises(ValidationError, match="Duplicate variable names"):
            ClassifiedBatch(
                reasoning="test",
                variables=[
                    ClassifiedVariable(
                        concept="Systolic Blood Pressure", variable_name="SBP"
                    ),
                    ClassifiedVariable(
                        concept="Systolic Blood Pressure", variable_name="SBP"
                    ),
                ],
            )

    def test_same_concept_different_vars_ok(self):
        batch = ClassifiedBatch(
            reasoning="test",
            variables=[
                ClassifiedVariable(
                    concept="Systolic Blood Pressure", variable_name="SBP1"
                ),
                ClassifiedVariable(
                    concept="Systolic Blood Pressure", variable_name="SBP2"
                ),
            ],
        )
        assert len(batch.variables) == 2


# ---------------------------------------------------------------------------
# ConceptBank
# ---------------------------------------------------------------------------


class TestConceptBank:
    """Tests for the ConceptBank dataclass."""

    def test_empty_bank(self):
        bank = ConceptBank()
        assert len(bank.concepts) == 0
        assert bank.top_n() == []

    def test_register_new_concepts(self):
        bank = ConceptBank()
        new = bank.register(["Age", "Sex", "Height"])
        assert new == 3
        assert bank.concepts["Age"] == 1
        assert bank.concepts["Sex"] == 1

    def test_register_increments_existing(self):
        bank = ConceptBank()
        bank.register(["Age", "Sex"])
        new = bank.register(["Age", "Weight"])
        assert new == 1  # only Weight is new
        assert bank.concepts["Age"] == 2
        assert bank.concepts["Weight"] == 1

    def test_top_n(self):
        bank = ConceptBank()
        bank.register(["Age"] * 10)
        bank.register(["Sex"] * 5)
        bank.register(["Height"] * 3)
        bank.register(["Weight"] * 1)

        top2 = bank.top_n(2)
        assert len(top2) == 2
        assert top2[0] == ("Age", 10)
        assert top2[1] == ("Sex", 5)

    def test_top_n_larger_than_bank(self):
        bank = ConceptBank()
        bank.register(["Age", "Sex"])
        top = bank.top_n(100)
        assert len(top) == 2

    def test_format_for_prompt_empty(self):
        bank = ConceptBank()
        result = bank.format_for_prompt()
        assert "No concepts assigned yet" in result

    def test_format_for_prompt_with_concepts(self):
        bank = ConceptBank()
        bank.register(["Age"] * 10)
        bank.register(["Sex"] * 5)
        result = bank.format_for_prompt(10)
        assert "Age (10)" in result
        assert "Sex (5)" in result

    def test_save_load_roundtrip(self, tmp_path):
        bank = ConceptBank()
        bank.register(["Age"] * 10)
        bank.register(["Sex"] * 5)
        bank.register(["Height"] * 3)

        save_path = tmp_path / "bank.json"
        bank.save(save_path)

        loaded = ConceptBank.load(save_path)
        assert loaded.concepts == bank.concepts
        assert loaded.concepts["Age"] == 10
        assert loaded.concepts["Sex"] == 5

    def test_save_creates_parent_dirs(self, tmp_path):
        bank = ConceptBank()
        bank.register(["Age"])
        save_path = tmp_path / "nested" / "dir" / "bank.json"
        bank.save(save_path)
        assert save_path.exists()


# ---------------------------------------------------------------------------
# Output validator logic
# ---------------------------------------------------------------------------


class TestOutputValidation:
    """Tests for the output validation logic (deps-based)."""

    def test_missing_variables_detected(self):
        """Simulates the agent output validator detecting missing variables."""
        input_names = {"SBP", "DBP", "HR"}
        result = ClassifiedBatch(
            reasoning="test",
            variables=[
                ClassifiedVariable(
                    concept="Systolic Blood Pressure", variable_name="SBP"
                ),
                ClassifiedVariable(
                    concept="Diastolic Blood Pressure", variable_name="DBP"
                ),
            ],
        )
        output_vars = {v.variable_name for v in result.variables}
        missing = input_names - output_vars
        assert missing == {"HR"}

    def test_extra_variables_detected(self):
        """Simulates the agent output validator detecting extra variables."""
        input_names = {"SBP", "DBP"}
        result = ClassifiedBatch(
            reasoning="test",
            variables=[
                ClassifiedVariable(
                    concept="Systolic Blood Pressure", variable_name="SBP"
                ),
                ClassifiedVariable(
                    concept="Diastolic Blood Pressure", variable_name="DBP"
                ),
                ClassifiedVariable(
                    concept="Heart Rate", variable_name="HR"
                ),
            ],
        )
        output_vars = {v.variable_name for v in result.variables}
        extra = output_vars - input_names
        assert extra == {"HR"}

    def test_exact_match_passes(self):
        """When output exactly matches input, no missing or extra."""
        input_names = {"SBP", "DBP"}
        result = ClassifiedBatch(
            reasoning="test",
            variables=[
                ClassifiedVariable(
                    concept="Systolic Blood Pressure", variable_name="SBP"
                ),
                ClassifiedVariable(
                    concept="Diastolic Blood Pressure", variable_name="DBP"
                ),
            ],
        )
        output_vars = {v.variable_name for v in result.variables}
        assert input_names == output_vars


# ---------------------------------------------------------------------------
# format_table_prompt
# ---------------------------------------------------------------------------

_SAMPLE_TABLE = ParsedTable(
    study_id="phs000007",
    dataset_id="pht000183.v14",
    table_name="blood_pressure",
    study_name="Framingham Cohort",
    description="Blood pressure measurements",
    variables=[
        {"name": "SBP", "description": "Systolic blood pressure", "id": "phv001"},
        {"name": "DBP", "description": "Diastolic blood pressure", "id": "phv002"},
        {"name": "OPAQUE", "id": "phv003"},
    ],
    variable_count=3,
    file_path="/fake/path.xml",
)


class TestFormatTablePrompt:
    """Tests for the format_table_prompt helper."""

    def test_includes_study_info(self):
        prompt = format_table_prompt("phs000007", "Framingham Cohort", _SAMPLE_TABLE)
        assert "phs000007" in prompt
        assert "Framingham Cohort" in prompt

    def test_includes_table_metadata(self):
        prompt = format_table_prompt("phs000007", "Framingham Cohort", _SAMPLE_TABLE)
        assert "blood_pressure" in prompt
        assert "Blood pressure measurements" in prompt

    def test_includes_all_variables(self):
        prompt = format_table_prompt("phs000007", "Framingham Cohort", _SAMPLE_TABLE)
        assert "SBP: Systolic blood pressure" in prompt
        assert "DBP: Diastolic blood pressure" in prompt
        assert "3 vars" in prompt

    def test_variable_without_description(self):
        prompt = format_table_prompt("phs000007", "Framingham Cohort", _SAMPLE_TABLE)
        # OPAQUE has no description key — should appear as just the name
        assert "  OPAQUE" in prompt

    def test_subset_of_variables(self):
        subset = [{"name": "SBP", "description": "Systolic blood pressure"}]
        prompt = format_table_prompt(
            "phs000007", "Framingham Cohort", _SAMPLE_TABLE, variables=subset
        )
        assert "1 vars" in prompt
        assert "SBP" in prompt
        assert "DBP" not in prompt

    def test_none_description(self):
        table = ParsedTable(
            study_id="phs000007",
            dataset_id="pht000183.v14",
            table_name="tbl",
            study_name="Study",
            description="",
            variables=[{"name": "X", "description": "test"}],
            variable_count=1,
            file_path="/fake.xml",
        )
        prompt = format_table_prompt("phs000007", "Study", table)
        assert "(none)" in prompt


# ---------------------------------------------------------------------------
# write_study_output
# ---------------------------------------------------------------------------


class TestWriteStudyOutput:
    """Tests for writing and reading per-study JSON."""

    def test_roundtrip(self, tmp_path):
        study = {
            "studyId": "phs000007",
            "studyName": "Framingham Cohort",
            "tables": [
                {
                    "tableName": "bp",
                    "datasetId": "pht001",
                    "description": "Blood pressure",
                    "concepts": ["Diastolic Blood Pressure", "Systolic Blood Pressure"],
                    "variables": [
                        {
                            "name": "SBP",
                            "id": "phv001",
                            "description": "Systolic",
                            "concept": "Systolic Blood Pressure",
                        },
                        {
                            "name": "DBP",
                            "id": "phv002",
                            "description": "Diastolic",
                            "concept": "Diastolic Blood Pressure",
                        },
                    ],
                }
            ],
        }
        path = write_study_output(study, tmp_path)
        assert path.name == "phs000007.json"

        with open(path) as f:
            loaded = json.load(f)

        assert loaded["studyId"] == "phs000007"
        assert len(loaded["tables"]) == 1
        assert loaded["tables"][0]["variables"][0]["concept"] == "Systolic Blood Pressure"

    def test_creates_output_dir(self, tmp_path):
        study = {"studyId": "phs999", "studyName": "Test", "tables": []}
        nested = tmp_path / "a" / "b"
        path = write_study_output(study, nested)
        assert path.exists()


# ---------------------------------------------------------------------------
# Resumability: skipped studies register concepts in the bank
# ---------------------------------------------------------------------------


class TestResumability:
    """Tests for the resume-from-disk logic in run_pipeline."""

    def test_skipped_study_registers_in_bank(self, tmp_path):
        """When a study's output already exists, its concepts join the bank."""
        # Write a fake existing output file
        existing = {
            "studyId": "phs000007",
            "studyName": "Framingham",
            "tables": [
                {
                    "tableName": "bp",
                    "datasetId": "pht001",
                    "description": None,
                    "concepts": ["Systolic Blood Pressure"],
                    "variables": [
                        {
                            "name": "SBP",
                            "id": "phv001",
                            "description": "",
                            "concept": "Systolic Blood Pressure",
                        },
                        {
                            "name": "SBP2",
                            "id": "phv002",
                            "description": "",
                            "concept": "Systolic Blood Pressure",
                        },
                        {
                            "name": "DBP",
                            "id": "phv003",
                            "description": "",
                            "concept": "Diastolic Blood Pressure",
                        },
                    ],
                }
            ],
        }
        output_path = tmp_path / "phs000007.json"
        with open(output_path, "w") as f:
            json.dump(existing, f)

        # Simulate the resume logic from run_pipeline
        bank = ConceptBank()
        with open(output_path) as f:
            data = json.load(f)
        concepts = [
            v["concept"] for t in data["tables"] for v in t["variables"]
        ]
        bank.register(concepts)

        assert "Systolic Blood Pressure" in bank.concepts
        assert "Diastolic Blood Pressure" in bank.concepts
        assert bank.concepts["Systolic Blood Pressure"] == 2
        assert bank.concepts["Diastolic Blood Pressure"] == 1

    def test_bank_persists_across_studies(self, tmp_path):
        """Bank accumulates concepts from multiple resumed studies."""
        bank = ConceptBank()

        for study_id, concept, count in [
            ("phs001", "Age", 5),
            ("phs002", "Sex", 3),
            ("phs003", "Age", 2),
        ]:
            bank.register([concept] * count)

        assert bank.concepts["Age"] == 7
        assert bank.concepts["Sex"] == 3
        assert len(bank.concepts) == 2


# ---------------------------------------------------------------------------
# Near-duplicate detection
# ---------------------------------------------------------------------------


class TestNormalizeConcept:
    """Tests for the _normalize_concept helper."""

    def test_basic(self):
        assert _normalize_concept("Systolic Blood Pressure") == "systolic blood pressure"

    def test_strips_hyphens(self):
        assert _normalize_concept("Ankle-Brachial Index") == "ankle brachial index"

    def test_strips_parentheses(self):
        assert _normalize_concept("Complete Blood Count (CBC)") == "complete blood count cbc"

    def test_strips_slashes(self):
        assert _normalize_concept("Race/Ethnicity") == "race ethnicity"

    def test_collapses_whitespace(self):
        assert _normalize_concept("Race /  Ethnicity") == "race ethnicity"

    def test_near_dupes_match(self):
        assert _normalize_concept("Systolic Blood Pressure") == \
               _normalize_concept("Systolic Blood-Pressure")

    def test_distinct_concepts_differ(self):
        assert _normalize_concept("Systolic Blood Pressure") != \
               _normalize_concept("Diastolic Blood Pressure")


class TestBuildBankLookup:
    """Tests for the _build_bank_lookup helper."""

    def test_empty_bank(self):
        bank = ConceptBank()
        lookup = _build_bank_lookup(bank)
        assert lookup == {}

    def test_builds_normalized_lookup(self):
        bank = ConceptBank()
        bank.register(["Systolic Blood Pressure", "Ankle-Brachial Index"])
        lookup = _build_bank_lookup(bank)
        assert lookup["systolic blood pressure"] == "Systolic Blood Pressure"
        assert lookup["ankle brachial index"] == "Ankle-Brachial Index"

    def test_near_dupe_detected_via_lookup(self):
        """A new concept that normalizes to an existing bank entry is a near-dupe."""
        bank = ConceptBank()
        bank.register(["Systolic Blood Pressure"])
        lookup = _build_bank_lookup(bank)

        new_concept = "Systolic Blood-Pressure"
        norm = _normalize_concept(new_concept)
        assert norm in lookup
        assert lookup[norm] == "Systolic Blood Pressure"

    def test_exact_match_not_flagged(self):
        """An exact match should be in bank_exact, not treated as near-dupe."""
        bank = ConceptBank()
        bank.register(["Systolic Blood Pressure"])
        lookup = _build_bank_lookup(bank)

        exact = "Systolic Blood Pressure"
        bank_exact = set(lookup.values())
        assert exact in bank_exact

    def test_genuinely_new_concept_not_flagged(self):
        """A truly new concept should not appear in the lookup."""
        bank = ConceptBank()
        bank.register(["Systolic Blood Pressure"])
        lookup = _build_bank_lookup(bank)

        new_concept = "Heart Rate"
        norm = _normalize_concept(new_concept)
        assert norm not in lookup
