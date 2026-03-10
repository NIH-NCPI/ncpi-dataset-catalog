"""Tests for consent_logic module."""

from __future__ import annotations

from concept_search.consent_logic import (
    ParsedConsentCode,
    compute_eligible_codes,
    expand_consent_tags,
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


# ---------------------------------------------------------------------------
# Extended fixture — larger realistic code list with mixed modifiers
# ---------------------------------------------------------------------------

EXTENDED_CODES = [
    # GRU family
    "GRU",
    "GRU-IRB",
    "GRU-NPU",
    "GRU-IRB-NPU",
    "GRU-IRB-PUB",
    "GRU-PUB",
    "GRU-COL",
    # HMB family
    "HMB",
    "HMB-IRB",
    "HMB-NPU",
    "HMB-IRB-NPU",
    "HMB-PUB",
    "HMB-MDS",
    "HMB-GSO",
    "HMB-COL-NPU-GSO",
    # HMP and HR
    "HMP",
    "HR",
    # Disease-specific: cancer hierarchy
    "DS-CA",
    "DS-CA-IRB",
    "DS-CA-NPU",
    "DS-CA-MDS",
    "DS-CA-IRB-NPU-GSO",
    "DS-BRCA",
    "DS-BRCA-MDS",
    "DS-BRCA-NPU-MDS",
    "DS-OVCA",
    "DS-OVCA-NPU",
    "DS-LC",
    "DS-LC-NPU",
    "DS-PC",
    "DS-PC-MDS",
    # Disease-specific: CVD hierarchy
    "DS-CVD",
    "DS-CVD-IRB",
    "DS-CVD-NPU",
    "DS-CVD-IRB-NPU-MDS",
    "DS-AF-IRB-RD",
    "DS-CHD",
    "DS-STK-IRB-RD",
    # Disease-specific: diabetes hierarchy
    "DS-DIAB",
    "DS-DIAB-IRB",
    "DS-DIAB-NPU",
    "DS-T1D",
    "DS-T2D",
    "DS-T2D-IRB-RD",
    "DS-T1DR-IRB-RD",
    "DS-IR",
    "DS-IR-IRB",
    # Disease-specific: other diseases (no hierarchy)
    "DS-ASTHMA",
    "DS-ASTHMA-IRB-COL",
    "DS-COPD",
    "DS-COPD-NPU",
    "DS-SCD",
    "DS-HIV-IRB",
    # Other base codes
    "NPU",
    "CADM",
    "IRU",
]


# ---------------------------------------------------------------------------
# For-profit vs non-profit (NPU filtering)
# ---------------------------------------------------------------------------


class TestForProfitNonProfit:
    """NPU modifier handling: for-profit orgs cannot use NPU-modified codes.

    GA4GH DUO principle: profit status and base code eligibility are
    independent axes.  The base code (GRU/HMB/DS) controls *what kind*
    of research is permitted.  The NPU modifier controls *who* can access
    the data.  A for-profit company can use HMB and DS data — the only
    effect of is_nonprofit=False is excluding codes with the -NPU modifier.
    """

    def test_for_profit_pharma_cancer_research(self):
        """GA4GH: a for-profit pharma company doing cancer research gets
        GRU + HMB + HMP + HR + DS-CA (all minus -NPU variants).

        Profit status only filters NPU — it does NOT restrict base codes.
        """
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", is_nonprofit=False
        )
        bases = {parse_consent_code(c).base for c in result}
        # For-profit still gets all three base code families
        assert "GRU" in bases, "For-profit can use GRU data"
        assert "HMB" in bases, "For-profit can use HMB data (it's health research)"
        assert "DS" in bases, "For-profit can use DS-CA data (disease matches)"
        assert "HMP" in bases, "For-profit can use HMP data"
        # Specific inclusions
        assert "GRU" in result
        assert "GRU-IRB" in result
        assert "HMB" in result
        assert "HMB-IRB" in result
        assert "DS-CA" in result
        assert "DS-CA-IRB" in result
        assert "DS-BRCA" in result
        # NPU variants excluded
        assert "GRU-NPU" not in result
        assert "HMB-NPU" not in result
        assert "DS-CA-NPU" not in result
        assert "DS-BRCA-NPU-MDS" not in result

    def test_for_profit_vs_nonprofit_same_bases(self):
        """For-profit and non-profit get the same base code families;
        the only difference is NPU-modified codes are excluded for for-profit."""
        for_profit = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", is_nonprofit=False
        )
        nonprofit = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", is_nonprofit=True
        )
        fp_bases = {parse_consent_code(c).base for c in for_profit}
        np_bases = {parse_consent_code(c).base for c in nonprofit}
        assert fp_bases == np_bases, (
            f"Same base codes for both; only NPU variants differ. "
            f"for-profit bases={fp_bases}, nonprofit bases={np_bases}"
        )
        # Non-profit has strictly more codes (the NPU variants)
        assert set(for_profit).issubset(set(nonprofit))
        assert len(nonprofit) > len(for_profit)

    def test_for_profit_general_excludes_npu(self):
        """For-profit + general purpose: GRU codes only, no -NPU variants."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="general", is_nonprofit=False
        )
        for code in result:
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers, f"NPU code {code} should be excluded for-profit"
            assert parsed.base == "GRU", f"Only GRU expected for general purpose, got {code}"
        assert "GRU" in result
        assert "GRU-IRB" in result
        assert "GRU-NPU" not in result
        assert "GRU-IRB-NPU" not in result

    def test_for_profit_health_excludes_npu(self):
        """For-profit + health purpose: GRU + HMB families, no -NPU variants."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="health", is_nonprofit=False
        )
        for code in result:
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers, f"NPU code {code} excluded for-profit"
        assert "GRU" in result
        assert "HMB" in result
        assert "HMB-IRB" in result
        assert "GRU-NPU" not in result
        assert "HMB-NPU" not in result
        assert "HMB-IRB-NPU" not in result
        assert "HMB-COL-NPU-GSO" not in result

    def test_for_profit_disease_excludes_npu(self):
        """For-profit + disease purpose: matching DS codes minus NPU variants."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", is_nonprofit=False
        )
        for code in result:
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers, f"NPU code {code} excluded for-profit"
        assert "DS-CA" in result
        assert "DS-CA-IRB" in result
        assert "DS-CA-NPU" not in result
        assert "DS-CA-IRB-NPU-GSO" not in result
        assert "DS-BRCA" in result
        assert "DS-BRCA-NPU-MDS" not in result
        assert "DS-OVCA-NPU" not in result
        assert "DS-LC-NPU" not in result

    def test_nonprofit_true_includes_npu(self):
        """Non-profit (is_nonprofit=True) includes NPU codes."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="health", is_nonprofit=True
        )
        assert "GRU-NPU" in result
        assert "HMB-NPU" in result
        assert "HMB-IRB-NPU" in result

    def test_nonprofit_none_includes_npu(self):
        """Default (is_nonprofit=None) includes NPU codes."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="health")
        assert "GRU-NPU" in result
        assert "HMB-NPU" in result

    def test_for_profit_explicit_code_excludes_npu(self):
        """Explicit code path + for-profit still filters NPU."""
        result = compute_eligible_codes(
            EXTENDED_CODES, explicit_code="HMB", is_nonprofit=False
        )
        assert "HMB" in result
        assert "HMB-IRB" in result
        assert "HMB-PUB" in result
        assert "HMB-NPU" not in result
        assert "HMB-IRB-NPU" not in result
        assert "HMB-COL-NPU-GSO" not in result


# ---------------------------------------------------------------------------
# GRU vs HMB hierarchy — general vs health/medical/biomedical
# ---------------------------------------------------------------------------


class TestGruHmbHierarchy:
    """GRU (broadest) ⊇ HMB (health) ⊇ DS (disease-specific)."""

    def test_general_is_gru_only(self):
        """General research: only GRU codes are eligible (broadest consent)."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="general")
        bases = {parse_consent_code(c).base for c in result}
        assert bases == {"GRU"}

    def test_health_adds_hmb_hmp_hr(self):
        """Health research: GRU + HMB + HMP + HR, but not DS."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="health")
        bases = {parse_consent_code(c).base for c in result}
        assert "GRU" in bases
        assert "HMB" in bases
        assert "HMP" in bases
        assert "HR" in bases
        assert "DS" not in bases

    def test_disease_adds_matching_ds(self):
        """Disease research: GRU + HMB + HMP + HR + matching DS codes."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="DIAB"
        )
        bases = {parse_consent_code(c).base for c in result}
        assert "GRU" in bases
        assert "HMB" in bases
        assert "DS" in bases
        # Verify non-matching DS excluded
        assert "DS-CA" not in result
        assert "DS-CVD" not in result
        assert "DS-ASTHMA" not in result

    def test_general_subset_of_health(self):
        """Every general-eligible code is also health-eligible."""
        general = set(compute_eligible_codes(EXTENDED_CODES, purpose="general"))
        health = set(compute_eligible_codes(EXTENDED_CODES, purpose="health"))
        assert general.issubset(health), f"general not ⊆ health: {general - health}"

    def test_health_subset_of_disease(self):
        """Every health-eligible code is also disease-eligible (with a disease)."""
        health = set(compute_eligible_codes(EXTENDED_CODES, purpose="health"))
        disease = set(
            compute_eligible_codes(EXTENDED_CODES, purpose="disease", disease="DIAB")
        )
        assert health.issubset(disease), f"health not ⊆ disease: {health - disease}"

    def test_cadm_iru_never_eligible(self):
        """CADM, IRU, standalone NPU are not primary consent → never eligible."""
        for purpose in ("general", "health", "disease"):
            kwargs = {"purpose": purpose}
            if purpose == "disease":
                kwargs["disease"] = "CA"
            result = compute_eligible_codes(EXTENDED_CODES, **kwargs)
            bases = {parse_consent_code(c).base for c in result}
            assert "CADM" not in bases, f"CADM should not be eligible for {purpose}"
            assert "IRU" not in bases, f"IRU should not be eligible for {purpose}"
            # Standalone "NPU" (as base, not modifier) isn't a consent grant
            assert "NPU" not in bases, f"NPU as base should not be eligible for {purpose}"


