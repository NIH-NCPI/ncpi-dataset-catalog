# PRD: Consent Code Compatibility Model

**Status:** DRAFT — Feb 2026
**Related:** PRD-concept-search.md, PRD-search-api.md

---

## Problem

The search API treats consent codes as opaque strings with exact-match semantics. This fails for the three most common researcher consent queries:

| Query                                      | Current behavior                                | Expected behavior                                  |
| ------------------------------------------ | ----------------------------------------------- | -------------------------------------------------- |
| "I'm studying diabetes, what can I use?"   | Resolves to DS-DIAB (~9 studies)                | GRU-\* + HMB-\* + DS-DIAB family (~2,300+ studies) |
| "I'm a for-profit company studying cancer" | No consent handling; returns all cancer studies | GRU-\* + HMB-\* + DS-CA-\* minus NPU codes         |
| "Studies with GRU consent"                 | Exact match "GRU" (1,081 studies)               | All GRU-\* variants (1,543 studies)                |

**Root causes:**

1. **No permission hierarchy.** GRU (general research) permits any health research, HMB permits health/medical, DS-X permits only disease X. A diabetes researcher is eligible for GRU and HMB studies too, not just DS-DIAB. The pipeline doesn't know this.
2. **No base code expansion.** The DuckDB store does exact string matching. "GRU" misses GRU-IRB, GRU-NPU, GRU-MDS, etc. — 462 studies lost.
3. **No modifier semantics.** NPU means "non-profit only" but the system treats it as an opaque suffix. "For-profit company" queries can't work.

## Background: How Consent Codes Work

Consent codes (GA4GH Data Use Ontology / dbGaP standard) encode data use permissions:

### Structure

```
[Base Code] - [Disease*] - [Modifier] - [Modifier] ...
```

### Base codes (one per consent group)

| Code       | Name                      | Scope                                                 |
| ---------- | ------------------------- | ----------------------------------------------------- |
| **GRU**    | General Research Use      | Any research purpose — most permissive                |
| **HMB**    | Health/Medical/Biomedical | Health research only (excludes ancestry-only studies) |
| **DS-[X]** | Disease-Specific          | Only research on disease X                            |

**Permission hierarchy:** GRU ⊇ HMB ⊇ DS-X

### Modifiers (zero or more, appended with hyphens)

| Modifier | Meaning                      | Effect on researcher              |
| -------- | ---------------------------- | --------------------------------- |
| **NPU**  | Not-for-Profit Use Only      | For-profit organizations excluded |
| **IRB**  | Ethics/IRB Approval Required | Must provide IRB documentation    |
| **PUB**  | Publication Required         | Must publish results              |
| **COL**  | Collaboration Required       | Must collaborate with study PI    |
| **MDS**  | Methods Development          | Use for methods research          |
| **GSO**  | Genetic Studies Only         | Only genetic analyses permitted   |

Modifiers add **requirements on the researcher**, not restrictions on the research purpose. `GRU-IRB` is still general research use — it just requires IRB paperwork.

### Real examples from the catalog

- `GRU` — general research, no restrictions
- `GRU-IRB-NPU` — general research, needs IRB, non-profit only
- `HMB-MDS` — health research, methods development
- `DS-DIAB` — diabetes research only
- `DS-CVD-IRB-NPU` — cardiovascular research, needs IRB, non-profit only
- `DS-BRCA-PUB` — breast cancer research, must publish

### Disease sub-disease relationships

Some disease abbreviations are sub-types of broader categories:

| Parent | Children                                                                                                 |
| ------ | -------------------------------------------------------------------------------------------------------- |
| DIAB   | T1D, T2D, DRC, T1DR, IR                                                                                  |
| CA     | BRCA, OVCA, LC, PC, HCC, CC, PACA, NHL, LEU, HNC, MM, RCC, CLL, OC, BLADDERCA, BROC, BT, PEDCR, LCTC, HM |
| CVD    | AF, HF, MI, PAD, STK, CHD                                                                                |
| LD     | LIVD, ESD                                                                                                |

A researcher studying "diabetes" is eligible for DS-DIAB, DS-T1D, DS-T2D, DS-DRC, etc.

---

## Design Principles

### 1. Deterministic compatibility logic, not LLM reasoning

The permission hierarchy and modifier semantics are fixed GA4GH rules. This logic belongs in deterministic Python code (`consent_logic.py`), not in agent prompts. The resolve agent identifies what the user wants; deterministic code computes which codes are compatible.

### 2. Consent filtering only when asked

