# Design: Single-Agent Conversation Loop (#362)

> Status: **spike / proposed**. Additive only — does not change the live `/search` pipeline.
> Builds on the `SessionStore` seam from #360, the Option A/B analysis in
> `PRD-conversation-routing.md` (branch `noopdog/327/conversation-router-spike`), and lessons
> from the sibling **BRC Analytics** assistant (`/Users/dave/projects/brc-analytics`).

## 1. Context

### Current architecture (verified against code, June 2026)

`POST /search` runs a four-agent Haiku state machine, fully **stateless** — the client
round-trips the `previous_query` (a `QueryModel`) on every turn.

```
fresh:   query ─→ Extract ─→ (Resolve ∥ Structure) ─→ Merge ─→ QueryModel
route:   query + previous_query ─→ Router ─→ {select|refine|remove|replace|reset} ─→ QueryModel
requery: previous_query only ─→ skip LLM, re-run lookup
QueryModel ─→ constraint expansion ─→ DuckDB lookup ─→ response building ─→ SearchResponse
```

- **Extract** (`extract_agent.py`, no tools) → `RawMention[]` + intent.
- **Resolve** (`resolve_agent.py`, **10** tools, `ConceptIndex` deps) → per-mention `ResolveResult`
  (values or disambiguation). Runs in parallel per mention via `asyncio.gather`.
- **Structure** (`structure_agent.py`, no tools) → `exclude` flags. Runs parallel with Resolve.
- **Router** (`router_agent.py`) → one of `RouteSelect | RouteRefine | RouteRemove | RouteReplace
| RouteReset`, dispatched by `_handle_route` in `api.py`.