# ---------------------------------------------------------------------------
# Disease-specific codes — hierarchy expansion
# ---------------------------------------------------------------------------


class TestDiseaseHierarchy:
    """DS codes and bidirectional disease hierarchy matching."""

    def test_cancer_parent_matches_all_subcancers(self):
        """Searching disease=CA includes DS-BRCA, DS-OVCA, DS-LC, DS-PC, etc."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "CA" in ds_diseases
        assert "BRCA" in ds_diseases
        assert "OVCA" in ds_diseases
        assert "LC" in ds_diseases
        assert "PC" in ds_diseases
        # Non-cancer DS codes excluded
        assert "CVD" not in ds_diseases
        assert "DIAB" not in ds_diseases

    def test_subcancer_matches_parent(self):
        """Searching disease=BRCA matches DS-BRCA and DS-CA (BRCA ∈ CA children)."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="BRCA"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "BRCA" in ds_diseases, "Direct match"
        assert "CA" in ds_diseases, "Parent match (BRCA is child of CA)"
        # Other cancer children should NOT match
        assert "OVCA" not in ds_diseases
        assert "LC" not in ds_diseases

    def test_cvd_hierarchy(self):
        """CVD parent matches AF, CHD, STK (those present in fixture)."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CVD"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "CVD" in ds_diseases
        assert "AF" in ds_diseases  # DS-AF-IRB-RD
        assert "CHD" in ds_diseases  # DS-CHD
        assert "STK" in ds_diseases  # DS-STK-IRB-RD

    def test_diabetes_child_t1d_matches_parent(self):
        """T1D (leaf) matches DS-T1D and DS-DIAB (parent)."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="T1D"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "T1D" in ds_diseases
        assert "DIAB" in ds_diseases
        # Other diabetes children NOT matched (T1D doesn't expand to T2D)
        assert "T2D" not in ds_diseases

    def test_diabetes_parent_matches_children_in_fixture(self):
        """DIAB matches DS-DIAB, DS-T1D, DS-T2D, DS-T1DR, DS-IR (those in fixture)."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="DIAB"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "DIAB" in ds_diseases
        assert "T1D" in ds_diseases
        assert "T2D" in ds_diseases
        assert "T1DR" in ds_diseases
        assert "IR" in ds_diseases

    def test_unrelated_diseases_excluded(self):
        """Diabetes search excludes cancer and CVD."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="DIAB"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "CA" not in ds_diseases
        assert "BRCA" not in ds_diseases
        assert "CVD" not in ds_diseases
        assert "ASTHMA" not in ds_diseases
        assert "COPD" not in ds_diseases

    def test_no_hierarchy_disease(self):
        """Diseases with no hierarchy match only themselves."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="ASTHMA"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert ds_diseases == {"ASTHMA"}


# ---------------------------------------------------------------------------
# IRB modifier handling
# ---------------------------------------------------------------------------


class TestIrbModifier:
    """IRB is a requirement (requestor needs IRB approval), not a restriction.
    IRB-modified codes should always be included when the base code is eligible."""

    def test_irb_codes_included_general(self):
        """GRU-IRB is eligible for general purpose (IRB is a requirement, not restriction)."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="general")
        assert "GRU-IRB" in result
        assert "GRU-IRB-PUB" in result

    def test_irb_codes_included_health(self):
        """HMB-IRB is eligible for health purpose."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="health")
        assert "HMB-IRB" in result
        assert "GRU-IRB" in result

    def test_irb_codes_included_disease(self):
        """DS-*-IRB codes are eligible when disease matches."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CVD"
        )
        assert "DS-CVD-IRB" in result
        assert "DS-CVD-IRB-NPU-MDS" in result
        assert "DS-AF-IRB-RD" in result
        assert "DS-STK-IRB-RD" in result

    def test_irb_not_a_filter(self):
        """IRB does not reduce the eligible set — codes with and without IRB appear."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="DIAB"
        )
        # Both plain and IRB variants
        assert "DS-DIAB" in result
        assert "DS-DIAB-IRB" in result
        assert "DS-T2D" in result
        assert "DS-T2D-IRB-RD" in result
        assert "DS-IR" in result
        assert "DS-IR-IRB" in result

    def test_irb_npu_combined(self):
        """Codes with both IRB and NPU: for-profit excludes them (NPU filter applies)."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="health", is_nonprofit=False
        )
        assert "HMB-IRB" in result  # IRB only — included
        assert "HMB-IRB-NPU" not in result  # IRB + NPU — excluded (NPU)
        assert "GRU-IRB-NPU" not in result  # IRB + NPU — excluded (NPU)

    def test_irb_npu_combined_nonprofit(self):
        """Non-profit org: codes with both IRB and NPU are included."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="health", is_nonprofit=True
        )
        assert "HMB-IRB-NPU" in result
        assert "GRU-IRB-NPU" in result


# ---------------------------------------------------------------------------
# disease_only flag
# ---------------------------------------------------------------------------


class TestDiseaseOnlyFlag:
    """disease_only=True restricts results to DS-* codes only."""

    def test_disease_only_returns_only_ds(self):
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", disease_only=True
        )
        for code in result:
            assert code.startswith("DS-"), f"Expected DS-* only, got {code}"
        assert len(result) > 0

    def test_disease_only_excludes_gru_hmb(self):
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", disease_only=True
        )
        assert "GRU" not in result
        assert "HMB" not in result
        assert "HMP" not in result
        assert "HR" not in result

    def test_disease_only_still_matches_hierarchy(self):
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CA", disease_only=True
        )
        ds_diseases = {parse_consent_code(c).disease for c in result}
        assert "CA" in ds_diseases
        assert "BRCA" in ds_diseases
        assert "OVCA" in ds_diseases

    def test_disease_only_with_for_profit(self):
        """disease_only + for-profit: DS-* only, minus NPU."""
        result = compute_eligible_codes(
            EXTENDED_CODES,
            purpose="disease",
            disease="CA",
            disease_only=True,
            is_nonprofit=False,
        )
        for code in result:
            assert code.startswith("DS-")
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers
        assert "DS-CA" in result
        assert "DS-CA-IRB" in result
        assert "DS-CA-NPU" not in result
        assert "DS-BRCA" in result
        assert "DS-BRCA-NPU-MDS" not in result

    def test_disease_only_without_disease_returns_empty_ds(self):
        """disease_only=True with purpose='health' (no disease) → no DS codes match."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="health", disease_only=True
        )
        # disease_only filters to DS-* only, but purpose='health' without a disease
        # won't match any DS codes (DS requires disease overlap)
        assert result == []


