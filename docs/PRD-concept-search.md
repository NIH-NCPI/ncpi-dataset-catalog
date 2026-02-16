# PRD: Natural Language Concept Search API

## Overview

A Python API that accepts natural language queries about biomedical measurements and returns matching NCPI dataset studies. Powered by a Pydantic AI agent that translates free-text queries into structured concept lookups against an indexed concept database built from variable-level classifications.

## Example Queries

- _"Show me whole genome studies where vitamin K intake and age-related macular degeneration were evaluated"_
- _"Which studies measured systolic blood pressure?"_
- _"Studies with both echocardiography and carotid intima-media thickness"_
- _"What lipid measurements exist across all studies?"_
- _"Does the Framingham Heart Study have sleep data?"_
- _"Studies with BMI data"_ (agent resolves abbreviation)
- _"Blood sugar studies"_ (agent maps lay term to Fasting Glucose, HbA1c, etc.)

## Problem

The catalog has ~450K phenotype variables classified into standardized concept names. Researchers cannot currently search by what was measured — only by study-level metadata. This API bridges the gap: natural language in, matching studies out.

## Design Principles

### 1. Let the LLM do what LLMs are good at

The LLM's job is **natural language understanding** — the thing no search index can do. It understands that "blood sugar" means glucose, that "BMI" is Body Mass Index, that "juvenile Hispanics with type one diabetes" contains three separate constraints, and that "type one" is the word form of "1". Don't try to replicate this with fuzzy string matching, synonym lists, or keyword expansion. The LLM already knows medical vocabulary — give it tools to look up concepts and let it reason.

### 2. Let the LLM retry and ask for clarification

When a concept lookup fails, the LLM doesn't give up — it **rewrites the term** using its medical knowledge and tries again. "Type one diabetes" fails exact match → LLM rewrites to "Type 1 Diabetes Mellitus" → succeeds. "Autoimmune diabetes" fails → LLM tries "Type 1 Diabetes" → succeeds. If all rewrites fail, the LLM **asks the user**: _"I found 'primary adrenal insufficiency' (12 studies) and 'secondary adrenal insufficiency' (3 studies). Which did you mean?"_ This retry loop is the safety net that makes the system robust without requiring perfect synonym curation upfront.

### 3. Separation of concerns

**The LLM handles natural language understanding. The concept index handles grounding. The query logic is deterministic.**

The LLM never filters datasets directly. The concept index never interprets user intent. The query engine never guesses concept names.

## Architecture

```
User NL query
     │
     ▼
┌──────────────────────────────────┐
│  LLM: Mention Extraction         │
│  (structured output)             │
│                                  │
│  - Identify concept "mentions"   │
│  - Correct typos                 │
│  - Normalize synonyms/abbrevs    │
│  - Tag boolean logic (AND/OR)    │
│  - Handle corner cases           │
│                                  │
│  Output: QueryModel              │
└──────────────┬───────────────────┘
               │ (LLM is done here)
               ▼
┌──────────────────────────────────┐
│  Code: Concept Resolution        │
│  (deterministic, no LLM)        │
│                                  │
│  Each mention → concept lookup   │
│  → exact match → fuzzy match     │
│  → resolve to canonical concepts │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Code: Study Lookup              │
│  (deterministic, no LLM)        │
│                                  │
│  Intersect resolved concepts     │
│  → return matching studies       │
│  → return directly to user       │
└──────────────────────────────────┘
```

The LLM emits a `QueryModel` and is done. No study data flows through the LLM. Code handles resolution and results.

### The Hard Part: Mention Extraction

The LLM's sole job is parsing natural language into structured concept mentions. This is where the corner cases live:

- _"juvenile Hispanics with type one diabetes where insulin response was measured"_ → 3 mentions, not 1. "juvenile" is age, not "juvenile diabetes".
- _"blood pressure and diabetes"_ → 2 mentions with AND
- _"studies with BMI"_ → 1 mention, LLM normalizes abbreviation to "Body Mass Index"
- _"blood sugar studies"_ → 1 mention, LLM translates lay term to "Glucose" or "Fasting Glucose"
- _"echocardiography but not stress echo"_ → 1 AND, 1 NOT
- _"lipid panel"_ → could expand to multiple mentions (LDL, HDL, Triglycerides) or stay as one umbrella term — depends on what exists in the concept index

```python
class Mention(BaseModel):
    term: str           # normalized concept phrase
    bool_op: str        # "AND" | "OR" | "NOT"

class QueryModel(BaseModel):
    mentions: list[Mention]
```

Example: _"studies with blood pressure and diabetes"_ →
```
mentions: [
  {term: "Blood Pressure", bool_op: "AND"},
  {term: "Diabetes", bool_op: "AND"}
]
```

### Concept Resolution (code, no LLM)

Each mention term is looked up against the concept index:

1. **Exact match** — term matches a concept name
2. **Substring match** — "Blood Pressure" matches "Systolic Blood Pressure", "Diastolic Blood Pressure"
3. **Fuzzy match** — handles minor variations the LLM didn't catch

If a mention resolves to multiple concepts (e.g., "Blood Pressure" → Systolic + Diastolic), include all of them as an OR group.

### Study Lookup (code, no LLM)

Deterministic intersection of resolved concepts against the study index. AND = studies must have ALL concept groups. Results returned directly to the user — the LLM never sees them.

