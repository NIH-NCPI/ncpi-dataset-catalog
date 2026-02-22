"""Tests for consent_logic module."""

from __future__ import annotations

from concept_search.consent_logic import (
    ParsedConsentCode,
    compute_eligible_codes,
    expand_disease,
    parse_consent_code,
    resolve_disease_name,
)

# ---------------------------------------------------------------------------
# Fixtures — realistic consent code list
# ---------------------------------------------------------------------------

SAMPLE_CODES = [
    "DS-BRCA",
    "DS-CA",
    "DS-CA-IRB",
    "DS-CVD",
    "DS-CVD-IRB",
    "DS-CVD-NPU",
    "DS-DIAB",
    "DS-DIAB-IRB",
    "DS-T1D",
    "DS-T2D",
    "GRU",
    "GRU-IRB",
    "GRU-NPU",
    "HMB",
    "HMB-IRB",
    "HMB-NPU",
    "HMP",
    "HR",
]


# ---------------------------------------------------------------------------
# parse_consent_code
# ---------------------------------------------------------------------------


class TestParseConsentCode:
    def test_simple_base(self):
        result = parse_consent_code("GRU")
        assert result == ParsedConsentCode(base="GRU")

    def test_base_with_modifier(self):
        result = parse_consent_code("GRU-IRB")
        assert result.base == "GRU"
        assert result.modifiers == {"IRB"}
        assert result.disease is None

    def test_base_with_multiple_modifiers(self):
        result = parse_consent_code("GRU-IRB-NPU")
        assert result.base == "GRU"
        assert result.modifiers == {"IRB", "NPU"}

    def test_ds_with_disease(self):
        result = parse_consent_code("DS-CVD")
        assert result.base == "DS"
        assert result.disease == "CVD"
        assert result.modifiers == set()

    def test_ds_with_disease_and_modifier(self):
        result = parse_consent_code("DS-CVD-IRB")
        assert result.base == "DS"
        assert result.disease == "CVD"
        assert result.modifiers == {"IRB"}

    def test_ds_with_disease_and_multiple_modifiers(self):
        result = parse_consent_code("DS-CVD-IRB-NPU")
        assert result.base == "DS"
        assert result.disease == "CVD"
        assert result.modifiers == {"IRB", "NPU"}

    def test_ds_with_compound_disease(self):
        # Some disease abbreviations could be multi-part (not common, but test)
        result = parse_consent_code("DS-BRCA")
        assert result.base == "DS"
        assert result.disease == "BRCA"

    def test_hmb_with_modifier(self):
        result = parse_consent_code("HMB-IRB")
        assert result.base == "HMB"
        assert result.disease is None
        assert result.modifiers == {"IRB"}

    def test_npu_standalone(self):
        result = parse_consent_code("NPU")
        assert result.base == "NPU"
        assert result.disease is None


# ---------------------------------------------------------------------------
# expand_disease
# ---------------------------------------------------------------------------


class TestExpandDisease:
    def test_parent_with_children(self):
        result = expand_disease("DIAB")
        assert "DIAB" in result
        assert "T1D" in result
        assert "T2D" in result
        assert "DRC" in result
        assert "T1DR" in result
        assert "IR" in result

    def test_cancer_hierarchy(self):
        result = expand_disease("CA")
        assert "CA" in result
        assert "BRCA" in result
        assert "LC" in result
        assert len(result) == 21  # CA + 20 children

    def test_cvd_hierarchy(self):
        result = expand_disease("CVD")
        assert "CVD" in result
        assert "AF" in result
        assert "CHD" in result

    def test_leaf_disease(self):
        result = expand_disease("T1D")
        assert result == {"T1D"}

    def test_unknown_disease(self):
        result = expand_disease("UNKNOWN")
        assert result == {"UNKNOWN"}


# ---------------------------------------------------------------------------
# compute_eligible_codes — explicit code path
# ---------------------------------------------------------------------------


