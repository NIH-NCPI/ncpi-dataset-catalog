# Backend Request Flow

How a `/search` request is processed, step by step.

---

## 1. HTTP Entry — Front Controller

**File**: [api.py](../backend/concept_search/api.py) (line 332)

The `POST /search` endpoint receives a `SearchRequest`:

- `query` — natural language text (may be empty)
- `previous_query` — a `QueryModel` round-tripped from the client (may be null)

Rate limiting is checked per-IP. Then the controller determines the **mode**:

| Condition           | Mode        | What happens                                                                                                                                                  |
| ------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| query + no previous | **fresh**   | Full 3-agent pipeline                                                                                                                                         |
| query + previous    | **route**   | Router agent classifies the follow-up                                                                                                                         |
| no query + previous | **requery** | Skip LLM, re-run lookup on previous QueryModel (e.g., after the UI removes a filter — the client patches the QueryModel and resubmits without new query text) |

---

## 2. Mode: Fresh — Full Pipeline

**File**: [pipeline.py](../backend/concept_search/pipeline.py) (line 298)

Entry: `run_pipeline(query)`. Checks the **pipeline cache** first
(key: `query.strip().lower()`, LRU with TTL). On miss, runs the three agents:

### 2.1 Extract Agent (sequential)

**File**: [extract_agent.py](../backend/concept_search/extract_agent.py)
**Prompt**: [EXTRACT_PROMPT.md](../backend/concept_search/EXTRACT_PROMPT.md)
**Model**: Haiku

**Input**: raw query string
**Output**: `ExtractResult` — a list of `RawMention` items + an `intent`

Each `RawMention` has:

- `facet` — which dimension (platform, focus, measurement, consentCode, etc.)
- `text` — the user's phrase
- `values` — **pre-resolved** for small-cardinality facets (see below)

**Small facets** (resolved here, not by the resolve agent):

- platform, dataType, studyDesign, sex, raceEthnicity, computedAncestry
- The full value list is in the prompt; the LLM picks matches directly

**Large facets** (text only, resolved later):

- focus, measurement, consentCode
- `values` left empty; the resolve agent handles them

**Intent detection**: `"study"` (find datasets), `"variable"` (find measured
variables), or `"auto"` (ambiguous — ask for clarification)

### 2.2 Resolve Agent + Structure Agent (parallel)

These two run concurrently via `asyncio.gather()`.

#### 2.2.1 Resolve Agent

**File**: [resolve_agent.py](../backend/concept_search/resolve_agent.py)
**Prompt**: [RESOLVE_PROMPT.md](../backend/concept_search/RESOLVE_PROMPT.md)
**Model**: Haiku
**Deps**: `ConceptIndex` (injected via pydantic-ai `deps`)

**Input**: one `RawMention` (called per-mention, in parallel)
**Output**: `ResolveResult` — either `values` (resolved) or `disambiguation` (ambiguous)

Each mention that wasn't pre-resolved by extract gets its own resolve call.
Results are cached per `(facet, normalized_text)` in the **resolve cache** (LRU
with TTL).

**Resolution strategy depends on the facet type:**

##### Focus (disease/condition)

1. **Primary**: `search_concepts_by_embedding()` — semantic KNN over MeSH
   disease embeddings
2. **Drill-down**: `get_focus_category_terms()` — browse MeSH category tree
3. **Fallback**: `search_concepts()` — keyword substring match
4. **Post-processing**: ISA deduplication — if both a parent and its descendant
   are selected, the descendant is dropped (the parent's closure already
   includes it)

##### Measurement (what was measured)

1. **Primary**: `search_concepts_by_embedding()` — semantic KNN over
   measurement concept embeddings (TOPMed, PhenX, NCPI vocabularies)
2. **Drill-down**: `get_concept_children()` — navigate the measurement
   hierarchy; `list_variables_for_concept()` — verify at leaf level
3. **Category browse**: `get_measurement_category_concepts()` — keyword search
   within concept namespaces
4. **Ancestor preference**: the resolve prompt instructs the LLM to prefer
   parent concepts from the `ancestors` list returned by embedding search,
   giving broader coverage

##### Consent Code

Two resolution patterns:

- **Pattern A — explicit code**: user says "GRU" or "HMB-IRB" →
  `values=["explicit:GRU"]`. Tools: `get_consent_code_categories()`,
  `get_consent_codes_for_base()`, `get_disease_specific_codes()`
- **Pattern B — research use case**: user says "for-profit research" →
  `values=["no-npu"]` (a symbolic tag). Tool:
  `compute_consent_eligibility()` determines which codes are eligible

Tags are expanded to actual code lists later in step 4.

##### Disambiguation

If the resolve agent can't determine a unique match, it returns
`disambiguation` — a list of 2-3 options with labels. When disambiguation is
present, `values` is forced empty (mutual exclusivity invariant). The client
shows the options; the user picks one in a follow-up (handled by the router
agent's `RouteSelect`).

#### 2.2.2 Structure Agent

**File**: [structure_agent.py](../backend/concept_search/structure_agent.py)
**Prompt**: [STRUCTURE_PROMPT.md](../backend/concept_search/STRUCTURE_PROMPT.md)
**Model**: Haiku

**Input**: query text + placeholder mentions (facet + text only, no values)
**Output**: `QueryModel` with `exclude` flag set per mention

Determines boolean logic: which mentions are inclusive (AND) vs. exclusive
(NOT). Runs on placeholders so it doesn't need to wait for resolve.

### 2.3 Merge (deterministic)

**File**: [pipeline.py](../backend/concept_search/pipeline.py) (line 132)

Zips together:

- **Values** from resolve (step 2.2.1)
- **Exclude flags** from structure (step 2.2.2)

Produces a `QueryModel` with fully resolved mentions, each carrying both its
canonical values and its boolean role.

### 2.4 Multi-turn Merge (if previous_query exists)

**File**: [pipeline.py](../backend/concept_search/pipeline.py) (line 168)

When the user is refining a previous query (via route → add/replace), the new
mentions are merged with previous ones:

- Key: `(facet, original_text)` — new mentions overwrite previous on collision
- Intent: preserved from previous unless the new extraction explicitly returns
  a non-default intent

---

## 3. Mode: Route — Multi-turn Follow-up

**File**: [api.py](../backend/concept_search/api.py) (line 234)
**Router**: [router_agent.py](../backend/concept_search/router_agent.py)
**Prompt**: [ROUTER_PROMPT.md](../backend/concept_search/ROUTER_PROMPT.md)
**Model**: Haiku

**Input**: new query text + previous QueryModel
**Output**: one of five route types (discriminated union)

| Route          | User intent                 | What happens                                      |
| -------------- | --------------------------- | ------------------------------------------------- |
| `RouteAdd`     | "also filter by X"          | Run pipeline on new text with previous as context |
| `RouteRemove`  | "drop the sex filter"       | Remove matching mentions by original_text         |
| `RouteReplace` | "change cancer to diabetes" | Remove old mention, pipeline on new text          |
| `RouteSelect`  | "the second one"            | Pick from disambiguation options                  |
| `RouteReset`   | "start over with Y"         | Fresh pipeline, ignore previous state             |

All routes except Reset preserve the previous intent.

---

## 4. Constraint Expansion

**File**: [mention_constraints.py](../backend/concept_search/mention_constraints.py) (line 48)

Converts `ResolvedMention` list into two lists of `(facet, values)` constraint
tuples: **include** and **exclude**.

**Consent tag expansion** (NCPI-specific):

1. Infer scope from sibling focus mentions: `"general"` | `"health"` | `"disease"`
2. If disease scope, resolve disease name from focus mentions
3. Expand symbolic tags (e.g., `"no-npu"`, `"explicit:GRU"`) into actual
   consent code lists via [consent_logic.py](../backend/concept_search/consent_logic.py)

---

## 5. Deterministic Lookup

**File**: [api.py](../backend/concept_search/api.py) (line 412)
**Store**: [store.py](../backend/concept_search/store.py)
**Index**: [index.py](../backend/concept_search/index.py)

Branches on intent:

| Intent     | Lookup                                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------- |
| `auto`     | Skip — return clarification message only                                                                                    |
| `study`    | `store.query_studies(include, exclude)` — faceted study search                                                              |
| `variable` | Filter studies by non-measurement constraints, then `store.query_variables(concepts, study_ids)` with ISA closure expansion |

**Boolean semantics**:

- Within a mention: values are **OR**-ed
- Between include mentions: **AND**-ed
- Exclude mentions: subtracted (**NOT**)

**ISA closure**: querying for a parent concept (e.g., `ncpi:biomarkers`)
matches all descendant variables. Implemented via `concept_ids_closure` array
stored on each variable row.

---

## 6. Response Building

**File**: [response_summary.py](../backend/concept_search/response_summary.py)

### 6.1 Query Structure

`build_query_structure()` (line 55) converts the QueryModel into a
`QueryStructure` — a list of `QueryClause` items, each with human-readable
labels, the facet, and the boolean operator.

### 6.2 Message

Three paths:

| Condition              | Function                   | Result                                                          |
| ---------------------- | -------------------------- | --------------------------------------------------------------- |
| Results found          | `build_message()`          | "Found 42 studies in focus Lung Neoplasms on BioData Catalyst." |
| Zero results           | `diagnose_empty_results()` | "Found 0 studies. Removing the platform filter would find 15."  |
| Disambiguation pending | (keep resolve message)     | "Which did you mean? 1) Current Age 2) Age at Diagnosis"        |

`diagnose_empty_results()` does a **drop-one-at-a-time** analysis: re-queries
without each constraint to tell the user which filter is too restrictive.

---

## 7. HTTP Response

**File**: [api_models.py](../backend/concept_search/api_models.py)

Returns `SearchResponse`:

- `intent` — study / variable / auto
- `message` — human-readable summary or disambiguation prompt
- `query` — the full `QueryModel` (round-tripped to client for multi-turn)
- `query_structure` — clauses with labels for the UI filter display
- `studies` — matched study summaries (study intent)
- `variables` — matched variable rows (variable intent)
- `timing` — pipeline_ms, lookup_ms, total_ms
- `total_studies`, `total_variables` — counts (variables may be capped at 500)

---

## Caching

| Layer    | Key                             | Scope                | Default TTL | Default Size |
| -------- | ------------------------------- | -------------------- | ----------- | ------------ |
| Pipeline | `query.strip().lower()`         | Full QueryModel      | 24h         | 10,000       |
| Resolve  | `(facet, text.strip().lower())` | Single ResolveResult | 24h         | 10,000       |

Pipeline cache is **bypassed** for multi-turn requests (session-specific state).
Resolve cache is **always active** — even in multi-turn, individual mention
resolutions are reused.

---

## Data Flow Diagram

```
POST /search(query, previous_query?)
  │
  ├── requery ──────────────────────────────────────┐
  │                                                  │
  ├── route ─→ Router Agent ─→ RouteAdd/Remove/...  │
  │              │                                   │
  │              ├─ RouteSelect → patch mention      │
  │              ├─ RouteRemove → drop mentions      │
  │              ├─ RouteReplace → remove + pipeline  │
  │              ├─ RouteReset → fresh pipeline       │
  │              └─ RouteAdd → pipeline + merge       │
  │                                                  │
  ├── fresh ─→ Pipeline                              │
  │    │                                             │
  │    ├─ 1. Extract Agent                           │
  │    │     query → RawMention[] + intent           │
  │    │                                             │
  │    ├─ 2. (parallel)                              │
  │    │     ├─ Resolve Agent (per mention)           │
  │    │     │    RawMention → ResolveResult          │
  │    │     │    (values or disambiguation)          │
  │    │     │                                       │
  │    │     └─ Structure Agent                      │
  │    │          mentions → exclude flags            │
  │    │                                             │
  │    ├─ 3. Merge                                   │
  │    │     values + flags → QueryModel             │
  │    │                                             │
  │    └─ 4. Multi-turn merge (if previous)          │
  │          new + previous → merged QueryModel      │
  │                                                  │
  ▼                                                  │
QueryModel ◄────────────────────────────────────────┘
  │
  ├─ Constraint expansion (consent tag → code lists)
  │
  ├─ Deterministic lookup (DuckDB)
  │    ├─ study intent  → query_studies()
  │    └─ variable intent → query_variables() with ISA closure
  │
  ├─ Response building
  │    ├─ query_structure (clauses + labels)
  │    ├─ message (summary or diagnosis)
  │    └─ timing
  │
  └─ SearchResponse
```