Plain disease queries ("diabetes studies") are topic-only searches. Consent eligibility filtering only activates when the user uses eligibility language: "what can I use", "consented for", "I'm a for-profit company", "available for my research". The extract agent recognizes these cues.

### 3. Dual mentions when eligibility is triggered

"What diabetes datasets can I use?" generates:

- **focus** mention: "diabetes" (topic filter — study must be about diabetes)
- **consentCode** mention: "eligible for diabetes research" (permission filter — consent must permit diabetes research)

These are orthogonal: a GRU cardiovascular study passes consent but fails focus.

### 4. Base code expansion always happens

"GRU" expands to all GRU-\* variants (GRU, GRU-IRB, GRU-NPU, etc.). A GRU-IRB study is still a GRU study — the modifier adds a requirement, not a restriction. But "GRU-IRB" does NOT expand — the user specified the exact code with modifier.

### 5. Permissive defaults

Unknown researcher attributes don't filter. If profit status isn't mentioned, NPU codes are included.

---

## Consent Compatibility Model

### Parsed code structure

Every consent code decomposes into:

```python
@dataclass
class ParsedConsentCode:
    raw: str              # "DS-DIAB-IRB-NPU"
    base: str             # "DS"
    disease: str | None   # "DIAB" (only for DS-* codes)
    modifiers: set[str]   # {"IRB", "NPU"}
```

Parsing walks the hyphen-separated parts: first token is the base code, then for DS codes accumulate disease parts until hitting a known modifier, then accumulate modifiers.

```
GRU           → base=GRU,  disease=None, modifiers={}
GRU-IRB-NPU  → base=GRU,  disease=None, modifiers={IRB, NPU}
DS-DIAB       → base=DS,   disease=DIAB, modifiers={}
DS-CVD-IRB    → base=DS,   disease=CVD,  modifiers={IRB}
```

### Eligibility computation

```python
class ConsentEligibility(BaseModel):
    """Researcher's use case for consent compatibility."""
    purpose: Literal["general", "health", "disease_specific"] = "general"
    disease: str | None = None       # disease abbreviation for DS matching
    is_nonprofit: bool | None = None # None = unknown, don't filter
    explicit_code: str | None = None # when user names a code directly
```

**Algorithm for `compute_eligible_codes(eligibility, all_codes)`:**

1. **Explicit code** — if set, return all codes with that prefix (e.g., "GRU" → all GRU-\*)
2. **By purpose:**
   - `"general"` → all codes (GRU + HMB + DS-\*)
   - `"health"` → all codes (GRU + HMB + DS-\* — all are health-related)
   - `"disease_specific"` → GRU-\* + HMB-\* + DS-[matching disease and sub-diseases]-\*
3. **Modifier filter:**
   - `is_nonprofit == False` → exclude codes with NPU modifier
   - `is_nonprofit == True` or `None` → include all

### Handling large value lists

A general-purpose nonprofit query would return all ~842 codes. Optimizations:

- **Short-circuit:** If purpose="general" and is_nonprofit is True/None → all codes eligible, skip consent constraint entirely
- **Exclusion inversion:** If eligible set is >50% of all codes, return the excluded codes with `exclude=true` instead. For "general purpose, for-profit" the excluded set is just ~100 NPU codes

---

## Changes to Each Agent

### Extract Agent (`EXTRACT_PROMPT.md`)

Add researcher profile recognition. New patterns:

| User language                               | Extract as                                                             |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| "I'm studying [disease]" + eligibility cue  | focus="[disease]" + consentCode="eligible for [disease] research"      |
| "for-profit" / "commercial" / "industry"    | consentCode="for-profit use"                                           |
| "nonprofit" / "academic" / "not-for-profit" | consentCode="nonprofit use"                                            |
| "what can I use for [disease]?"             | consentCode="eligible for [disease] research"                          |
| "consented for general research"            | consentCode="general research use"                                     |
| "I'm a nonprofit studying cancer"           | focus="cancer" + consentCode="eligible for cancer research, nonprofit" |

**Key rule:** A disease name is a consent mention (not focus) only when the query describes what research the data is _consented for_. Eligibility cues: "what can I use", "consented for", "approved for", "available for", "am I eligible", "do you have studies I can use". Without these cues, disease mentions are focus-only.

### Resolve Agent (`RESOLVE_PROMPT.md` + `resolve_agent.py`)

Add new tool `compute_consent_eligibility`:

