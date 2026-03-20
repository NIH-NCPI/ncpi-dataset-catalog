"""Tests for build_archetypes.py — rejection mechanism and write_outputs."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from build_archetypes import (
    Archetype,
    ArchetypeTree,
    _lookup_parent_info,
    build_assign_prompt,
    build_user_prompt,
    write_outputs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_output(tmp_path):
    """Set up temp dirs with minimal vocab, ISA, and study files."""
    vocab = [
        {
            "concept_id": "topmed:ecg",
            "name": "Electrocardiogram",
            "description": "ECG measurements including rhythm and intervals",
            "cui": None,
            "domain": "imaging",
        },
        {
            "concept_id": "vte_followup_start_age",
            "name": "VTE Followup Start Age",
            "description": "Age at start of VTE follow-up period",
            "cui": None,
            "domain": "vte",
        },
    ]
    isa = [{"child": "topmed:ecg", "parent": "ncpi:imaging"}]

    vocab_path = tmp_path / "concept-vocabulary.json"
    isa_path = tmp_path / "concept-isa.json"
    vocab_path.write_text(json.dumps(vocab, indent=2))
    isa_path.write_text(json.dumps(isa, indent=2))

    # Study file with mixed variables
    llm_dir = tmp_path / "llm-concepts-v4"
    llm_dir.mkdir()
    study = {
        "tables": [
            {
                "table_name": "t1",
                "variables": [
                    {"name": "AFIB", "description": "Atrial fibrillation", "concept_id": "topmed:ecg"},
                    {"name": "QT_INT", "description": "QT interval", "concept_id": "topmed:ecg"},
                    {"name": "AGE", "description": "Subject age", "concept_id": "topmed:ecg"},
                    {"name": "age_visit", "description": "Age at visit", "concept_id": "topmed:ecg"},
                ],
            }
        ]
    }
    (llm_dir / "phs000001.json").write_text(json.dumps(study, indent=2))

    # Categories file
    cats = [{"concept_id": "ncpi:imaging", "name": "Imaging"}]
    (tmp_path / "ncpi-categories.json").write_text(json.dumps(cats))

    return tmp_path, vocab_path, isa_path, llm_dir


# ---------------------------------------------------------------------------
# ArchetypeTree validation
# ---------------------------------------------------------------------------


class TestArchetypeTree:
    """Tests for ArchetypeTree model validation."""

    def test_rejected_category_accepted(self):
        """_rejected is a valid concept_id."""
        tree = ArchetypeTree(categories=[
            Archetype(
                concept_id="atrial_fibrillation",
                name="Atrial Fibrillation",
                description="AF detection",
                variables=["AFIB"],
            ),
            Archetype(
                concept_id="_rejected",
                name="Rejected",
                description="Does not belong",
                variables=["AGE"],
            ),
        ])
        assert len(tree.categories) == 2

    def test_empty_categories_allowed(self):
        """Empty categories list is valid."""
        tree = ArchetypeTree(categories=[])
        assert tree.categories == []

    def test_duplicate_ids_rejected(self):
        """Duplicate concept_ids raise ValueError."""
        with pytest.raises(ValueError, match="Duplicate"):
            ArchetypeTree(categories=[
                Archetype(concept_id="a", name="A", description="A", variables=["x"]),
                Archetype(concept_id="a", name="B", description="B", variables=["y"]),
            ])


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


class TestPrompts:
    """Tests for prompt generation with rejection instructions."""

    def test_user_prompt_includes_rejection(self):
        """User prompt mentions _rejected."""
        with patch("build_archetypes._lookup_parent_info", return_value=("ECG", "ECG measurements")):
            prompt = build_user_prompt("topmed:ecg", [
                {"name": "AFIB", "description": "Atrial fibrillation"},
            ])
        assert "_rejected" in prompt
        assert "ECG" in prompt

    def test_assign_prompt_includes_rejection(self):
        """Assignment prompt lists _rejected as an option."""
        archetypes = [
            Archetype(concept_id="af", name="AF", description="AF", variables=[]),
        ]
        with patch("build_archetypes._lookup_parent_info", return_value=("ECG", "ECG measurements")):
            prompt = build_assign_prompt("topmed:ecg", archetypes, [
                {"name": "AGE", "description": "Subject age"},
            ])
        assert "_rejected" in prompt
        assert "don't belong" in prompt

    def test_user_prompt_includes_parent_description(self):
        """User prompt shows parent concept name and description."""
        with patch("build_archetypes._lookup_parent_info",
                   return_value=("VTE Followup Start Age", "Age at start of VTE follow-up")):
            prompt = build_user_prompt("topmed:vte", [
                {"name": "AGE", "description": "Subject age"},
            ])
        assert "VTE Followup Start Age" in prompt
        assert "Age at start of VTE follow-up" in prompt


# ---------------------------------------------------------------------------
# write_outputs with rejection
# ---------------------------------------------------------------------------


class TestWriteOutputsRejection:
    """Tests for write_outputs handling of _rejected variables."""

    def test_rejected_vars_cleared(self, tmp_output):
        """Variables in _rejected category get concept_id set to None."""
        tmp_path, vocab_path, isa_path, llm_dir = tmp_output

        results = {
            "topmed:ecg": ArchetypeTree(categories=[
                Archetype(
                    concept_id="atrial_fibrillation",
                    name="Atrial Fibrillation",
                    description="AF detection",
                    variables=["AFIB"],
                ),
                Archetype(
                    concept_id="qt_interval",
                    name="QT Interval",
                    description="QT measurement",
                    variables=["QT_INT"],
                ),
                Archetype(
                    concept_id="_rejected",
                    name="Rejected",
                    description="Does not belong",
                    variables=["AGE", "age_visit"],
                ),
            ])
        }

        with patch("build_archetypes.OUTPUT", tmp_path), \
             patch("build_archetypes.VOCAB_PATH", vocab_path), \
             patch("build_archetypes.ISA_PATH", isa_path), \
             patch("build_archetypes.LLM_DIR", llm_dir):
            write_outputs(results)

        # Check study file
        with open(llm_dir / "phs000001.json") as f:
            study = json.load(f)
        vars_by_name = {v["name"]: v for v in study["tables"][0]["variables"]}

        # Real archetypes get re-tagged
        assert vars_by_name["AFIB"]["concept_id"] == "ncpi:ecg_atrial_fibrillation"
        assert vars_by_name["QT_INT"]["concept_id"] == "ncpi:ecg_qt_interval"

        # Rejected vars get cleared
        assert vars_by_name["AGE"]["concept_id"] is None
        assert vars_by_name["age_visit"]["concept_id"] is None

    def test_rejected_not_in_vocab(self, tmp_output):
        """_rejected category does NOT create a vocab entry or ISA edge."""
        tmp_path, vocab_path, isa_path, llm_dir = tmp_output

        results = {
            "topmed:ecg": ArchetypeTree(categories=[
                Archetype(
                    concept_id="atrial_fibrillation",
                    name="Atrial Fibrillation",
                    description="AF detection",
                    variables=["AFIB"],
                ),
                Archetype(
                    concept_id="_rejected",
                    name="Rejected",
                    description="Does not belong",
                    variables=["AGE"],
                ),
            ])
        }

        with patch("build_archetypes.OUTPUT", tmp_path), \
             patch("build_archetypes.VOCAB_PATH", vocab_path), \
             patch("build_archetypes.ISA_PATH", isa_path), \
             patch("build_archetypes.LLM_DIR", llm_dir):
            write_outputs(results)

        # Check vocab — should have archetype but not _rejected
        with open(vocab_path) as f:
            vocab = json.load(f)
        vocab_ids = {e["concept_id"] for e in vocab}
        assert "ncpi:ecg_atrial_fibrillation" in vocab_ids
        assert "ncpi:ecg__rejected" not in vocab_ids
        assert "_rejected" not in vocab_ids

        # Check ISA — no _rejected edge
        with open(isa_path) as f:
            isa = json.load(f)
        isa_children = {e["child"] for e in isa}
        assert "ncpi:ecg_atrial_fibrillation" in isa_children
        assert "ncpi:ecg__rejected" not in isa_children

    def test_no_results_no_crash(self, tmp_output):
        """Empty results dict doesn't crash."""
        tmp_path, vocab_path, isa_path, llm_dir = tmp_output
        with patch("build_archetypes.OUTPUT", tmp_path), \
             patch("build_archetypes.VOCAB_PATH", vocab_path), \
             patch("build_archetypes.ISA_PATH", isa_path), \
             patch("build_archetypes.LLM_DIR", llm_dir):
            write_outputs({})  # Should print "No results" and return
