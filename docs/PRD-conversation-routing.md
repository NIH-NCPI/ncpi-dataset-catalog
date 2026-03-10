# PRD: Conversation Routing & Disambiguation #268

**Issue**: #268
**Status**: Draft
**Date**: 2026-03-09

## Pipeline Modes

| Mode        | Trigger                                  | Description                                                                                                                                         |
| ----------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **fresh**   | `query` present, no `previousQuery`      | First query in a conversation. Runs the full LLM pipeline: extract → resolve → structure.                                                           |
| **requery** | No `query`, `previousQuery` present      | Re-run the database query with the current mentions. No LLM calls. Used when the client mutates mentions directly (e.g. chip removal via X button). |
| **route**   | `query` present, `previousQuery` present | User sent a follow-up message. An LLM router classifies the intent (add, remove, replace, select, reset) before dispatching.                        |

## Problem

The search pipeline currently handles three modes — fresh, route, requery — determined by the presence of `query` and `previousQuery`. This works for simple flows but breaks down when:

1. The resolve agent returns a disambiguation question ("Did you mean X or Y?")
2. The user responds to that question in natural language
3. The system needs to figure out what the response means and act accordingly

Today the pipeline treats every follow-up as a refinement (extract new mentions, merge with previous). It has no concept of "the user is answering a question we asked."

## Conversation Types

### Turn 1: Original Query

User submits a fresh query with no prior state.

```
User: "glucose in diabetes studies"
System: extracts [measurement: glucose, focus: diabetes]
        → resolve finds glucose is ambiguous
        → returns disambiguation question + filter chips for diabetes
```

### Turn 2a: Disambiguation Response

User responds to a disambiguation question. Four sub-types:

| Response            | Example                             | Action                                                          |
| ------------------- | ----------------------------------- | --------------------------------------------------------------- |
| **Select one**      | "blood glucose"                     | Resolve the disambiguation mention with the selected concept    |
| **Select multiple** | "both blood glucose and dietary"    | Resolve with multiple selected concepts                         |
| **Replace**         | "actually I meant meat consumption" | Drop the disambiguation mention, extract & resolve the new term |
| **Reject all**      | "never mind the glucose part"       | Drop the disambiguation mention entirely                        |

### Turn 2b: Refinement

User modifies criteria while keeping prior context.

| Response    | Example                      | Action                                         |
| ----------- | ---------------------------- | ---------------------------------------------- |
| **Add**     | "also on AnVIL"              | Extract new mention, merge with previous       |
| **Remove**  | "remove the diabetes filter" | Remove the specified mention(s)                |
| **Replace** | "change diabetes to asthma"  | Remove old mention, extract & resolve new term |

Note: chip removal via the UI X button is already handled (requery mode). Add/remove/replace here cover the _chat-based_ equivalents.

### Turn 2c: Subject Change

User abandons the current query entirely.

| Response      | Example                        | Action                            |
| ------------- | ------------------------------ | --------------------------------- |
| **New topic** | "show me COPD studies instead" | Clear state, start fresh pipeline |

## Router Decision Tree

The router runs only in **route mode** (both `query` and `previousQuery` present). It classifies the user's follow-up message and dispatches accordingly.

```
User sends follow-up message
  │
  ├─ Is disambiguation pending?
  │   │
  │   ├─ YES ─── Does the message answer the question?
  │   │            │
  │   │            ├─ Picks option(s) ───────→ select  (set values from chosen concept_ids, requery)
  │   │            ├─ Rejects all ───────────→ remove  (drop the ambiguous mention entirely, requery)
  │   │            │                            System responds: "OK, removed. How would you like to refine your search?"
  │   │            ├─ Wants something else ──→ replace (drop mention + options, run pipeline on new term)
  │   │            │                            e.g. "actually I meant meat consumption"
  │   │            └─ Unrelated ─────────────→ reset   (clear everything, run pipeline fresh)
  │   │                                         e.g. "show me COPD studies instead"
  │   │
  │   └─ NO ──── What is the user doing?
  │               │
  │               ├─ Adding new criteria ────→ add     (run pipeline, merge with previous)
  │               ├─ Removing a filter ──────→ remove  (drop mention, requery)
  │               ├─ Replacing a filter ─────→ replace (drop old, run pipeline on new term)
  │               └─ Changing subject ───────→ reset   (clear state, run pipeline fresh)
```

