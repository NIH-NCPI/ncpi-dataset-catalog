# PRD: Natural Language Concept Search API

## Overview

A Python API that accepts natural language queries about biomedical measurements and returns matching NCPI dataset studies. Three specialized agents handle extraction, resolution, and query structuring — then deterministic code executes the query against an in-memory index.

## Example Queries

- _"Show me whole genome studies where vitamin K intake and age-related macular degeneration were evaluated"_
- _"Which studies measured systolic blood pressure?"_
- _"Studies with both echocardiography and carotid intima-media thickness"_
- _"What lipid measurements exist across all studies?"_
- _"Does the Framingham Heart Study have sleep data?"_
- _"Studies with BMI data"_ (agent resolves abbreviation)
- _"Blood sugar studies"_ (agent maps lay term to Fasting Glucose, etc.)
- _"GRU consented WGS from diabetic patients where vitamin K was measured"_ (multi-facet)
- _"Studies with both heart disease and diabetes"_ (same-facet AND)
- _"Echocardiography studies but not transesophageal"_ (exclusion)

## Problem

The catalog has ~450K phenotype variables across ~2,900 studies, classified into ~95K concept names. Researchers cannot currently search by what was measured — only by study-level metadata (platform, disease focus, data type, etc.). This API bridges the gap: natural language in, matching studies out, across all facets.

## Design Principles

### 1. Let the LLM do what LLMs are good at

The LLM's job is **natural language understanding** — the thing no search index can do. It understands that "blood sugar" means glucose, that "BMI" is Body Mass Index, that "juvenile Hispanics with type one diabetes" contains three separate constraints. Don't replicate this with fuzzy string matching or synonym lists.

### 2. Separation of concerns — three agents

Each agent has one job:

- **Extract Agent** — NLU only: parse query into raw mentions with facet guesses
- **Resolve Agent** — grounding only: find canonical index values for each mention
- **Structure Agent** — logic only: determine boolean relationships between resolved mentions

The LLM never filters datasets directly. The concept index never interprets user intent. The query engine never guesses concept names.

### 3. Let the resolve agent retry

When a concept lookup fails, the resolve agent rewrites the term using medical knowledge and tries again. "Type one diabetes" fails → rewrites to "Type 1 Diabetes Mellitus" → succeeds. If all rewrites fail, the mention is included with an empty values list for the caller to handle.

## Facets

The NCPI catalog has these filterable facets:

| Facet             | Key           | Values                               | Agent Behavior                              |
| ----------------- | ------------- | ------------------------------------ | ------------------------------------------- |
| **Platform**      | `platform`    | AnVIL, BDC, CRDC, KFDRC, dbGaP       | Small enum — extract agent matches directly |
| **Focus/Disease** | `focus`       | ~950 MeSH terms                      | Resolve agent searches index                |
| **Data Type**     | `dataType`    | ~64 values (WGS, WXS, RNA-Seq, etc.) | Small enum — extract agent matches directly |
| **Study Design**  | `studyDesign` | ~15 values                           | Small enum — extract agent matches directly |
| **Consent Code**  | `consentCode` | ~840 codes (GRU, HMB, DS-\*, etc.)   | Extract agent recognizes standard codes     |
| **Measurement**   | `measurement` | ~95K concept names                   | Resolve agent always searches index         |

## Architecture

```
User NL query
     │
     ▼
┌──────────────────────────────────────┐
│  Agent 1: EXTRACT                    │
│  (Haiku, no tools)                   │
│                                      │
│  Parse query into raw mentions       │
│  - Identify distinct phrases         │
│  - Guess facet for each mention      │
│  - Correct typos, expand abbrevs     │
│                                      │
│  Output: list[RawMention]            │
│    [{text, facet}, ...]              │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Agent 2: RESOLVE                    │
│  (Haiku, has search_concepts tool)   │
│                                      │
│  For each raw mention:               │
│  - search_concepts(text, facet)      │
│  - If no match → rewrite & retry     │
│  - Pick best canonical value(s)      │
│                                      │
│  Output: list[ResolvedMention]       │
│    [{text, facet, values}, ...]      │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Agent 3: STRUCTURE                  │
│  (Haiku, no tools)                   │
│                                      │
│  Given original query + resolved     │
│  mentions, determine boolean logic:  │
│  - "X and Y" → separate mentions     │
│  - "X or Y" → merge into one mention │
│  - "but not X" → exclude=true        │
│                                      │
│  Output: QueryModel                  │
└──────────────┬───────────────────────┘
               │ (LLMs are done here)
               ▼
┌──────────────────────────────────────┐
│  Code: Study Lookup                  │
│  (deterministic, no LLM)            │
│                                      │
│  Execute QueryModel against index    │
│  → return matching studies           │
└──────────────────────────────────────┘
```

## Query Model

### Boolean Semantics

Two levels of boolean logic:

**Within a mention** — `values` are always **OR**. A mention with `values=["Total Cholesterol", "HDL Cholesterol"]` matches studies that have _any_ of those.

**Between mentions** — always **AND**, unless `exclude=True` (NOT). Studies must satisfy every non-excluded mention. Excluded mentions subtract from the result.

### Supported Query Complexity