The **Router is the fragile part** (#327): we keep prose-encoding conversational intent rules —
fighting the LLM's strength.

### How results flow today (verified)

The **backend executes the query and returns the rows**; the frontend is a thin renderer.

- `api.py` runs `store.query_studies` / `query_variables` and returns the actual rows in
  `SearchResponse.studies` / `.variables`.
- The frontend (`ResearchView/.../QueryResults/utils.ts`) renders `response.studies` **directly** —
  it does **not** re-run the structured query client-side. `query_structure` is returned but unused.
- `response.query` is round-tripped as `previousQuery` on the next turn and for filter-removal.
- **No LLM is downstream of the QueryModel today** — lookup + the summary message
  (`build_message` / `diagnose_empty_results`) are deterministic.

### Doc drift found while writing this (fix separately)

`docs/backend-request-flow.md` / `RESOLVE_PROMPT.md` have drifted from code:

| Doc says                              | Code says                                                                                                                                                           |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| intent `"auto"`                       | `"ambiguous"` (`Intent = Literal["ambiguous","study","variable"]`, default `"study"`)                                                                               |
| `RouteAdd`                            | `RouteRefine` (`kind="refine"`)                                                                                                                                     |
| Resolve has "11 tools"                | **10** registered                                                                                                                                                   |
| all resolve tools wrap `ConceptIndex` | `compute_consent_eligibility` is built in the agent (uses `consent_logic` + `index.list_facet_values`); `list_variables_for_concept` is registered but undocumented |

## 2. Goal & approach

Replace the Extract→Resolve→Structure→Router state machine with a **single conversation-aware
agentic loop** (one pydantic-ai `Agent`, the framework NCPI already uses) that:

1. Does routing **implicitly** — the intent _is_ the tool call; no classifier.
2. Builds the internal `QueryModel` incrementally — fills small facets directly, makes tool calls
   to ground complex ones (disease, measurement, consent).
3. Handles multi-turn naturally from conversation history.
4. **Backs off agentically** on empty results (count → relax → re-count) instead of the
   deterministic `diagnose_empty_results`.

### Why agentic (lessons from BRC Analytics)

BRC is a production pydantic-ai agent whose **emergent** behavior comes _from_ the loop: asked
"what bacteria do we have?", it composed `filter(domain=Bacteria) + operation=facets +
facet_by=[phylum]` on its own — nobody coded that path. The lesson: **a small set of orthogonal,
composable tools beats many narrow ones.** BRC has ~8 tools; the catalog core is essentially one
query IR with `count | list | facets` modes plus a couple of lookups, and zero hardcoded
back-off logic. We adopt that shape.

This is **Option A** (consolidation), but the proven **resolve agent is kept as a tool**, so its
`eval_resolve.py` safety net stays valid (the Option B insight).

## 3. Non-breaking spike strategy

Purely additive — the live `/search` pipeline and its four agents are untouched.

| Piece        | Approach                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------------- |
| Module       | New `conversation_agent.py` — one pydantic-ai `Agent`.                                                      |
| Endpoint     | New `POST /search/agent` on the same `app`. Live `/search` unchanged.                                       |
| Internal rep | Same `QueryModel`, built incrementally.                                                                     |
| Grounding    | `resolve_concept` wraps the **existing resolve agent** (no rewrite; evals stay valid).                      |
| Lookup       | Reuse `mention_constraints` → `store.query_studies` / `query_variables` verbatim.                           |
| Response     | Reuse `response_summary` builders; **same `SearchResponse` shape** so the frontend renderer barely changes. |
| History      | Reuse `SessionStore` (#360).                                                                                |
| Removal      | Delete one module + one route to back out. Zero blast radius.                                               |

## 4. The loop & data flow

```
POST /search/agent { sessionId, query }
  │
  ├─ load session (history + current QueryModel) from SessionStore
  ├─ append user message (fenced as untrusted input)
  │
  ├─ pydantic-ai agent.run(message, history) — tool loop:
  │     ├─ small facets → update_query(...)            (direct enum mapping)
  │     ├─ complex terms → resolve_concept(facet, text) (existing resolve agent)
  │     │                 → update_query(...)            (validated commit)
  │     ├─ explore / back off → query_catalog(count|facets)   (stateless)
  │     └─ terminal: prose reply to the user
  │
  ├─ execute committed QueryModel deterministically → full rows  (reuse existing lookup)
  ├─ persist history + QueryModel to SessionStore
  └─ SearchResponse { message, query, studies/variables, ... }
```

### The model sees summaries; the UI gets rows

This is the key separation (and answers "do results enter the prompt?" — **no**):

| Audience      | Sees                                                                                                                                                                    |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **The model** | counts + facet breakdowns + a small sample (~10 rows) from tool returns. Enough to reason, summarize, and decide back-off. **Never** the full result set.               |
| **The UI**    | the full rows — produced by **deterministically executing the committed `QueryModel`** (reuse `store.query_studies` + existing builders), attached to `SearchResponse`. |

NCPI result sets are large (variables capped at 500); dumping them into context every turn would
be costly and pointless. The model reasons over "how many, of what shape"; execution stays
deterministic.

## 5. Tool set (~4 composable tools)

| Tool                                                                   | Role                                                                                                                                        | Backing                                                         | Mutates state?                 |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------ |
| `query_catalog(constraints, operation: count\|list\|facets, facet_by)` | the power-tool — execute / count / group-by; enables emergent "what diseases/measurements do we have" **and** agentic empty-result back-off | `store.query_studies/query_variables` + a thin facet/count mode | **No** (stateless exploration) |
| `update_query(add?, remove?, replace?, exclude?)`                      | commit changes to the persistent `QueryModel`; returns the resulting `{ total, facets, sample }`                                            | applies to session `QueryModel`; runs lookup for the summary    | **Yes** (validated)            |
| `resolve_concept(facet, text)`                                         | ground complex terms (focus/measurement/consent) → concept IDs or disambiguation                                                            | wraps the **existing resolve agent** (keeps `eval_resolve`)     | No                             |
| `search_concepts(query, facet)`                                        | lighter keyword/embedding browse when the agent wants candidates                                                                            | existing `index` methods                                        | No                             |

Small facets (platform, dataType, studyDesign, sex, raceEthnicity, computedAncestry) are mapped
**directly** by the model into `update_query` — no tool needed (they're enum picks).
`exclude`/OR logic is set as part of `update_query` — this absorbs the Structure agent.
Disambiguation is the agent asking in prose (BRC-style grounded suggestion chips are the analogue);
the next user turn is just answered in-conversation — this absorbs the Router.

### Why state mutation is a tool call, not a parsed line

BRC commits state by emitting a `SCHEMA_UPDATE: {json}` line that code regex-parses. We use a
**validated `update_query` tool call** instead. Rationale:

- **Validation + self-repair**: pydantic-ai validates the args against the `QueryModel` schema
  (enums, concept IDs, flags) and feeds `ValidationError`s back to the model to retry. Parsing a
  line has no repair path.
- **No silent state loss**: BRC's parser tolerates bold/markdown/case and **silently drops
  malformed JSON into the reply** — the prose can say "added diabetes" while state didn't change.
  For our enum-typed `QueryModel` that's a trust-destroying, hard-to-debug bug.
- **Clean channel separation**: machine state never shares a text blob with the user message.

**Cost**: ~1 extra model generation per turn (a tool call is non-terminal, so the prose reply
follows it). Mitigated by (a) Anthropic prompt caching on tool defs + instructions, and (b)
`update_query` returning the result summary — so the round-trip also fetches what the model needs
to reply (it's productive, not pure overhead). Worth it for typed-state correctness.

### Model selection — how we avoid the 60×

The ~60× figure is the worst case: a single all-Sonnet agent doing the token-heavy grounding too.
We don't pay it. Only the orchestrator is a new LLM; grounding stays on the existing Haiku agent.

| Call in a turn                                       | Model                                         | New?     |
| ---------------------------------------------------- | --------------------------------------------- | -------- |
| Orchestrator (conversation loop)                     | **Sonnet** (env-configurable)                 | new      |
| `resolve_concept`                                    | **Haiku** (existing resolve agent, untouched) | existing |
| `query_catalog` / `update_query` / `search_concepts` | none — DuckDB / code / index lookup           | —        |

Each component is a separate pydantic-ai `Agent` with its own `model` string — exactly how the
four Haiku agents already work today (`_get_agent(model)`). "Registering multiple models" is just
passing a different model per agent.

Cost levers, in order of payoff:

1. **Orchestrator model = env var, default Sonnet; eval-gate a Haiku orchestrator.** If Haiku
   passes the multi-turn/composition evals, cost drops to near-current. (Start Sonnet, test down —
   the emergent composition is where Sonnet earns its keep.)
2. **Tiered per-query routing** (Haiku for simple single-facet queries, Sonnet for
   complex/multi-turn) — possible later, but adds a routing decision; defer unless cost bites.

This is the hybrid: Sonnet orchestrates (~one call/turn, prompt-cached), Haiku does the heavy
grounding → ~10× current cost, not ~60×.

## 6. System prompt (checklist style, sketch)

```
You are a search assistant for the NCPI Dataset Catalog. Resolve researchers'
natural language into catalog concepts using your tools — never invent values.
Only ever present concepts/studies a tool actually returned. (grounding guard)

Before acting, consider:
- Intent: studies or variables? (study | variable | ambiguous)
- Starting fresh, refining, or answering a pending disambiguation?
- Each term: which facet? small facet (map directly) or large facet (resolve_concept)?
- Exclusions ("but not", "excluding")?
- If results are empty, relax: query_catalog(count) without each filter to find the culprit,
  then tell the user which filter is too restrictive.

Small facets (map directly): platform, dataType, studyDesign, sex, raceEthnicity,
computedAncestry — [enum lists].
Large facets (resolve_concept): focus, measurement, consentCode.
ISA closure: a parent concept includes descendants — prefer the most specific ancestor
that covers the user's intent.
Commit selections with update_query. When ready, the committed query drives the results.
```

## 7. Session / history

- Request carries `sessionId`; backend owns state via `SessionStore` (#360).
- **History shape**: follow BRC — persist the **full pydantic-ai message history** (tool calls +
  results), **truncated** to ~N messages keeping the first (intent), with **Anthropic prompt
  caching** on. This gives full continuity ("go back to before the diabetes filter") and avoids
  re-running tools. `SessionState` (#360) carries this payload — it's already a pydantic model,
  so evolving it is free. (Supersedes the earlier "lean text-only" sketch.)
- Persist the current `QueryModel` alongside, for the response's filter chips and as the resume
  point.

## 8. Request / response

```python
class SearchAgentRequest(BaseModel):   # api_models.py, camelCase aliases
    session_id: str
    query: str = Field(default="", max_length=1000)
```

Reuse `SearchResponse` (message, query, query_structure, studies, variables, timing, totals) so
the existing frontend renderer works unchanged; `message` becomes the agent's prose reply.
Keep the 60s `asyncio.wait_for` timeout and the per-IP rate limiter, matching `/search`.

## 9. Eval plan

- `resolve_concept` wraps the unchanged resolve agent → **`eval_resolve.py` still guards
  grounding**. Only the new orchestration needs new evals.
- Port the **router eval** cases (13) into multi-turn conversation cases against `/search/agent`.
- Run existing **pipeline eval** cases end-to-end; compare study counts / facet constraints to
  the current pipeline (regression guard).
- New multi-turn cases: disambiguation answer, refine, remove, replace, reset, "go back",
  empty-result back-off.
- Promotion gate: match or beat current router + pipeline results before any UI wiring.

## 10. Risks & open questions

- **Cost / latency**: Sonnet orchestrator + Haiku resolver, multi-round loop. ~10× current
  cost; +2-3s/turn. Acceptable at our scale; prompt caching helps. Revisit if it bites.
- **Resolve quality**: preserved by keeping the resolve agent as `resolve_concept` (its 200-line
  prompt + 10 internal tools are unchanged).
- **Consent logic** is the most intricate path — `resolve_concept` must route consent to the
  existing `compute_consent_eligibility` impl; lean on `eval_resolve.py` consent cases.
- **Back-off depth**: agentic relaxation could fan out tool calls — cap loop iterations / tool
  budget per turn.
- **`update_query` granularity**: confirm add/remove/replace/exclude covers all mutations
  (incl. selecting a disambiguation option) without a separate tool.

## 11. Out of scope (future tickets)

- DynamoDB `SessionStore` adapter.
- Frontend `session_id` plumbing (replace `previousQuery` round-trip).
- Promoting `/search/agent` to the default `/search`.
- Fixing the doc drift in §1 (separate housekeeping PR).