# ---------------------------------------------------------------------------
# Edge cases and combined scenarios
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty input, unknown diseases, combined modifiers."""

    def test_empty_code_list(self):
        assert compute_eligible_codes([], purpose="general") == []
        assert compute_eligible_codes([], purpose="health") == []
        assert compute_eligible_codes([], purpose="disease", disease="CA") == []
        assert compute_eligible_codes([], explicit_code="GRU") == []

    def test_unknown_disease_no_hierarchy_match(self):
        """Unknown disease (not in hierarchy) matches only exact DS-code."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="SCD"
        )
        ds_codes = [c for c in result if c.startswith("DS-")]
        # SCD is not in any hierarchy, so only DS-SCD matches
        ds_diseases = {parse_consent_code(c).disease for c in ds_codes}
        assert "SCD" in ds_diseases
        assert len(ds_diseases) == 1

    def test_disease_purpose_without_disease_returns_no_ds(self):
        """purpose='disease' without a disease arg → GRU + HMB but no DS."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="disease")
        bases = {parse_consent_code(c).base for c in result}
        assert "GRU" in bases
        assert "HMB" in bases
        assert "DS" not in bases

    def test_results_always_sorted(self):
        """All paths produce sorted output."""
        for purpose in ("general", "health", "disease"):
            kwargs = {"purpose": purpose}
            if purpose == "disease":
                kwargs["disease"] = "CVD"
            result = compute_eligible_codes(EXTENDED_CODES, **kwargs)
            assert result == sorted(result), f"Not sorted for purpose={purpose}"

    def test_multi_modifier_codes_preserved(self):
        """Codes with many modifiers (IRB-NPU-MDS) are correctly handled."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CVD"
        )
        assert "DS-CVD-IRB-NPU-MDS" in result

    def test_multi_modifier_codes_npu_filtered(self):
        """Multi-modifier with NPU excluded for for-profit."""
        result = compute_eligible_codes(
            EXTENDED_CODES, purpose="disease", disease="CVD", is_nonprofit=False
        )
        assert "DS-CVD-IRB-NPU-MDS" not in result
        assert "DS-CVD-IRB" in result

    def test_gso_modifier_not_a_filter(self):
        """GSO (Genetic Studies Only) is a modifier, not a filter."""
        result = compute_eligible_codes(EXTENDED_CODES, purpose="health")
        assert "HMB-GSO" in result
        assert "HMB-COL-NPU-GSO" in result

    def test_explicit_code_ignores_purpose(self):
        """Explicit code path does not consider purpose at all."""
        result = compute_eligible_codes(
            EXTENDED_CODES, explicit_code="HMB", purpose="general"
        )
        # Even though purpose=general normally excludes HMB, explicit path ignores it
        assert "HMB" in result
        assert "HMB-IRB" in result


