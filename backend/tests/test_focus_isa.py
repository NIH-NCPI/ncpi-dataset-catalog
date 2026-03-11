"""Tests for focus ISA hierarchy: edge computation and dedup logic."""

from __future__ import annotations

from types import SimpleNamespace

from concept_search.build_focus_categories import _compute_isa_edges
from concept_search.resolve_agent import _dedup_focus_values

# ---------------------------------------------------------------------------
# _compute_isa_edges
# ---------------------------------------------------------------------------


def _make_result(term: str, tree_numbers: list[str]) -> dict:
    """Build a minimal result dict for _compute_isa_edges."""
    return {"term": term, "tree_numbers": tree_numbers}


class TestComputeIsaEdges:
    """Tests for _compute_isa_edges: MeSH tree → ISA edge derivation."""

    def test_simple_parent_child(self) -> None:
        """Direct parent-child: C04.588 is a child of C04."""
        results = [
            _make_result("Neoplasms", ["C04"]),
            _make_result("Digestive System Neoplasms", ["C04.588"]),
        ]
        edges = _compute_isa_edges(results)
        assert edges == [{"child": "Digestive System Neoplasms", "parent": "Neoplasms"}]

    def test_nearest_ancestor_only(self) -> None:
        """Walk stops at the nearest catalog ancestor, not the root."""
        results = [
            _make_result("Neoplasms", ["C04"]),
            _make_result("Pancreatic Neoplasms", ["C04.588.274"]),
            _make_result("Carcinoma, Pancreatic Ductal", ["C04.588.274.761"]),
        ]
        edges = _compute_isa_edges(results)
        edge_tuples = {(e["child"], e["parent"]) for e in edges}
        # Carcinoma → Pancreatic Neoplasms (nearest), NOT → Neoplasms
        assert ("Carcinoma, Pancreatic Ductal", "Pancreatic Neoplasms") in edge_tuples
        assert ("Carcinoma, Pancreatic Ductal", "Neoplasms") not in edge_tuples
        # Pancreatic Neoplasms → Neoplasms
        assert ("Pancreatic Neoplasms", "Neoplasms") in edge_tuples

    def test_polyhierarchy_multiple_parents(self) -> None:
        """A term with two tree numbers can have two parents."""
        results = [
            _make_result("Endocrine Diseases", ["C19"]),
            _make_result("Urogenital Diseases", ["C12"]),
            _make_result("PCOS", ["C19.100", "C12.200"]),
        ]
        edges = _compute_isa_edges(results)
        edge_tuples = {(e["child"], e["parent"]) for e in edges}
        assert ("PCOS", "Endocrine Diseases") in edge_tuples
        assert ("PCOS", "Urogenital Diseases") in edge_tuples

    def test_no_self_edges(self) -> None:
        """A term should not create an edge to itself."""
        results = [
            _make_result("Neoplasms", ["C04"]),
            _make_result("Lung Neoplasms", ["C04.588"]),
        ]
        edges = _compute_isa_edges(results)
        for e in edges:
            assert e["child"] != e["parent"]

    def test_no_ancestor_in_catalog(self) -> None:
        """Term with no catalog ancestor produces no edges."""
        results = [
            _make_result("Orphan Term", ["Z99.100.200"]),
        ]
        edges = _compute_isa_edges(results)
        assert edges == []

    def test_empty_tree_numbers(self) -> None:
        """Term with no tree numbers produces no edges."""
        results = [
            _make_result("Unknown Term", []),
            _make_result("Neoplasms", ["C04"]),
        ]
        edges = _compute_isa_edges(results)
        assert edges == []

    def test_sibling_terms_no_edge(self) -> None:
        """Siblings (same depth, shared parent) don't create edges to each other."""
        results = [
            _make_result("Neoplasms", ["C04"]),
            _make_result("Alpha", ["C04.100"]),
            _make_result("Beta", ["C04.200"]),
        ]
        edges = _compute_isa_edges(results)
        edge_tuples = {(e["child"], e["parent"]) for e in edges}
        assert ("Alpha", "Beta") not in edge_tuples
        assert ("Beta", "Alpha") not in edge_tuples
        # Both are children of Neoplasms
        assert ("Alpha", "Neoplasms") in edge_tuples
        assert ("Beta", "Neoplasms") in edge_tuples

    def test_output_sorted(self) -> None:
        """Output is sorted by (parent, child)."""
        results = [
            _make_result("Root", ["A01"]),
            _make_result("Zebra", ["A01.300"]),
            _make_result("Apple", ["A01.100"]),
        ]
        edges = _compute_isa_edges(results)
        keys = [(e["parent"], e["child"]) for e in edges]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# _dedup_focus_values
# ---------------------------------------------------------------------------


def _make_index_with_isa(children_map: dict[str, list[str]]) -> object:
    """Build a mock index with _focus_isa_children."""
    return SimpleNamespace(_focus_isa_children=children_map)


class TestDedupFocusValues:
    """Tests for _dedup_focus_values: cull descendants from resolved values."""

    def test_parent_subsumes_child(self) -> None:
        """Child is removed when parent is present."""
        index = _make_index_with_isa(
            {
                "Lung Neoplasms": ["Adenocarcinoma of Lung"],
            }
        )
        result = _dedup_focus_values(["Lung Neoplasms", "Adenocarcinoma of Lung"], index)
        assert result == ["Lung Neoplasms"]

    def test_grandchild_removed(self) -> None:
        """Transitive descendants are also removed."""
        index = _make_index_with_isa(
            {
                "A": ["B"],
                "B": ["C"],
            }
        )
        result = _dedup_focus_values(["A", "C"], index)
        assert result == ["A"]

    def test_unrelated_terms_kept(self) -> None:
        """Terms with no ISA relationship are all kept."""
        index = _make_index_with_isa(
            {
                "X": ["X1"],
                "Y": ["Y1"],
            }
        )
        result = _dedup_focus_values(["X", "Y"], index)
        assert result == ["X", "Y"]

    def test_single_value_passthrough(self) -> None:
        """Single value list is returned as-is (no dedup needed)."""
        index = _make_index_with_isa({"A": ["B"]})
        result = _dedup_focus_values(["B"], index)
        assert result == ["B"]

    def test_empty_isa_children(self) -> None:
        """No ISA data — values returned unchanged."""
        index = _make_index_with_isa({})
        result = _dedup_focus_values(["A", "B"], index)
        assert result == ["A", "B"]

    def test_no_isa_attribute(self) -> None:
        """Index without _focus_isa_children — values returned unchanged."""
        index = SimpleNamespace()
        result = _dedup_focus_values(["A", "B"], index)
        assert result == ["A", "B"]

    def test_preserves_order(self) -> None:
        """Surviving values keep their original order."""
        index = _make_index_with_isa(
            {
                "Parent": ["Child1", "Child2"],
            }
        )
        result = _dedup_focus_values(["Child2", "Parent", "Child1"], index)
        assert result == ["Parent"]

    def test_cycle_does_not_loop(self) -> None:
        """Cycle in ISA graph terminates without infinite loop."""
        index = _make_index_with_isa(
            {
                "A": ["B"],
                "B": ["A"],
            }
        )
        # Cycles shouldn't happen in practice, but the function must not hang.
        # Both terms are descendants of each other, so both get removed.
        result = _dedup_focus_values(["A", "B"], index)
        assert result == []
