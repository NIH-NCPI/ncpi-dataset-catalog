# PRD: Variable-Level Search

## Problem

The AI search currently only returns **studies**. Researchers also need to find
**specific variables** — e.g., "what variables measured chocolate consumption?"
— and get back the actual variable names, dbGaP IDs, and links rather than a
list of studies that happen to contain related concepts.

Today the pipeline collapses variable-level detail (name, PHV ID, description,
table) into study-level concept counts during indexing. The rich per-variable
data in `llm-concepts/*.json` is loaded but immediately aggregated away.

## Goals

1. Support **variable-level queries** alongside existing study-level queries.
2. Automatically determine query intent (study vs. variable) from context; ask
   when ambiguous.
3. Return variable-level detail: canonical concept, variable name, dbGaP PHV
   ID, dataset/table, study, and a link to dbGaP.

## User Stories

| #   | Story                                                                                           | Example Query                                                                                        |
| --- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| 1   | As a researcher, I want to search for variables that measure a specific thing                   | "What variables measured chocolate consumption?"                                                     |
| 2   | As a researcher, I want to see the dbGaP variable ID and a link so I can navigate to the source | (result includes `phv00481718.v2.p1` with hyperlink)                                                 |
| 3   | As a researcher, I want the system to figure out whether I'm asking about studies or variables  | "diabetes datasets" → studies; "what's measured for blood pressure?" → variables                     |
| 4   | As a researcher, I want to be asked for clarification when intent is ambiguous                  | "blood pressure" → "Are you looking for studies about blood pressure, or variables that measure it?" |

## Design

### Query Intent Detection

The **extract agent** gains a new `intent` field on its output:

| Intent     | When                                                                      | Example                                         |
| ---------- | ------------------------------------------------------------------------- | ----------------------------------------------- |
| `study`    | User asks about datasets, studies, cohorts, platforms, consent            | "diabetes datasets on AnVIL"                    |
| `variable` | User asks what is measured, what variables exist, column names            | "what variables measure chocolate consumption?" |
| `auto`     | System infers from context (default) — falls back to `study` when unclear | "blood pressure" with no other context          |

**Inference heuristics** (for the extract agent prompt):

- Keywords signalling `variable` intent: "variable(s)", "measured", "what is
  measured", "column", "field", "phenotype variable", "which measurements"
- Keywords signalling `study` intent: "study/studies", "dataset(s)",
  "cohort(s)", "trial(s)", "platform", "released"
- When the user asks "what X" or "which X" where X is a measurement concept,
  default to `variable`
- When intent cannot be determined, set `intent: "auto"` and add a `message`
  asking the user to clarify: "Are you looking for studies about X, or
  variables that measure X?"

### Variable Index

Currently `_load_measurement_concepts()` only stores concept → study mappings.
For variable search, the index must also store per-variable rows:

**New DuckDB table: `variables`**

| Column          | Type         | Source                          |
| --------------- | ------------ | ------------------------------- |
| `phv_id`        | `VARCHAR` PK | `var.id` from llm-concepts JSON |
| `variable_name` | `VARCHAR`    | `var.name`                      |
| `description`   | `VARCHAR`    | `var.description`               |
| `concept`       | `VARCHAR`    | `var.concept` (canonical)       |
| `dataset_id`    | `VARCHAR`    | `table.datasetId`               |
| `table_name`    | `VARCHAR`    | `table.tableName`               |
| `study_id`      | `VARCHAR` FK | `data.studyId`                  |

**Estimated size**: ~75,000 rows (from concept-summary stats).

The existing `study_facet_values` EAV table and concept index remain unchanged
for study-level queries.

### Variable Query Execution

When `intent == "variable"`:

1. **Extract** identifies the measurement concept(s) as usual.
2. **Resolve** maps to canonical concept name(s) as usual.
3. **Lookup** queries the `variables` table instead of the `studies` table:
   ```sql
   SELECT v.*, s.raw_json
   FROM variables v
   JOIN studies s ON v.study_id = s.db_gap_id
   WHERE v.concept IN (?)
   ORDER BY v.concept, v.study_id
   ```
4. **Response** returns `VariableResult` objects (see API response below).

### API Response

**New response model for variable results:**