# ---------------------------------------------------------------------------
# expand_consent_tags — axis-based tag expansion
# ---------------------------------------------------------------------------


class TestExpandConsentTags:
    """Tests for the tag-based consent expansion introduced in #273."""

    def test_no_npu_disease_scope(self):
        """no-npu + disease scope → GRU + HMB + DS-CVD minus NPU codes."""
        result = expand_consent_tags(
            EXTENDED_CODES, ["no-npu"], scope="disease", disease="CVD"
        )
        # Should include GRU, HMB, and matching DS-CVD codes
        assert "GRU" in result
        assert "HMB" in result
        assert "DS-CVD" in result
        assert "DS-CVD-IRB" in result
        # NPU codes excluded
        assert "GRU-NPU" not in result
        assert "HMB-NPU" not in result
        assert "DS-CVD-NPU" not in result

    def test_no_npu_general_scope(self):
        """no-npu + general scope → GRU codes minus NPU."""
        result = expand_consent_tags(
            EXTENDED_CODES, ["no-npu"], scope="general"
        )
        for code in result:
            assert parse_consent_code(code).base == "GRU"
            assert "NPU" not in parse_consent_code(code).modifiers
        assert "GRU" in result
        assert "GRU-IRB" in result
        assert "GRU-NPU" not in result

    def test_empty_tags_general_scope(self):
        """Empty tags + general scope → all GRU codes (no filtering)."""
        result = expand_consent_tags(EXTENDED_CODES, [], scope="general")
        all_gru = compute_eligible_codes(EXTENDED_CODES, purpose="general")
        assert result == all_gru

    def test_multiple_modifier_tags(self):
        """no-npu + no-irb → exclude both NPU and IRB modifiers."""
        result = expand_consent_tags(
            EXTENDED_CODES, ["no-npu", "no-irb"], scope="health"
        )
        for code in result:
            parsed = parse_consent_code(code)
            assert "NPU" not in parsed.modifiers
            assert "IRB" not in parsed.modifiers
        assert "GRU" in result
        assert "HMB" in result
        assert "GRU-IRB" not in result
        assert "HMB-IRB" not in result
        assert "GRU-NPU" not in result

    def test_explicit_gru(self):
        """explicit:GRU → all GRU variants."""
        result = expand_consent_tags(EXTENDED_CODES, ["explicit:GRU"])
        assert "GRU" in result
        assert "GRU-IRB" in result
        assert "GRU-NPU" in result
        assert "HMB" not in result

    def test_explicit_hmb_with_no_npu(self):
        """explicit:HMB + no-npu → HMB variants minus NPU."""
        result = expand_consent_tags(EXTENDED_CODES, ["explicit:HMB", "no-npu"])
        assert "HMB" in result
        assert "HMB-IRB" in result
        assert "HMB-PUB" in result
        assert "HMB-NPU" not in result
        assert "HMB-IRB-NPU" not in result
        assert "GRU" not in result

    def test_empty_tags_no_filter(self):
        """Empty tags = scope-based codes with no modifier filtering."""
        result = expand_consent_tags(EXTENDED_CODES, [], scope="health")
        expected = compute_eligible_codes(EXTENDED_CODES, purpose="health")
        assert result == expected

    def test_results_sorted(self):
        """Output is always sorted."""
        result = expand_consent_tags(
            EXTENDED_CODES, ["no-npu"], scope="disease", disease="CA"
        )
        assert result == sorted(result)