### LLM Retry (future enhancement)

If concept resolution fails for a mention, a second LLM call could rewrite the term and try again. But this is an optimization — start without it, measure the failure rate, add if needed.

## Concept Index

Built from `output/llm-concepts/*.json`. Two lookup structures:

### concept → studies

```json
{
  "Systolic Blood Pressure": {
    "study_count": 342,
    "variable_count": 4521,
    "studies": [
      {"study_id": "phs000007", "study_name": "Framingham Heart Study",
       "table_count": 31, "variable_count": 124},
      ...
    ]
  }
}
```

### study → concepts

```json
{
  "phs000007": {
    "study_name": "Framingham Heart Study",
    "concepts": ["Systolic Blood Pressure", "Diastolic Blood Pressure", ...],
    "concept_count": 847,
    "variable_count": 91702
  }
}
```

The concept vocabulary is small enough (estimated 1K-5K unique after normalization) to fit in memory and potentially in LLM context.

## Tech Stack

- **FastAPI** — API framework
- **Pydantic AI** — agent orchestration with typed tools
- **Anthropic Claude** — LLM for planning and retry (Haiku for cost, Sonnet option)
- **In-memory index** — concept database loaded from JSON at startup

No OpenSearch, no vector DB, no embeddings for Phase 1. The concept vocabulary is small enough for exact/fuzzy string matching. Upgrade path to OpenSearch + k-NN exists per DESIGN.md if needed.

## LLM Output Model

The LLM has no tools. It receives the query and emits structured output:

```python
class Mention(BaseModel):
    term: str           # normalized concept phrase
    bool_op: str        # "AND" | "OR" | "NOT"

class QueryModel(BaseModel):
    mentions: list[Mention]
```

The system prompt includes the concept vocabulary (or a summary) so the LLM knows what terms are resolvable. This is the only place the concept list enters the LLM context.

## Testing: Mention Extraction Evals

The hard problem is mention extraction, so we test it directly using pydantic-evals — same pattern as the concept classification evals.

```python
# Each eval case: NL query → expected QueryModel
mention_case(
    "simple-and",
    query="studies with blood pressure and diabetes",
    expected=[
        Mention(term="Blood Pressure", bool_op="AND"),
        Mention(term="Diabetes", bool_op="AND"),
    ],
)

mention_case(
    "abbreviation",
    query="studies with BMI data",
    expected=[
        Mention(term="Body Mass Index", bool_op="AND"),
    ],
)

mention_case(
    "lay-term",
    query="blood sugar studies",
    expected=[
        Mention(term="Glucose", bool_op="AND"),
    ],
)

mention_case(
    "complex-decomposition",
    query="juvenile Hispanics with type one diabetes where insulin was measured",
    expected=[
        Mention(term="Age", bool_op="AND"),
        Mention(term="Hispanic", bool_op="AND"),
        Mention(term="Type 1 Diabetes", bool_op="AND"),
        Mention(term="Insulin", bool_op="AND"),
    ],
)

mention_case(
    "negation",
    query="cardiac imaging but not stress echo",
    expected=[
        Mention(term="Cardiac Imaging", bool_op="AND"),
        Mention(term="Stress Echocardiography", bool_op="NOT"),
    ],
)
```

Build the eval suite first, then iterate the prompt against it — just like we did for concept classification.

## API

```
POST /api/concept-search
{
  "query": "studies with systolic blood pressure and diabetes"
}

Response:
{
  "concepts_matched": [
    {"concept": "Systolic Blood Pressure", "study_count": 342},
    {"concept": "Diabetes History", "study_count": 156}
  ],
  "studies": [
    {"study_id": "phs000007", "study_name": "Framingham Heart Study",
     "matched_concepts": ["Systolic Blood Pressure", "Diabetes History"],
     "variable_count": 187},
    ...
  ],
  "total_studies": 47,
  "explanation": "Found 47 studies measuring both."
}
```

## Phases

### Phase 1: Mention Extraction Agent + Evals

- Build mention extraction agent with pydantic-evals test harness
- Iterate prompt against eval cases until mention extraction is reliable
- CLI: `python concept_search.py "studies with blood pressure"`
- No API yet — focus on getting the LLM to reliably parse mentions

### Phase 2: Concept Index + End-to-End Pipeline

- Build concept index from classification output
- Wire up: LLM mention extraction → concept resolution → study lookup
- End-to-end CLI that returns actual study results

### Phase 3: API Endpoint

- FastAPI app wrapping the pipeline
- Streaming responses
- Query logging to identify common mention extraction failures

### Phase 4: Enrichment

- UMLS CUI grounding per concept (synonym expansion)
- Concept normalization (merge synonyms from classification)
- LLM retry for failed concept resolution
- Domain grouping (Cardiovascular, Pulmonary, Behavioral, etc.)

## Dependencies

- Variable-level concept classification output (complete or in progress)
- Concept normalization pass (reduces synonym sprawl)
- Anthropic API key for query-time LLM calls

## Open Questions

1. **Concept count after normalization** — determines if full vocab fits in LLM context as system prompt
2. **Query latency budget** — Haiku ~1s vs Sonnet ~3s per LLM call, 2-3 calls per query
3. **Hosting** — separate Python service from the Next.js frontend
4. **Synonym quality** — how much does the LLM retry rate drop after UMLS grounding?
