# Backend Request Flow

How a `/search` request is processed, step by step.

The backend runs a **single conversation-aware agent** (Sonnet) that builds a
`QueryModel` incrementally by calling tools. It replaced the
Extract → Resolve → Structure → Router state machine in #412. Conversation state
lives on the **server**: the client sends its message text plus a `sessionId`,
and never round-trips a `QueryModel` (it did until #411).

---

## 1. HTTP Entry — Front Controller

**File**: [api.py](../backend/concept_search/api.py)

`POST /search` receives a `SearchRequest`:

- `query` — natural language text
- `sessionId` — client-generated, created once per visit and sent on every request

Rate limiting is checked per client IP. There are no modes: every request is one
turn of the same conversation. Whether it starts a fresh search, refines the
current one, or answers a question the agent asked is decided by the agent
itself, from the conversation history.

Two other endpoints:

| Endpoint              | LLM? | Purpose                                                              |
| --------------------- | ---- | -------------------------------------------------------------------- |
| `POST /search`        | yes  | One conversational turn                                              |
| `POST /search/filter` | no   | Deterministic chip removal — drop one facet value, re-run the lookup |
| `GET /health`         | no   | `status`, `gitSha`, `indexStats`, `resolveCache`                     |

---

## 2. Load Session State

**File**: [session_store.py](../backend/concept_search/session_store.py)

`get_session_store()` returns an `InMemorySessionStore` or a
`DynamoDBSessionStore`, selected by `SESSION_STORE_BACKEND` — **`"memory"` by
default**, so a local run needs no AWS. Deployed environments set `"dynamodb"`
(and `SESSION_TABLE_NAME`) from outside this repo. Both honour
`SESSION_TTL_SECONDS`, defaulting to 86400s (24h).

A `SessionState` holds:

- `query` — the committed `QueryModel`
- `pending` — disambiguation choices offered but not yet answered
- `agent_message_history` — serialized pydantic-ai messages (tool calls **and**
  their results), so the agent has full continuity across turns
- `messages` — the user/assistant text transcript

A store read failure is **retryable, not a 500**: the handler logs and returns a
friendly message.

---

## 3. Run One Conversational Turn

**File**: [conversation_agent.py](../backend/concept_search/conversation_agent.py)
**Prompt**: [CONVERSATION_PROMPT.md](../backend/concept_search/CONVERSATION_PROMPT.md)

`run_conversation(message, deps, message_history)` builds the turn's input as:

```
[Current search: …]              ← trusted state preamble, outside the fence
[Pending choice for "X": 1) … ]

<user_input>
…the user's message…             ← untrusted, fenced (#364)
</user_input>
```

The close tag is defanged with a zero-width space so a user cannot break out of
the fence. The agent is bounded by `UsageLimits(request_limit=10)` per turn, and
the whole turn by a 60s timeout and a concurrency semaphore of 5.

The agent has exactly three tools:

### 3.1 `resolve_concepts(mentions)`

Grounds large-facet terms (`focus`, `measurement`, `consentCode`) against the
concept index. Batched — all of a query's terms resolve in parallel. Delegates to
the **resolve agent** (Haiku), unchanged since the pipeline days.

**Prompt**: [RESOLVE_PROMPT.md](../backend/concept_search/RESOLVE_PROMPT.md)

Returns per term either canonical `values` or `disambiguation` options. Ambiguous
terms become `pending` choices; the agent asks the user rather than guessing.
Results are LRU-cached (`resolve_cache`, surfaced on `/health`).

Small facets (`platform`, `dataType`, `studyDesign`, `sex`, `raceEthnicity`,
`computedAncestry`) need no tool — the prompt lists their values and the agent
maps the user's wording directly.

### 3.2 `update_query(add, remove, intent, reset)`

The **source of truth** for what the user sees. Commits selections and returns a
summary: counts, active filters, and a 5-study sample.

Boolean semantics — the shape the agent commits _is_ the logic:

> Values within one mention are **OR**-ed. Separate mentions are **AND**-ed.
> Excluded mentions subtract.

So `"diabetes or asthma"` must be **one** focus mention holding both values, and
`"WGS and WXS"` must be **two** dataType mentions.

Two things the tool decides, not the agent:

- **Empty result** → the summary carries a `relaxation` map, giving the result
  count if each filter alone were dropped, so the agent can say which filter is
  too restrictive without extra exploration.
- **Impossible query** → committing two terms that no single study can hold on a
  facet each study has only one of (`focus`, `studyDesign`) returns
  `{"error": "unsatisfiable_and", …}`. Nothing is committed **and the search is
  cleared**, so the user sees no results rather than the previous search's rows.
  The payload carries each term's count, `if_or`, and `cleared_filters`. See #363.

Satisfiability is decided by asking the index, not by reasoning over the ISA
table: a study is indexed under its focus value's whole ancestor closure, so
`cancer ∧ lung cancer` still intersects (the lung-cancer studies — redundant, not
impossible) while `diabetes ∧ asthma` cannot.

### 3.3 `query_catalog(operation, facet_by, drop_facets)`

Explores **without** changing the committed query: `count`, group-by, or `list` a
sample. Used to answer "what's in the catalog" questions.

---

## 4. Constraint Expansion

**File**: [mention_constraints.py](../backend/concept_search/mention_constraints.py)

`split_mentions()` turns resolved mentions into include/exclude constraint
tuples. Each tuple is one AND constraint; values within it are OR-ed.

`consentCode` tags (`no-*`, `explicit:*`) expand here into actual consent codes,
using a scope inferred from sibling focus mentions (general / health / disease).
An expansion that yields nothing becomes a `__NO_MATCH__` sentinel, so the
constraint stays active and returns zero rather than silently broadening.

---

## 5. Deterministic Lookup

**File**: [search_execution.py](../backend/concept_search/search_execution.py)

`execute_query_model(query_model, index)` — no LLM.

- **study** intent → `query_studies(include, exclude)` against DuckDB
- **variable** intent → apply study-level constraints first, then
  `query_variables()` over the concept **ISA closure**, so a parent concept
  matches variables tagged with any descendant
- **ambiguous** intent → no lookup at all; the caller asks the user what they meant

---

## 6. Response Building

**File**: [response_summary.py](../backend/concept_search/response_summary.py)

- `query_structure` — one clause per mention, with concept IDs resolved to
  **display labels** (`ncpi:cancer_…_treatment_response` → "Treatment Response
  Assessment")
- `message` — the agent's own reply, rendered as markdown by the frontend
- `timing` — `pipeline_ms` (the agent turn) and `lookup_ms`

---

## 7. Persist and Respond

The committed `QueryModel`, `pending` choices, and the agent's message history
are written back to the session store. Both histories are **bounded on write**
(`_MAX_AGENT_HISTORY = 40`, `_MAX_SESSION_MESSAGES = 50`) so stored state cannot
grow past DynamoDB's per-item size cap. A coherent truncation policy is tracked
in #380.

A persist failure does **not** 500 — the response is already built.

---

## Data Flow Diagram

```
POST /search(query, sessionId)
  │
  ├─ rate limit (per IP)
  │
  ├─ load SessionState  (session store, keyed by sessionId)
  │     query_state · pending · agent_message_history
  │
  ▼
run_conversation()  ── one Sonnet turn, ≤10 requests, 60s timeout
  │
  │   state preamble  +  <user_input>…</user_input>   (fenced, untrusted)
  │
  ├─ resolve_concepts()  → values | disambiguation → pending
  ├─ query_catalog()     → explore, no commit
  └─ update_query()      → COMMIT
        │
        ├─ unsatisfiable AND? → clear search, return counts + cleared_filters
        ├─ empty result?      → attach relaxation map
        └─ otherwise          → counts + active filters + 5-study sample
  │
  ▼
QueryModel (committed)
  │
  ├─ split_mentions()        include/exclude tuples; consent tags expanded
  │
  ├─ execute_query_model()   DuckDB, no LLM
  │    ├─ study    → query_studies()
  │    ├─ variable → query_variables() over ISA closure
  │    └─ ambiguous→ no lookup
  │
  ├─ build_query_structure() clauses + display labels
  │
  ├─ persist SessionState    (bounded on write)
  │
  └─ SearchResponse(message = the agent's reply)
```