```python
@_agent.tool
def compute_consent_eligibility(
    ctx: RunContext[ConceptIndex],
    purpose: str = "general",
    disease: str | None = None,
    is_nonprofit: bool | None = None,
    explicit_code: str | None = None,
) -> dict:
    """Compute all consent codes compatible with a researcher's use case.

    Args:
        purpose: "general", "health", or "disease_specific"
        disease: Disease abbreviation (e.g., "DIAB", "CA"). Call
                 get_disease_specific_codes() first to find it.
        is_nonprofit: True=nonprofit, False=for-profit, None=unknown
        explicit_code: Specific code to expand (e.g., "GRU" → all GRU-*)

    Returns:
        Dict with 'codes' list and 'summary' description.
    """
```

Update RESOLVE_PROMPT.md consent section with two patterns:

- **Pattern A (explicit code):** User names "GRU", "HMB-IRB" → call `compute_consent_eligibility(explicit_code=...)` for prefix expansion
- **Pattern B (eligibility):** User describes use case → determine purpose + disease + org type → call `compute_consent_eligibility(purpose=..., disease=..., is_nonprofit=...)`

### Structure Agent

No changes needed. Existing boolean semantics (AND between mentions, OR within values, exclude flag) work correctly. The resolve agent handles all consent semantics before the structure agent sees it.

---

## New Module: `consent_logic.py`

Deterministic Python module, no LLM dependencies:

- `parse_consent_code(code: str) -> ParsedConsentCode` — decompose code string
- `expand_disease(disease: str) -> set[str]` — return disease + sub-diseases
- `compute_eligible_codes(all_codes, purpose, disease, is_nonprofit, explicit_code) -> list[str]` — core eligibility computation

Disease hierarchy defined in `consent_codes.json` under new `disease_hierarchy` key.

---

## Before/After Examples

### Example 1: "I'm studying diabetes, what datasets can I use?"

**Before:**

```
Extract: [consentCode: "diabetes research"]
Resolve: get_disease_specific_codes() → DS-DIAB → values=["DS-DIAB"]
DuckDB:  exact match "DS-DIAB" → ~9 studies
```

**After:**

```
Extract: [focus: "diabetes", consentCode: "eligible for diabetes research"]
Resolve (focus):   "Diabetes Mellitus"
Resolve (consent): compute_consent_eligibility(purpose="disease_specific", disease="DIAB")
                   → all GRU-* + HMB-* + DS-DIAB-* + DS-T1D-* + DS-T2D-* + DS-DRC-*
DuckDB:  focus=Diabetes AND consentCode IN (...eligible codes...)
         → ~50-100 studies (diabetes focus + permissive consent)
```

### Example 2: "I'm a for-profit company studying cancer"

**Before:**

```
Extract: [focus: "cancer"] — no consent mention extracted
Result:  All cancer studies regardless of consent; many NPU studies
         the company cannot actually access
```

**After:**

```
Extract: [focus: "cancer", consentCode: "for-profit use, cancer research"]
Resolve (focus):   "Neoplasms"
Resolve (consent): compute_consent_eligibility(
                     purpose="disease_specific", disease="CA", is_nonprofit=False)
                   → GRU-* + HMB-* + DS-CA-* minus anything with NPU
DuckDB:  focus=Neoplasms AND consentCode IN (...non-NPU codes...)
```

### Example 3: "Studies with GRU consent"

**Before:**

```
Resolve: values=["GRU"]
DuckDB:  exact match "GRU" → 1,081 studies (misses 462 GRU-* variants)
```

**After:**

```
Resolve: compute_consent_eligibility(explicit_code="GRU")
         → [GRU, GRU-IRB, GRU-NPU, GRU-MDS, ...]
DuckDB:  matches all GRU-* → 1,543 studies
```

### Example 4: "HMB-IRB studies with smoking data"

**Before and after are the same** — user specified a full code with modifier:

```
Resolve: compute_consent_eligibility(explicit_code="HMB-IRB") → ["HMB-IRB"]
DuckDB:  exact match "HMB-IRB" → 116 studies
```

### Example 5: "I'm a nonprofit studying Alzheimer's, what can I use?"

**After:**

```
Extract: [focus: "Alzheimer's", consentCode: "nonprofit, Alzheimer's research"]
Resolve (focus):   "Alzheimer Disease"
Resolve (consent): compute_consent_eligibility(
                     purpose="disease_specific", disease="ALZ", is_nonprofit=True)
                   → all GRU-* + HMB-* + DS-ALZ-* (including NPU variants)
```

---

## Eval Test Cases

### Extract Agent