| Level                              | Example                                                                        | Supported                               |
| ---------------------------------- | ------------------------------------------------------------------------------ | --------------------------------------- |
| 1. Single facet, single value      | `disease = Diabetes`                                                           | Yes                                     |
| 2. Single facet, OR within values  | `dataType = (WGS OR WXS)`                                                      | Yes                                     |
| 3. Multiple facets, AND between    | `(disease = Diabetes) AND (dataType = WGS)`                                    | Yes                                     |
| 4. Multi-facet with OR within some | `(disease = Diabetes) AND (dataType = (WGS OR WXS))`                           | Yes                                     |
| 5. Same facet AND                  | `(disease = Diabetes) AND (disease = Heart Disease)`                           | Yes                                     |
| 6. NOT (exclusion)                 | `(measurement = Echo) AND NOT (measurement = TEE)`                             | Yes                                     |
| 7. Mixed                           | `(disease = Diabetes) AND (dataType = (WGS OR WXS)) AND NOT (platform = CRDC)` | Yes                                     |
| 8. OR between facets               | `(disease = Diabetes) OR (measurement = Glucose)`                              | No — requires union of separate queries |
| 9+ Nested groups                   | `((A AND B) OR (C AND D))`                                                     | No — requires expression tree model     |

### Data Model

```python
class RawMention(BaseModel):
    """Output of the extract agent."""
    text: str          # raw phrase from the query
    facet: Facet       # guessed facet

class ResolvedMention(BaseModel):
    """Output of the resolve agent, input to the structure agent."""
    original_text: str
    facet: Facet
    values: list[str]  # canonical value(s), OR within. Empty if unresolved.
    exclude: bool      # True = NOT (exclude matching studies)

class QueryModel(BaseModel):
    """Final structured query. Non-excluded mentions are AND-ed."""
    mentions: list[ResolvedMention]
```

### Examples

_"studies with blood pressure and diabetes"_:

```
facet=measurement  exclude=false  values=[Systolic Blood Pressure, Diastolic Blood Pressure]
facet=focus        exclude=false  values=[Diabetes Mellitus]
```

Studies need ≥1 blood pressure concept AND a diabetes focus.

_"GRU consented WGS from diabetic patients where vitamin K was measured"_:

```
facet=consentCode  exclude=false  values=[GRU]
facet=dataType     exclude=false  values=[WGS]
facet=focus        exclude=false  values=[Diabetes Mellitus]
facet=measurement  exclude=false  values=[Vitamin K Intake]
```

_"echocardiography studies but not transesophageal"_:

```
facet=measurement  exclude=false  values=[Echocardiography]
facet=measurement  exclude=true   values=[Transesophageal Echocardiography]
```

_"studies with both heart disease and diabetes"_:

```
facet=focus        exclude=false  values=[Cardiovascular Diseases]
facet=focus        exclude=false  values=[Diabetes Mellitus]
```

Two separate focus mentions, both AND — study must match both.

_"studies with WGS or WXS data and cholesterol"_:

```
facet=dataType     exclude=false  values=[WGS, WXS]
facet=measurement  exclude=false  values=[Total Cholesterol, HDL Cholesterol, LDL Cholesterol]
```

WGS/WXS are OR within one mention. Cholesterol concepts are OR within one mention. The two mentions are AND-ed.

## Concept Index

Built from two sources:

1. **Measurement concepts**: `catalog-build/classification/output/llm-concepts/*.json` — ~2,870 study files, ~95K unique concept names with study counts
2. **Study metadata facets**: `catalog/ncpi-platform-studies.json` — ~2,944 studies with focus, dataType, studyDesign, consentCode, platform

Provides:

- `search_concepts(query, facet?, limit?)` — case-insensitive substring search
- `list_facet_values(facet)` — enumerate a facet's values
- `get_studies_for_mentions(facet_values)` — deterministic study lookup

The concept vocabulary is small enough for in-memory search. No vector DB or OpenSearch needed for Phase 1.

## Tech Stack

- **Pydantic AI** — agent orchestration with typed tools
- **pydantic-evals** — eval harness for mention extraction
- **Anthropic Claude** — Haiku for agents (fast, cheap), Sonnet for fallback
- **In-memory index** — concept database loaded from JSON at startup
- **FastAPI** — API framework (Phase 3)

## Testing: Eval Harness

Each eval case: NL query → expected QueryModel. Scoring uses recall (expected values ⊆ actual values). Extra values in actual are not penalized — the agent may reasonably expand concepts.

See `backend/concept_search/eval_mentions.py` for current cases.

## Phases

### Phase 1: Three-Agent Pipeline + Evals (current)

- Build extract / resolve / structure agents
- Eval harness with pydantic-evals
- CLI: `python -m concept_search.cli "query"`
- Iterate prompts against eval cases

### Phase 2: End-to-End Pipeline

- Wire agents together with deterministic controller
- Study lookup returns actual results
- End-to-end CLI with `--lookup` flag

### Phase 3: API Endpoint

- FastAPI app wrapping the pipeline
- Streaming responses
- Query logging for failure analysis

### Phase 4: Enrichment

- Concept hierarchy (is-a relations, e.g., "sleep data" → all sleep concepts)
- UMLS CUI grounding per concept (synonym expansion)
- Concept normalization (merge synonyms from classification)
- Domain grouping (Cardiovascular, Pulmonary, Behavioral, etc.)

## Open Questions

1. **Concept hierarchy** — "sleep data" currently expands to 20 individual sleep concepts. A hierarchy would let us model is-a relations and return the closure. Phase 4.
2. **Query latency budget** — Haiku ~1s per agent call × 3 agents = ~3s. Acceptable?
3. **Hosting** — separate Python service from the Next.js frontend
4. **95K concepts** — the classifier generates overly specific names for singleton variables. Normalization pass could reduce to ~5K useful concepts.
5. **OR between facets** — not supported in Phase 1. How common is this query pattern?