```python
class VariableResult(BaseModel):
    concept: str              # Canonical concept name (e.g., "Chocolate Intake")
    datasetId: str            # dbGaP dataset (e.g., "pht001210.v3")
    dbGapUrl: str             # Link to variable on dbGaP
    phvId: str                # dbGaP variable accession (e.g., "phv00481718.v2.p1")
    studyId: str              # Parent study (e.g., "phs000007")
    studyTitle: str           # Study title for display context
    tableName: str            # Dataset table name
    variableDescription: str  # Description from var_report
    variableName: str         # Raw variable name (e.g., "CHOC_INTAKE")
```

**`SearchResponse` changes:**

```python
class SearchResponse(BaseModel):
    intent: str               # "study" | "variable"
    message: str | None
    query: QueryModel
    studies: list[StudySummary]          # populated when intent == "study"
    timing: SearchTiming
    totalStudies: int                    # populated when intent == "study"
    totalVariables: int                  # populated when intent == "variable"
    variables: list[VariableResult]      # populated when intent == "variable"
```

### dbGaP Variable URL

Format:

```
https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi?study_id={studyAccession}&phv={phvNumeric}
```

The `phv_id` from the JSON is like `phv00481718.v2.p1`. The URL needs the
study accession (with version) and the numeric PHV portion. The study accession
version can be looked up from the study record; the PHV numeric part is
extracted from the ID string.

### Extract Agent Prompt Changes

Add to `EXTRACT_PROMPT.md`:

```markdown
## Query Intent

In addition to extracting mentions, determine the user's **intent**:

- **"study"** — the user wants to find studies/datasets.
  Signals: "studies", "datasets", "cohorts", "trials", "on AnVIL/BDC",
  "released after", "consented for"

- **"variable"** — the user wants to find specific measured variables.
  Signals: "variables", "what is measured", "what measures", "columns",
  "fields", "which phenotype variables", "what data is collected"

- **"auto"** — you cannot determine intent from context.
  Set `message` to ask: "Are you looking for studies about [X], or
  variables that measure [X]?"

Default to "study" when the query mentions platforms, consent codes, study
designs, or other study-level facets. Default to "variable" when the query
is specifically asking about what is measured or what variables exist.
```

### Structure Agent

No changes needed — the structure agent's exclude/include logic applies
identically to variable queries (the mentions are the same, just the lookup
target differs).

### Pipeline Changes

- `ExtractResult` gains an `intent: str` field (default `"study"`).
- `run_pipeline()` passes intent through to the API layer.
- API layer branches on intent: study path (existing) vs. variable path (new
  `query_variables()` method on store).

### Frontend

- When `intent == "variable"`, render a variable results table instead of the
  study table:
  - Columns: Concept | Variable Name | Description | Study | dbGaP Link
  - The dbGaP link should open in a new tab
- When `intent == "auto"` and a clarification message is returned, display
  the message and let the user refine their query.

## Scope

### In Scope

- Extract agent intent detection (study / variable / auto)
- `variables` table in DuckDB populated from llm-concepts JSON
- `query_variables()` method on DuckDBStore
- `VariableResult` API response model
- dbGaP variable URL construction
- Frontend variable results table
- Clarification flow for ambiguous intent

### Out of Scope (Follow-up)

- Cross-study variable harmonization / equivalence
- Variable-level faceted filtering (e.g., "WGS variables only")
- Exporting / downloading variable search results
- Searching variable descriptions (free-text) beyond concept matching

## Key Files

| File                                       | Change                                                     |
| ------------------------------------------ | ---------------------------------------------------------- |
| `backend/concept_search/models.py`         | Add `intent` field to `ExtractResult`                      |
| `backend/concept_search/EXTRACT_PROMPT.md` | Add intent detection guidance                              |
| `backend/concept_search/store.py`          | Add `variables` table, `query_variables()`                 |
| `backend/concept_search/index.py`          | Populate variables table in `_load_measurement_concepts()` |
| `backend/concept_search/pipeline.py`       | Pass intent through pipeline                               |
| `backend/concept_search/api.py`            | Branch on intent, build variable response                  |
| `backend/concept_search/api_models.py`     | Add `VariableResult`, update `SearchResponse`              |
| `app/components/Chat/chat.tsx`             | Variable results table rendering                           |

## Open Questions

1. **Result limits**: How many variable results to return? Could be hundreds
   for common concepts. Paginate, or cap at N (e.g., 100)?
2. **Grouping**: Should variable results be grouped by study, by concept, or
   flat?
3. **Mixed queries**: "diabetes studies with blood pressure variables" — study
   intent with a variable sub-query? Save for follow-up?
4. **Variable description search**: Should we support searching variable
   descriptions directly (beyond concept matching)?