| Name                        | Input                                                      | Expected                                                       |
| --------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| consent-eligibility-disease | "I'm studying diabetes, what datasets can I use?"          | focus="diabetes", consentCode="eligible for diabetes research" |
| consent-for-profit          | "I'm a for-profit company, what cancer studies can I use?" | focus="cancer", consentCode="for-profit use, cancer research"  |
| consent-nonprofit-general   | "I'm a nonprofit researcher, what's available?"            | consentCode="nonprofit, general research"                      |
| consent-explicit-code       | "GRU consented WGS studies"                                | consentCode="GRU", dataType=["WGS"]                            |
| consent-no-eligibility-cue  | "diabetes studies"                                         | focus="diabetes" only (no consent mention)                     |

### Resolve Agent

| Name                         | Input                                   | Expected values (recall)          |
| ---------------------------- | --------------------------------------- | --------------------------------- |
| consent-eligibility-diabetes | "eligible for diabetes research"        | GRU, HMB, DS-DIAB present         |
| consent-for-profit-cancer    | "for-profit use, cancer research"       | GRU, DS-CA present; no NPU codes  |
| consent-explicit-gru         | "GRU"                                   | GRU, GRU-IRB, GRU-NPU present     |
| consent-explicit-hmb         | "HMB"                                   | HMB, HMB-IRB present              |
| consent-sub-disease          | "eligible for type 1 diabetes research" | GRU, HMB, DS-T1D, DS-DIAB present |

### Unit Tests (`test_consent_logic.py`)

| Name                         | Test                                                                          |
| ---------------------------- | ----------------------------------------------------------------------------- |
| test_parse_simple            | GRU → base=GRU, disease=None, modifiers={}                                    |
| test_parse_compound          | DS-CVD-IRB-NPU → base=DS, disease=CVD, modifiers={IRB, NPU}                   |
| test_expand_diabetes         | DIAB → {DIAB, T1D, T2D, DRC, T1DR, IR}                                        |
| test_expand_no_children      | ALZ → {ALZ}                                                                   |
| test_eligible_explicit_gru   | explicit_code="GRU" returns all GRU-\*                                        |
| test_eligible_disease        | purpose="disease_specific", disease="DIAB" returns GRU + HMB + DS-DIAB family |
| test_eligible_for_profit     | is_nonprofit=False excludes NPU codes                                         |
| test_eligible_nonprofit      | is_nonprofit=True includes NPU codes                                          |
| test_eligible_unknown_profit | is_nonprofit=None includes all                                                |

---

## Edge Cases and Decisions

**Q: What about rare base codes (CADM, HMP, IRU, HR)?**
A: Treated as opaque strings for Phase 1. They appear in only 1-38 studies each. Explicit code references get prefix-expanded. They are not part of the GRU > HMB > DS hierarchy.

**Q: What if a study has multiple consent codes?**
A: 453 studies have multiple consent groups (e.g., "GRU" and "DS-DIAB-NPU"). A study matches if ANY of its consent codes is in the eligible set. This is correct — if one consent group permits the researcher's use, the study is accessible.

**Q: What about the ~4% of codes that don't map cleanly to GA4GH DUO?**
A: These are legacy or non-standard codes. They pass through as opaque strings. The eligibility model handles them gracefully by only filtering codes it can parse.

---

## Files to Create or Modify

| File                                        | Action                                                   |
| ------------------------------------------- | -------------------------------------------------------- |
| `backend/concept_search/consent_logic.py`   | **Create** — parsing, hierarchy, eligibility computation |
| `backend/concept_search/consent_codes.json` | **Modify** — add `disease_hierarchy`                     |
| `backend/concept_search/index.py`           | **Modify** — add `compute_consent_eligibility` method    |
| `backend/concept_search/resolve_agent.py`   | **Modify** — add `compute_consent_eligibility` tool      |
| `backend/concept_search/RESOLVE_PROMPT.md`  | **Modify** — eligibility-based resolution strategy       |
| `backend/concept_search/EXTRACT_PROMPT.md`  | **Modify** — researcher profile extraction               |
| `backend/concept_search/eval_extract.py`    | **Modify** — consent eligibility test cases              |
| `backend/concept_search/eval_resolve.py`    | **Modify** — consent eligibility test cases              |
| `backend/tests/test_consent_logic.py`       | **Create** — unit tests for deterministic logic          |

## Phases

### Phase 1: Core consent logic + base code expansion

- `consent_logic.py` with parse, expand, eligibility
- Resolve agent tool + prompt update
- Extract agent prompt update
- Eval cases and unit tests

### Phase 2: Exclusion inversion optimization

- Smart representation (include vs exclude list based on size)
- Short-circuit for "general purpose, nonprofit"

### Phase 3: Disease hierarchy refinement

- Expand parent-child mappings from analysis of all 363 DS-\* disease codes
- Consider auto-derivation from UMLS/MeSH