| Route | Handler | LLM pipeline? |
| --- | --- | --- |
| **select** | Set `values` from selected disambiguation `concept_id`(s), clear `disambiguation`, requery | No |
| **add** | Run extract → resolve → merge with previous mentions | Yes |
| **remove** | Drop matching mention(s) from `previousQuery`, requery | No |
| **replace** | Drop old mention, run extract → resolve on new term, merge | Yes |
| **reset** | Discard `previousQuery`, run fresh pipeline on new query | Yes |

State is **not persisted server-side**. It is encoded in the request:

- `previousQuery.mentions[].disambiguation` — non-empty means disambiguation is pending
- `previousQuery` present + `query` present — route mode (router runs)
- `previousQuery` present + `query` empty — requery mode (no router, no LLM)
- `query` present + no `previousQuery` — fresh mode (no router, full pipeline)

## Routing Logic

### When is an LLM needed for routing?

| Previous state          | Signal        | Router needed?                                             |
| ----------------------- | ------------- | ---------------------------------------------------------- |
| IDLE (no previousQuery) | —             | No. Always fresh extraction.                               |
| Any state               | query empty   | No. Always requery (chip mutation).                        |
| **DISAMBIGUATING**      | query present | **Yes.** Classify disambiguation response.                 |
| **RESOLVED**            | query present | **Yes.** Could be add, remove, replace, or subject change. |

**An LLM router is needed whenever there is both a `query` and a `previousQuery`.** The router determines whether the user is refining, answering disambiguation, or changing subject entirely.

### Router Classification

The router classifies every follow-up message (has both `query` and `previousQuery`):

```python
class DisambiguationSelect(BaseModel):
    """User selected one or more of the offered disambiguation options."""
    kind: Literal["select"]
    selected_ids: list[str]   # concept_ids from disambiguation options

class MentionReplace(BaseModel):
    """User wants to replace an existing mention with a different term."""
    kind: Literal["replace"]
    original_text: str        # which mention to replace (matches original_text)
    new_text: str             # the replacement term to extract & resolve

class MentionRemove(BaseModel):
    """User wants to drop one or more mentions entirely."""
    kind: Literal["remove"]
    original_texts: list[str] # which mentions to remove (matches original_text)

class MentionAdd(BaseModel):
    """User is adding new criteria to the existing query."""
    kind: Literal["add"]

class SubjectChange(BaseModel):
    """User is starting a completely new query."""
    kind: Literal["reset"]
    new_query: str
```

Note: `DisambiguationSelect` only applies when disambiguation is pending.
`MentionReplace` and `MentionRemove` apply to any mention — disambiguation
or resolved. `MentionAdd` falls through to the existing extract → resolve
pipeline. `SubjectChange` clears state and starts fresh.

The router agent receives:

- Active filters with their resolved values (and disambiguation options if pending)
- The user's message text

Output: one of the above types.

### Processing Each Route

**`select`**: Update the disambiguation mention in `previousQuery`:

- Set `values` to the selected `concept_ids`
- Clear `disambiguation`
- Re-run requery (no LLM pipeline needed)

**`replace`**: Find the mention matching `original_text` in `previousQuery`, remove it, then run the normal extract → resolve pipeline with `new_text` as the query and the modified `previousQuery` for merging.

**`remove`**: Remove the matching mentions from `previousQuery`, re-run requery. This is the chat-based equivalent of clicking the X on a chip.

