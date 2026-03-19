# PRD: Response Summary & Empty-Results Recovery

## Problem

When the search API returns results, the user sees a table and filter chips but no conversational feedback. There's no "I found 33 studies matching blood pressure in pediatric populations" — just a silent table swap. Users can't tell at a glance what the system understood, how many things matched, or why.

Worse, when zero results come back, the user sees "No results found." with filter chips but no guidance on which filters are too restrictive or what to drop. The only escape is manually clicking X on chips one at a time and hoping something works.

## Current Behavior

The `message` field on `SearchResponse` is already rendered in the assistant message area (via findable-ui's `AssistantMessage` component). Today it's only set for:

- **Disambiguation**: "Which did you mean?" + options (resolve agent)
- **Removal confirmation**: "Removed diabetes." (router)
- **Errors/timeouts**: "Search timed out" / "Something went wrong"

For successful queries with results — or queries with zero results — `message` is `None`.

## Proposed Behavior

Set `message` on every response. Three tiers:

### 1. Result Summary (has results)

A plain-English sentence summarizing what was found.

**Format**: `Found {N} studies [with {M} variables] matching {english_query}.`

The `english_query` is a human-readable rendering of the resolved query — not the raw input, but what the system actually searched for. This reveals the structure of the query so the user can verify the system understood them correctly.

**Examples**:

| User typed                                     | english_query                                            |
| ---------------------------------------------- | -------------------------------------------------------- |
| "blood pressure in kids"                       | blood pressure in pediatric populations                  |
| "lung cancer studies on BDC with genomic data" | lung cancer on BioData Catalyst, with genomic data types |
| "NOT diabetes"                                 | studies excluding diabetes                               |
| "BMI and smoking"                              | body mass index and smoking behavior                     |

**Rules for english_query**:

- Render each resolved mention by its concept label (not the raw text, not the concept ID)
- Group by role: measurement mentions as the main subject, then platform/dataType/focus/studyDesign as qualifiers
- Use "and" for multiple same-facet mentions, "excluding {X}" for negated mentions
- Keep it one sentence, no jargon

**Full examples**:

```
Found 33 studies matching blood pressure in pediatric populations.
Found 12 studies with 847 variables matching body mass index and smoking behavior.
Found 5 studies matching genomic data on BioData Catalyst, excluding diabetes.
```

### 2. Query Structure (always, as subtext)

Below the summary, show a structured breakdown that reveals how mentions combine — the and/or/not logic that actually drives the query.

**What exists today (insufficient)**:

findable-ui's `AssistantMessage` renders two lines:

- "Extracted mentions:" — flat comma-separated original texts (`blood pressure, kids, BDC`)
- "Extracted mappings:" — facet-values dump (`measurement: bp_systolic, bp_diastolic / platform: BDC`)

Neither shows grouping or boolean logic. The user can't tell whether "blood pressure AND diabetes" means studies must have both, or that two separate concepts were resolved, or how platform filters intersect with measurement filters.

**Proposed structure line**:

Render the query as a human-readable boolean expression, grouped by role:

```
Searching for: blood pressure (bp_systolic, bp_diastolic) AND smoking behavior
  on: BioData Catalyst
  excluding: diabetes
```

**Formatting rules**:

- **Measurements** listed first as the main subject, joined with AND
- Each measurement shows its concept label, with resolved child concepts in parentheses if >1 value was resolved from a single mention
- **Platform/dataType/focus/studyDesign** shown as qualifying clauses with "on:" / "with:" / "in:" prefixes
- **Excluded mentions** shown with "excluding:" prefix
- Multiple mentions within the same facet are joined with AND (they intersect)

**More examples**:

```
Searching for: body mass index AND subject age
  with: genomic data
```

```
Searching for: blood pressure
  on: AnVIL, BioData Catalyst
  in: cardiovascular disease
  excluding: pediatric populations
```

```
Searching for variables: blood pressure AND hemoglobin A1c
```

#### Two delivery mechanisms (ship both)

**A. Pre-built string in `message`** — the backend renders the summary + structure + refinements as a single text block. The frontend displays it immediately via the existing `AssistantMessage` component. This is the v1 experience.

**B. Structured metadata in `query_structure`** — a new field on `SearchResponse` that returns the resolved query as typed data, so the frontend can render it with richer formatting later (clickable groups, interactive refinement, etc.).

```python
class QueryClause(BaseModel):
    """A single clause in the structured query breakdown."""
    facet: Facet
    labels: list[str]       # Human-readable concept labels (not IDs)
    exclude: bool = False
    operator: str = "AND"   # How this clause combines with others

class QueryStructure(BaseModel):
    """Structured representation of the resolved query for frontend rendering."""
    clauses: list[QueryClause]
    intent: Intent
    summary: str            # The pre-built english summary sentence
```

**Response shape** (new fields highlighted):

```json
{
  "message": "Found 33 studies matching blood pressure and smoking behavior.\nSearching for: blood pressure (bp_systolic, bp_diastolic) AND smoking behavior\n  on: BioData Catalyst\n  excluding: diabetes\nYou could narrow by disease focus or data type.",
  "queryStructure": {
    "intent": "study",
    "summary": "Found 33 studies matching blood pressure and smoking behavior.",
    "clauses": [
      { "facet": "measurement", "labels": ["blood pressure"], "exclude": false, "operator": "AND" },
      { "facet": "measurement", "labels": ["smoking behavior"], "exclude": false, "operator": "AND" },
      { "facet": "platform", "labels": ["BioData Catalyst"], "exclude": false, "operator": "AND" },
      { "facet": "focus", "labels": ["diabetes"], "exclude": true, "operator": "NOT" }
    ]
  },
  "query": { ... },
  "studies": [ ... ],
  "totalStudies": 33
}
```

The concept labels come from the existing `concept_id → {"name", "description"}` vocabulary lookup already loaded by the index (`_load_concept_descriptions()`). For small facets (platform, dataType, studyDesign), the values are already human-readable.

The existing "Extracted mentions" / "Extracted mappings" lines from findable-ui remain as-is for now — slightly redundant but useful as a debug view until the structured query rendering is proven out. Can suppress later.

### 3. Refinement Suggestions (when useful)

Append refinement hints when the result set is large enough to benefit from narrowing.

**Threshold**: Show suggestions when `total_studies > 10`.

**Format**: Append to message:

```
You could narrow by {suggestion1}, {suggestion2}, or {suggestion3}.
```

**Suggestion sources** (pick top 3 that apply):

| Condition                                                       | Suggestion                                 |
| --------------------------------------------------------------- | ------------------------------------------ |
| No platform filter and results span multiple platforms          | "platform (results span AnVIL, BDC, CRDC)" |
| No data type filter and results have mixed data types           | "data type"                                |
| No focus/disease filter and results span multiple disease areas | "disease focus"                            |
| No consent filter                                               | "consent type"                             |
| Intent is "study" and variables exist                           | "switching to variable-level search"       |

**Example full message**:

```
Found 33 studies matching blood pressure.
You could narrow by platform (results span AnVIL, BDC), disease focus, or data type.
```

---

## Zero Results: Recovery Guidance

This is the critical UX gap. When `total_studies == 0 AND total_variables == 0`:

### Diagnosis

Determine _why_ results are empty by progressively relaxing filters. The lookup layer is fast (~5ms), so we can afford to re-query.

**Algorithm** (server-side, in `api.py` after the main lookup returns 0):

```
1. Start with all N mentions.
2. For each mention, compute: "if I drop this one mention, how many studies match?"
   (N queries, each ~5ms — negligible for N < 10)
3. Classify the result:
   a. ONE mention kills everything → that mention is the bottleneck
   b. COMBINATION kills everything → the intersection is too narrow
   c. NO individual mention has results → each mention alone is too restrictive
```

### Message Format

**Case A — Single bottleneck mention**:

```
No studies found matching blood pressure and rare genetic disorder X on BioData Catalyst.
Dropping "rare genetic disorder X" would match 14 studies.
Dropping "BioData Catalyst" would match 3 studies.
```

**Case B — Intersection too narrow**:

```
No studies found matching blood pressure and diabetes on BioData Catalyst with genomic data.
Each filter alone has results, but the combination is too narrow.
Try removing "BioData Catalyst" (→ 8 studies) or "genomic data" (→ 12 studies).
```

**Case C — Nothing matches at all**:

```
No studies found matching "flurbotronic spectral analysis."
This term didn't resolve to any known concepts. Try rephrasing or using a more common term.
```

Note: Case C should be rare since the resolve agent already handles unresolvable terms. This is a fallback for when resolution succeeds but the concept has zero indexed studies/variables.

### Recovery Actions

The message text includes the drop suggestions. The user can then:

1. **Type a follow-up** like "drop rare genetic disorder X" (handled by existing router, route=remove)
2. **Click the X on a chip** to remove a filter (existing behavior, #270 tracks showing this in chat)
3. **Start fresh** with a new query

No new UI components needed — the message renders in the existing text area, and chips are already removable.

---

## Implementation

### Backend Changes

**New models** (`api_models.py`):

- `QueryClause` — facet + labels + exclude + operator
- `QueryStructure` — clauses + intent + summary string
- Add `query_structure: QueryStructure | None` field to `SearchResponse`

**New module** (`response_summary.py`) — keeps `api.py` clean:

- `build_query_structure(query_model, index) -> QueryStructure` — resolve concept IDs to labels, group by facet, compute the summary sentence
- `build_message(query_structure, n_studies, n_variables, index) -> str` — render the full message text (summary + structure block + refinement suggestions)
- `diagnose_empty_results(query_model, index) -> str` — drop-one-at-a-time analysis for zero-result recovery
- `suggest_refinements(query_model, studies, index) -> str | None` — append narrowing hints when result set is large

**In `api.py`** — after the lookup (line ~454), before building `SearchResponse`:

```python
# Build structured query + summary message
query_structure = build_query_structure(query_model, index)
if query_model.message:
    # Disambiguation/removal — keep existing message, still return structure
    message = query_model.message
elif not studies and not variable_rows and query_model.mentions:
    # Zero results — recovery guidance
    message = diagnose_empty_results(query_model, index)
else:
    # Normal results — summary + structure + refinements
    message = build_message(query_structure, len(studies), total_variable_count, index)

response = SearchResponse(
    ...
    message=message,
    query_structure=query_structure,
)
```

### Preserving Existing Messages

The pipeline already sets `query_model.message` for disambiguation/removal. The summary should **not overwrite** these — instead:

- If `query_model.message` is already set (disambiguation, removal, etc.), use it as-is
- Only generate the summary when `query_model.message is None`

### Frontend Changes

**v1 (this PR)**: None. The pre-built `message` string renders via the existing `AssistantMessage` component. The `queryStructure` field is returned but ignored by the frontend for now.

**v2 (future)**: The frontend reads `queryStructure` and renders it as an interactive component — clickable facet groups, inline remove buttons, etc. At that point, suppress the `message` text block and the legacy "Extracted mentions/mappings" lines.

### No LLM Calls

The summary and recovery messages are generated with deterministic string formatting. No additional LLM calls. The english_query is built from the already-resolved mention labels and facets.

---

## Open Questions

1. **Variable-intent queries**: When intent is "variable", should the summary say "Found 847 variables across 12 studies" or just "Found 847 variables"? Leaning toward including the study count for context.

2. **Refinement suggestion ordering**: Should we rank suggestions by how much they'd narrow results (requires extra queries) or just use a static priority order?

3. **Message length**: The zero-results diagnosis could get verbose with many mentions. Cap at showing top 3 drop suggestions?

4. **Requery mode**: When the user removes a chip (requery, no LLM), should we still generate a summary? Leaning yes — the summary confirms what happened.
