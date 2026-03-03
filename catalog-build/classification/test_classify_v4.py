"""Tests for classify_v4.py — multi-table batching and namespace prefixing."""

import pytest

from models import ParsedTable

from classify_v4 import (
    DEFAULT_NAMESPACE,
    _namespace_concept_id,
    format_batch_prompt,
    pack_batches,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table(name, n_vars, desc=""):
    """Build a ParsedTable stub with n variables."""
    variables = [
        {"name": f"VAR{i}", "description": f"Variable {i}"}
        for i in range(n_vars)
    ]
    return ParsedTable(
        study_id="phs000001",
        dataset_id="pht000001",
        table_name=name,
        study_name="Test Study",
        description=desc,
        variables=variables,
        variable_count=n_vars,
        file_path="test",
    )


# ---------------------------------------------------------------------------
# pack_batches tests
# ---------------------------------------------------------------------------


class TestPackBatches:
    """Tests for the multi-table batch packing algorithm."""

    def test_empty(self):
        """Empty input produces empty output."""
        assert pack_batches([]) == []

    def test_single_small_table(self):
        """One small table produces one batch with one item."""
        t = _table("t1", 5)
        items = [(t, t.variables)]
        result = pack_batches(items)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_multiple_small_tables_packed(self):
        """Several small tables fit into one batch."""
        tables = [_table(f"t{i}", 10) for i in range(5)]
        items = [(t, t.variables) for t in tables]
        result = pack_batches(items)
        # 5 * 10 = 50 vars, fits in one batch of 100
        assert len(result) == 1
        assert len(result[0]) == 5

    def test_small_tables_overflow_to_two_batches(self):
        """Tables that exceed 100 vars total split into multiple batches."""
        tables = [_table(f"t{i}", 20) for i in range(6)]
        items = [(t, t.variables) for t in tables]
        result = pack_batches(items)
        # 6 * 20 = 120 vars, needs 2 batches
        assert len(result) == 2
        total_items = sum(len(b) for b in result)
        assert total_items == 6

    def test_large_table_alone(self):
        """A 100-var table gets its own batch."""
        t = _table("big", 100)
        items = [(t, t.variables)]
        result = pack_batches(items)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_mix_large_and_small(self):
        """Large and small tables pack correctly."""
        big = _table("big", 80)
        small1 = _table("s1", 10)
        small2 = _table("s2", 15)
        small3 = _table("s3", 10)
        items = [
            (big, big.variables),
            (small1, small1.variables),
            (small2, small2.variables),
            (small3, small3.variables),
        ]
        result = pack_batches(items)
        # big(80) + s1(10) = 90 fits; s2(15) + s3(10) = 25 second batch
        assert len(result) == 2
        batch_sizes = sorted(sum(len(v) for _, v in b) for b in result)
        assert batch_sizes[0] <= 100
        assert batch_sizes[1] <= 100


# ---------------------------------------------------------------------------
# format_batch_prompt tests
# ---------------------------------------------------------------------------


class TestFormatBatchPrompt:
    """Tests for multi-table prompt formatting."""

    def test_single_table(self):
        """Single table prompt includes study and table context."""
        t = _table("demographics", 2, desc="Participant demographics")
        prompt = format_batch_prompt("phs000001", "Test Study", [(t, t.variables)])
        assert "phs000001" in prompt
        assert "Test Study" in prompt
        assert "TABLE: demographics" in prompt
        assert "Participant demographics" in prompt
        assert "VAR0" in prompt
        assert "VAR1" in prompt

    def test_multiple_tables(self):
        """Multi-table prompt has all tables with clear boundaries."""
        t1 = _table("labs", 2, desc="Lab results")
        t2 = _table("vitals", 3, desc="Vital signs")
        prompt = format_batch_prompt(
            "phs000001", "Test Study",
            [(t1, t1.variables), (t2, t2.variables)],
        )
        assert "TABLE: labs" in prompt
        assert "TABLE: vitals" in prompt
        assert "(2 vars)" in prompt
        assert "(3 vars)" in prompt

    def test_no_description(self):
        """Table with no description shows (none)."""
        t = _table("misc", 1)
        prompt = format_batch_prompt("phs000001", "Test", [(t, t.variables)])
        assert "(none)" in prompt


# ---------------------------------------------------------------------------
# Namespace prefix tests
# ---------------------------------------------------------------------------


class TestNamespacePrefix:
    """Tests that concept_ids get namespaced in output."""

    def test_namespace_constant(self):
        """DEFAULT_NAMESPACE is set to topmed."""
        assert DEFAULT_NAMESPACE == "topmed"

    def test_namespace_format(self):
        """Namespaced concept_id follows 'namespace:bare_id' format."""
        bare_id = "bp_systolic"
        namespaced = f"{DEFAULT_NAMESPACE}:{bare_id}"
        assert namespaced == "topmed:bp_systolic"
        assert ":" in namespaced
        assert namespaced.split(":")[0] == "topmed"
        assert namespaced.split(":")[1] == bare_id

    def test_namespace_helper_bare_id(self):
        """Bare IDs get topmed: prefix."""
        assert _namespace_concept_id("bp_systolic") == "topmed:bp_systolic"

    def test_namespace_helper_phenx_passthrough(self):
        """PhenX IDs with existing prefix are passed through."""
        assert _namespace_concept_id("phenx:spirometry") == "phenx:spirometry"

    def test_namespace_helper_any_prefix_passthrough(self):
        """Any existing namespace prefix is preserved."""
        assert _namespace_concept_id("ncpi:biomarkers") == "ncpi:biomarkers"