class TestExplicitCode:
    def test_gru_prefix(self):
        result = compute_eligible_codes(SAMPLE_CODES, explicit_code="GRU")
        assert "GRU" in result
        assert "GRU-IRB" in result
        assert "GRU-NPU" in result
        assert "HMB" not in result

    def test_hmb_prefix(self):
        result = compute_eligible_codes(SAMPLE_CODES, explicit_code="HMB")
        assert "HMB" in result
        assert "HMB-IRB" in result
        assert "HMB-NPU" in result

    def test_explicit_with_npu_filter(self):
        result = compute_eligible_codes(
            SAMPLE_CODES, explicit_code="GRU", is_nonprofit=False
        )
        assert "GRU" in result
        assert "GRU-IRB" in result
        assert "GRU-NPU" not in result

    def test_ds_cvd_prefix(self):
        result = compute_eligible_codes(SAMPLE_CODES, explicit_code="DS-CVD")
        assert "DS-CVD" in result
        assert "DS-CVD-IRB" in result
        assert "DS-CVD-NPU" in result
        assert "DS-DIAB" not in result

    def test_exact_match(self):
        result = compute_eligible_codes(SAMPLE_CODES, explicit_code="HMB-IRB")
        assert result == ["HMB-IRB"]

    def test_case_insensitive(self):
        result = compute_eligible_codes(SAMPLE_CODES, explicit_code="gru")
        assert "GRU" in result
        assert "GRU-IRB" in result


# ---------------------------------------------------------------------------
# compute_eligible_codes — purpose path
# ---------------------------------------------------------------------------


class TestPurposePath:
    def test_general_purpose_returns_gru_only(self):
        """General/unrestricted research → GRU only.

        GRU = "no restrictions on use" — eligible for anything.
        HMB = "health/medical/biomedical only" — NOT eligible for
        general-purpose research (e.g. social science, population
        genetics unrelated to health).
        """
        result = compute_eligible_codes(SAMPLE_CODES, purpose="general")
        for code in result:
            assert code.startswith("GRU"), f"general purpose should only return GRU, got {code}"
        # Explicit exclusion checks
        assert not any(c.startswith("HMB") for c in result), "HMB should NOT appear for general purpose"
        assert not any(c.startswith("DS-") for c in result), "DS should NOT appear for general purpose"

    def test_health_purpose_returns_gru_and_hmb(self):
        """Health/medical/biomedical research → GRU + HMB + HMP + HR.

        GRU: always eligible (no restrictions).
        HMB: eligible because the purpose IS health/medical.
        HMP: health + population studies — also eligible.
        HR:  health research — also eligible.
        DS:  NOT eligible without a specific disease.
        """
        result = compute_eligible_codes(SAMPLE_CODES, purpose="health")
        bases = {parse_consent_code(c).base for c in result}
        assert "GRU" in bases
        assert "HMB" in bases
        assert "HMP" in bases
        assert "HR" in bases
        # DS codes should NOT appear for health purpose without disease
        assert not any(c.startswith("DS-") for c in result), "DS should NOT appear without a disease"

    def test_health_vs_general_disambiguation(self):
        """Verify that HMB appears for health but NOT for general."""
        general = compute_eligible_codes(SAMPLE_CODES, purpose="general")
        health = compute_eligible_codes(SAMPLE_CODES, purpose="health")
        general_bases = {parse_consent_code(c).base for c in general}
        health_bases = {parse_consent_code(c).base for c in health}
        # GRU in both
        assert "GRU" in general_bases
        assert "GRU" in health_bases
        # HMB only in health
        assert "HMB" not in general_bases, "HMB must NOT appear for general purpose"
        assert "HMB" in health_bases, "HMB must appear for health purpose"

    def test_disease_purpose_diabetes(self):
        result = compute_eligible_codes(
            SAMPLE_CODES, purpose="disease", disease="DIAB"
        )
        bases = {parse_consent_code(c).base for c in result}
        assert "GRU" in bases
        assert "HMB" in bases
        # DS-DIAB family should be included
        assert "DS-DIAB" in result
        assert "DS-DIAB-IRB" in result
        # DS-T1D and DS-T2D should be included (children of DIAB)
        assert "DS-T1D" in result
        assert "DS-T2D" in result
        # DS-CVD should NOT be included
        assert "DS-CVD" not in result

    def test_disease_purpose_child_disease(self):
        """T1D is a child of DIAB; querying T1D should match DS-T1D and DS-DIAB."""
        result = compute_eligible_codes(
            SAMPLE_CODES, purpose="disease", disease="T1D"
        )
        # DS-T1D: direct match
        assert "DS-T1D" in result
        # DS-DIAB: T1D ∈ expand_disease("DIAB"), and DIAB ∈ expand_disease("T1D")
        # Wait — expand_disease("T1D") = {"T1D"} because it's a leaf.
        # But expand_disease("DIAB") includes T1D, so code_diseases & user_diseases
        # = expand_disease("DIAB") & {"T1D"} = {"T1D"} which is truthy.
        assert "DS-DIAB" in result
        assert "DS-DIAB-IRB" in result

    def test_disease_purpose_cancer_includes_subcancers(self):
        result = compute_eligible_codes(
            SAMPLE_CODES, purpose="disease", disease="CA"
        )
        assert "DS-CA" in result
        assert "DS-CA-IRB" in result
        # BRCA is a child of CA
        assert "DS-BRCA" in result

    def test_npu_filter_for_profit(self):
        result = compute_eligible_codes(
            SAMPLE_CODES, purpose="health", is_nonprofit=False
        )
        for code in result:
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers

    def test_npu_filter_none_includes_all(self):
        """is_nonprofit=None (default) should include NPU codes."""
        result = compute_eligible_codes(SAMPLE_CODES, purpose="health")
        assert "HMB-NPU" in result
        assert "GRU-NPU" in result

    def test_empty_codes_list(self):
        result = compute_eligible_codes([], purpose="general")
        assert result == []

    def test_results_are_sorted(self):
        result = compute_eligible_codes(SAMPLE_CODES, purpose="health")
        assert result == sorted(result)

    def test_disease_only_excludes_gru_hmb(self):
        result = compute_eligible_codes(
            SAMPLE_CODES, purpose="disease", disease="DIAB", disease_only=True
        )
        for code in result:
            assert code.startswith("DS-"), f"Expected only DS-* codes, got {code}"
        assert "DS-DIAB" in result
        assert "DS-DIAB-IRB" in result
        assert "DS-T1D" in result
        assert "GRU" not in result
        assert "HMB" not in result

    def test_disease_only_with_npu_filter(self):
        result = compute_eligible_codes(
            SAMPLE_CODES,
            purpose="disease",
            disease="CVD",
            disease_only=True,
            is_nonprofit=False,
        )
        for code in result:
            assert code.startswith("DS-")
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers
        assert "DS-CVD" in result
        assert "DS-CVD-IRB" in result
        assert "DS-CVD-NPU" not in result

    def test_disease_only_no_effect_on_explicit_code(self):
        """disease_only should not affect explicit_code path."""
        result = compute_eligible_codes(
            SAMPLE_CODES, explicit_code="GRU", disease_only=True
        )
        assert "GRU" in result
        assert "GRU-IRB" in result