**`add`**: Fall through to existing refine mode (extract new mentions from the user's message, resolve, merge with previous).

**`reset`**: Discard `previousQuery` entirely, run fresh pipeline on `new_query`.

## Pipeline Changes

### Current flow

```
Request → mode detection (fresh/route/requery) → pipeline → response
```

### Proposed flow

```
Request → mode detection
  │
  ├─ fresh → pipeline (unchanged)
  ├─ requery → requery (unchanged)
  └─ route → router agent (has query + previousQuery)
       │
       ├─ select → update mention values from disambiguation, requery
       ├─ replace → remove old mention, pipeline with new text
       ├─ remove → remove mention(s), requery
       ├─ add → pipeline refine (existing extract → resolve → merge)
       └─ reset → pipeline fresh (ignore previousQuery)
```

### Mode Detection Update

```python
has_query = bool(request.query and request.query.strip())
has_previous = request.previous_query is not None

if not has_query and not has_previous:
    mode = "empty"          # 422 error
elif not has_query:
    mode = "requery"        # re-run DB query with mutated previousQuery (e.g. chip removal)
elif has_previous:
    mode = "route"          # LLM router classifies: disambiguate / refine / reset
else:
    mode = "fresh"          # new query, no prior state
```

## Router Agent Design

**Model**: `anthropic:claude-haiku-4-5-20251001` (same as extract/resolve)

**Input**: Structured prompt with conversation context:

```
You are classifying a user's follow-up message in a search conversation.

Active filters:
  - focus: "diabetes" → [Diabetes Mellitus] (include)
  - measurement: "glucose" → [] (DISAMBIGUATION PENDING)
    Options:
      1. phenx:fasting_plasma_glucose_blood_draw — Blood glucose measurement
      2. topmed:nutrient_intake — Dietary glucose intake

User's message: "{user_input}"

Classify this message.
```

When no disambiguation is pending, the prompt omits the options section and the router chooses between `add`, `remove`, `replace`, and `reset`.

**Output**: Discriminated union of the five types above.

**Caching**: Not cached — disambiguation responses are session-specific.

**Cost**: ~200 input tokens, ~20 output tokens per call. Negligible.

## API Contract

No changes to `SearchRequest` or `SearchResponse` schemas. The `disambiguation` field on mentions already flows through the response. The router is an internal pipeline detail.

## Eval Plan

### Router eval cases

| Case                | Input                               | Previous disambiguation           | Expected                                          |
| ------------------- | ----------------------------------- | --------------------------------- | ------------------------------------------------- |
| select-first        | "blood glucose"                     | glucose: [blood glucose, dietary] | select: [phenx:fasting_plasma_glucose_blood_draw] |
| select-multiple     | "both blood glucose and dietary"    | glucose: [blood glucose, dietary] | select: [phenx:..., topmed:...]                   |
| replace             | "actually I meant meat consumption" | glucose: [blood glucose, dietary] | replace: "meat consumption"                       |
| reject              | "forget about glucose"              | glucose: [blood glucose, dietary] | remove: ["glucose"]                               |
| add-with-disambig   | "also on AnVIL"                     | glucose: [blood glucose, dietary] | add                                               |
| reset-with-disambig | "show me COPD studies instead"      | glucose: [blood glucose, dietary] | reset: "show me COPD studies instead"             |
| shorthand-1         | "the first one"                     | glucose: [blood glucose, dietary] | select: [phenx:fasting_plasma_glucose_blood_draw] |
| shorthand-2         | "2"                                 | glucose: [blood glucose, dietary] | select: [topmed:nutrient_intake]                  |
| neither             | "neither"                           | glucose: [blood glucose, dietary] | remove: ["glucose"]                               |
| add-no-disambig     | "also on AnVIL"                     | (no disambiguation)               | add                                               |
| remove-via-chat     | "remove the diabetes filter"        | (no disambiguation)               | remove: ["diabetes"]                              |
| replace-via-chat    | "change diabetes to asthma"         | (no disambiguation)               | replace: original="diabetes", new="asthma"        |
| reset-no-disambig   | "show me COPD studies"              | (no disambiguation)               | reset: "show me COPD studies"                     |
| add-sex-filter      | "only in females"                   | (no disambiguation)               | add                                               |
| reset-unrelated     | "what about sleep data?"            | (no disambiguation)               | reset: "what about sleep data?"                   |

### End-to-end pipeline eval

Multi-turn case: fresh query with ambiguous term → disambiguation → user selects → verify final response has correct filter chip + study results.

## Out of Scope

- Clickable disambiguation chips in the UI (separate ticket, requires findable-ui changes)
- Multi-mention disambiguation in a single turn (handle one at a time for now)
- Disambiguation for non-measurement facets (consent, focus — future work)
- Server-side session state (client round-trips `previousQuery` as today)

## Implementation Order

1. Router agent + eval cases (backend only, testable in isolation)
2. Integrate router into pipeline mode detection
3. Pipeline handlers for each route type (select, replace, remove, add, reset)
4. End-to-end pipeline eval
5. Manual testing with frontend
