# PRD: Consent Code Compatibility Model

**Status:** Implemented — PR #199, Feb 2026
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

1. **No permission hierarchy.** GRU (general research) permits any health research, HMB permits health/medical, DS-X permits only disease X. A diabetes researcher is eligible for GRU and HMB studies too, not just DS-DIAB.
2. **No base code expansion.** "GRU" misses GRU-IRB, GRU-NPU, GRU-MDS, etc.
3. **No modifier semantics.** NPU means "non-profit only" but the system treats it as an opaque suffix.

## Background: How Consent Codes Work

Consent codes (GA4GH Data Use Ontology / dbGaP standard) encode data use permissions:

```
[Base Code] - [Disease*] - [Modifier] - [Modifier] ...
```

**Base codes:** GRU (any research), HMB (health/medical/biomedical), DS-X (disease-specific). Permission hierarchy: GRU ⊇ HMB ⊇ DS-X.

**Modifiers:** IRB (ethics approval), NPU (non-profit only), PUB (must publish), COL (collaboration required), MDS (methods development), GSO (genetic studies only). Modifiers add requirements on the researcher, not restrictions on the research purpose.

**Disease abbreviations:** Not standardized by GA4GH — chosen per study by the Genomic Program Administrator. The authoritative mapping lives in `catalog-build/common/disease_abbrev_mapping.tsv` (388 entries).

**Disease hierarchies:** Some diseases are sub-types (T1D, T2D are children of DIAB; BRCA, LC are children of CA). A researcher studying "diabetes" is eligible for DS-T1D studies too.

---

## Design

### Principle: Deterministic logic, not LLM reasoning

The permission hierarchy and modifier semantics are fixed GA4GH rules. This logic belongs in pure Python (`consent_logic.py`), not in agent prompts. The LLM identifies what the user wants; deterministic code computes which codes are compatible.

### Data flow

```
User query
  → Extract agent: recognizes eligibility language, emits consentCode mention
  → Resolve agent: maps mention to tool parameters (purpose, disease, nonprofit)
  → compute_consent_eligibility tool: calls consent_logic.py
  → consent_logic.py: deterministic eligibility computation
  → list of eligible codes returned as resolve values
```

### Extract layer: When to emit consent mentions

Disease names become consent mentions **only** when eligibility language is present. Cue words: "what can I use", "eligible for", "consented for", "for-profit", "non-profit", "available for my research".

- "diabetes studies" → focus only (topic search)
- "What diabetes datasets can I use?" → focus + consentCode (dual mention)

When both are emitted, focus filters on topic (study must be _about_ diabetes) and consentCode filters on permission (consent must _permit_ diabetes research). These are orthogonal.

### Resolve layer: Single tool call

The resolve agent has one new tool: `compute_consent_eligibility`. Two patterns:

- **Pattern A (explicit code):** User said "GRU" or "HMB-IRB" → prefix expansion
- **Pattern B (eligibility):** User described a use case → LLM picks purpose/disease/nonprofit → one tool call

The tool accepts disease names in any form ("diabetes", "DIAB", "type 1 diabetes") and resolves them internally. The LLM never needs to look up abbreviations.

### Eligibility algorithm

The core function `compute_eligible_codes` iterates all consent codes in the index and applies:

1. **NPU filter:** If researcher is for-profit (`is_nonprofit=False`), exclude codes with NPU modifier.
2. **Explicit code path:** Prefix-match the code (e.g. "GRU" matches GRU, GRU-IRB, GRU-NPU).
3. **Purpose path:**
   - GRU: always eligible (any research purpose)
   - HMB/HMP/HR: eligible for "health" or "disease" purpose, not "general"
   - DS-X: eligible when the user's disease overlaps X (including sub-diseases)
4. **disease_only flag:** When set, skips non-DS codes. For "specifically consented for diabetes" vs "eligible for diabetes research".

Disease overlap uses bidirectional expansion: querying "T1D" matches DS-DIAB (because DIAB's children include T1D), and querying "DIAB" matches DS-T1D (because DIAB expands to include T1D).

---

## Key decisions

**GRU vs HMB distinction:** GRU is eligible for _any_ research (social science, population genetics, etc.). HMB is restricted to health/medical/biomedical. "Social science behavioral genetics research" → GRU only, not HMB.

**Permissive defaults:** Unknown researcher attributes don't filter. If profit status isn't mentioned, NPU codes are included (`is_nonprofit=None`).

**Disease abbreviation source:** Read from `catalog-build/common/disease_abbrev_mapping.tsv` (388 entries, maintained separately). Not duplicated in backend code. Possessive forms ("Alzheimer's") are stripped before matching. Substring matches prefer the shortest disease name.

**Modifier semantics:** Modifiers are requirements, not restrictions. GRU-IRB is still GRU — it just requires IRB paperwork. So "GRU" expands to all GRU-\* variants.

---

## Files

| File                                              | Role                                        |
| ------------------------------------------------- | ------------------------------------------- |
| `concept_search/consent_logic.py`                 | Deterministic eligibility computation       |
| `concept_search/consent_codes.json`               | Base codes, modifiers, disease hierarchy    |
| `catalog-build/common/disease_abbrev_mapping.tsv` | Disease abbreviation → name mapping         |
| `concept_search/resolve_agent.py`                 | `compute_consent_eligibility` tool          |
| `concept_search/RESOLVE_PROMPT.md`                | Pattern A / Pattern B instructions          |
| `concept_search/EXTRACT_PROMPT.md`                | Eligibility language recognition            |
| `tests/test_consent_logic.py`                     | 46 unit tests                               |
| `concept_search/eval_resolve.py`                  | 48 resolve eval cases (16 consent-specific) |
| `concept_search/eval_extract.py`                  | 41 extract eval cases (8 consent-specific)  |

## Future work

- **Exclusion inversion:** When eligible set is >50% of all codes, return excluded codes instead
- **Deeper disease hierarchy:** Grandchild nesting, more parent groups beyond CA/CVD/DIAB/LD
- **Resolve result cache:** See PRD-resolve-cache.md