# ---------------------------------------------------------------------------
# resolve_disease_name
# ---------------------------------------------------------------------------


class TestResolveDiseaseName:
    def test_abbreviation_direct(self):
        assert resolve_disease_name("DIAB") == "DIAB"

    def test_abbreviation_case_insensitive(self):
        assert resolve_disease_name("diab") == "DIAB"

    def test_full_name(self):
        assert resolve_disease_name("Diabetes") == "DIAB"

    def test_full_name_exact(self):
        assert resolve_disease_name("Cancer") == "CA"

    def test_partial_name(self):
        assert resolve_disease_name("diabetes") == "DIAB"

    def test_breast_cancer(self):
        assert resolve_disease_name("Breast Cancer") == "BRCA"

    def test_type_1_diabetes(self):
        assert resolve_disease_name("Type 1 Diabetes") == "T1D"

    def test_cardiovascular(self):
        assert resolve_disease_name("Cardiovascular Disease") == "CVD"

    def test_unknown(self):
        assert resolve_disease_name("something random") is None

    def test_cancer_substring(self):
        result = resolve_disease_name("cancer")
        # Should match "Cancer" → CA
        assert result == "CA"

    def test_cardiovascular_prefers_shortest(self):
        # "cardiovascular" matches multiple TSV entries (CCSD, CVD, etc.)
        # Should prefer "Cardiovascular Disease" (CVD) over longer names
        assert resolve_disease_name("cardiovascular") == "CVD"

    def test_possessive_alzheimers(self):
        # "Alzheimer's" should strip possessive and match "Alzheimer Disease"
        assert resolve_disease_name("Alzheimer's") == "ALZ"

    def test_possessive_parkinsons(self):
        assert resolve_disease_name("Parkinson's") == "PD"
