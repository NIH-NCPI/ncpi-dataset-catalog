# PRD: Conversation-Aware Routing (#327)

## Context

The current search pipeline uses a multi-agent state machine: Extract → Resolve → Structure → Router. Each step is a separate Haiku call with a specialized prompt. The Router classifies follow-up messages (select, refine, remove, replace, reset) and advances the state machine.

During #301 (cross-facet disambiguation), we found the Router is the most fragile part of the pipeline. Matching paraphrased disambiguation responses required prompt tuning — "dietary intake" wasn't matched to "Glucose Intake from Diet" until we added instructions to combine the original mention with the user's response for semantic matching. The Router is essentially doing conversational intent classification, which is exactly what a capable model with conversation context does naturally.

Right now we are **programming a state machine in English**. The Router prompt says "if disambiguation is pending and the user gives a short answer, classify as `select`." The Extract prompt says "if it mentions a platform, put it in the platform facet." We are writing `if/then/else` branches as prose — and every edge case requires another rule.

This is **fighting the LLM's strength**. We are using the model as a regex engine when it is actually a reasoning engine.

## Current Architecture

```
User query → Extract (Haiku) → Resolve (Haiku, parallel per mention) → Structure (Haiku) → Merge → Response
Follow-up  → Router (Haiku) → classifies action → dispatches to appropriate handler
```

### Current Agents, Roles & Tools

| Agent         | Role                                                                       | Tools                                                                                                                                                                                                                                                                                                                                         | Prompt Size |
| ------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| **Extract**   | Parse NL query → facet/text mentions, detect intent                        | **None** — pure LLM parse against enum lists in prompt                                                                                                                                                                                                                                                                                        | ~148 lines  |
| **Resolve**   | Ground mentions against concept index → canonical values or disambiguation | **11 tools** — `search_concepts`, `search_concepts_by_embedding`, `get_focus_category_terms`, `get_concept_children`, `get_measurement_category_concepts`, `get_consent_code_categories`, `get_disease_specific_codes`, `get_consent_codes_for_base`, `compute_consent_eligibility`, `list_variables_for_concept`, plus focus facet embedding | ~102 lines  |
| **Structure** | Determine boolean logic (exclude flags) between mentions                   | **None** — pure LLM                                                                                                                                                                                                                                                                                                                           | ~57 lines   |
| **Router**    | Classify follow-ups: select / refine / remove / replace / reset            | **None** — pure LLM classification                                                                                                                                                                                                                                                                                                            | ~29 lines   |

### Strengths

- **Cost**: Haiku is ~60x cheaper than Sonnet per token
- **Latency**: Haiku ~1s per call, parallel calls can be faster than one sequential Sonnet call
- **Testability**: Each agent has a narrow job, independently eval'd
- **Guardrails**: State machine prevents impossible transitions

### Weaknesses

- **Router brittleness**: Prompt engineering to handle paraphrases, disambiguation responses, refine vs reset distinction
- **Complexity**: Debugging interactions between agents (extract assigns facet → resolve trusts it → router must match disambiguation responses back)
- **Against LLM strengths**: Forcing conversational interaction into a state machine, then fighting to make transitions feel natural

## What We Should Be Doing Instead

### 1. Tool-driven routing (let the model act, not classify)

Instead of the Router outputting a label like `RouteSelect` that Python code then dispatches, give the model **tools that perform the actions directly**.

The model sees the conversation history, sees the pending disambiguation, sees the user said "the measurement one" — and **calls the right tool**. No classification step needed. The intent _is_ the tool call.

### 2. Checklist prompts (reasoning framework, not rules)

A checklist prompt gives the model a **reasoning framework** rather than rules. Instead of:

> "If the user's response is short and disambiguation is pending, classify as select. If it contains 'instead' or 'actually', classify as replace..."

Write:

> "Before responding, consider:
>
> - Is there a pending disambiguation the user might be answering?
> - Is the user adding to their search, narrowing it, or starting over?
> - Does the user's message reference something from the conversation history?
>
> Then use the appropriate tool."

The checklist prompts the model to **think through the situation** rather than pattern-match against rules. The model already knows how conversations work — the checklist makes sure it doesn't skip steps.

### 3. General-purpose prompt + specific tool descriptions

Move domain knowledge from the prompt into the tool descriptions. Instead of a 200-line Resolve prompt explaining when to use embedding search vs. keyword search, make the tool descriptions self-documenting:

```python
@agent.tool
def search_concepts_by_embedding(query: str, facet: str, top_k: int = 10):
    """Semantic search for concepts. Best for focus and measurement facets
    where the user's phrasing may not match the canonical term exactly.
    Returns concepts ranked by semantic similarity.

    For focus facet: returning a parent concept automatically includes
    all descendant studies via ISA closure.
    """
```

The model reads the tool description and **decides when to use it** based on the situation. No rule needed saying "use embedding search for large facets" — the tool description explains what it's good for.

## Proposed Options

### Option A: Fully Consolidated (Single Sonnet)

One model, one conversation thread, one system prompt. It receives the user's message, reasons about what to do, and calls tools to build/modify the query.

#### Tool Set

| Tool                                                 | Replaces               | Description                                      |
| ---------------------------------------------------- | ---------------------- | ------------------------------------------------ |
| `search_concepts_by_embedding(query, facet, top_k)`  | Resolve tool           | Semantic search against concept index            |
| `search_concepts(query, facet, limit)`               | Resolve tool           | Keyword substring match                          |
| `get_concept_children(concept_id)`                   | Resolve tool           | Drill into parent concept                        |
| `get_consent_code_categories()`                      | Resolve tool           | List base codes + modifiers                      |
| `compute_consent_eligibility(purpose, disease, ...)` | Resolve tool           | Eligible codes for use case                      |
| `search_studies(query_model)`                        | API dispatch           | Execute the structured query against the catalog |
| `present_disambiguation(options)`                    | Resolve output         | Show user choices when meaning is ambiguous      |
| `get_current_query()`                                | Router context         | Inspect the active query state                   |
| `update_query(add, remove, replace)`                 | Router+Structure+Merge | Modify the active query in one call              |

**Dropped tools** (absorbed into the model's reasoning):

- `get_focus_category_terms`, `get_measurement_category_concepts` — rarely used fallbacks, the model can just retry embedding search with rephrased terms
- `list_variables_for_concept` — can be a tool if needed, but mostly a debug aid
- `get_disease_specific_codes`, `get_consent_codes_for_base` — can be folded into `get_consent_code_categories` or handled by the model knowing the code patterns

**What disappears entirely:**

- Extract agent — Sonnet parses the query as part of its reasoning before calling tools
- Structure agent — Sonnet interprets "but not X" naturally and sets exclude flags via `update_query`
- Router agent — there is no routing; the model just continues the conversation
- `_handle_route` dispatch code (~110 lines of Python)
- `_merge`, `_merge_with_previous` (~70 lines) — model manages query state via tools

#### System Prompt (~50-80 lines)

```markdown
You are a search assistant for the NCPI Dataset Catalog. Researchers
ask you to find biomedical studies and variables.

## Your job

Help users build structured queries by resolving their natural language
into catalog concepts. Use your tools to ground every term — never
invent values.

## Checklist (think through before acting)

- What is the user's intent: finding studies or finding variables?
- Are they starting fresh, refining, or answering a disambiguation?
- For each mention: which facet? Is it a small facet (resolve from
  known values) or a large facet (use search tools)?
- Does the query contain exclusions ("but not", "excluding")?

## Small facets (resolve directly, no tool call needed)

Platform: AnVIL, BDC, CRDC, KFDRC, dbGaP
Data Type: WGS, WXS, RNA-Seq, ...
[etc — same enum lists from current Extract prompt]

## Large facets (use tools)

- focus/disease: search_concepts_by_embedding with facet="focus"
- measurement: search_concepts_by_embedding with facet="measurement"
- consentCode: explicit codes or constraint tags (no-npu, no-irb, ...)

## ISA closure

Focus and measurement facets have hierarchy. Returning a parent
automatically includes descendants. Prefer the most specific ancestor
that covers the user's intent.

## Disambiguation

When results span unrelated domains, use present_disambiguation
to ask the user to choose. Don't guess.
```

No 148-line Extract prompt. No 29-line Router prompt. No multi-turn refinement rules. The model just continues the conversation.

#### Example: How Disambiguation Works Naturally

**Current (4 agents, state machine):**

```
User: "glucose studies"
  → Extract (Haiku): [{facet: [focus, measurement], text: "glucose"}]
  → Resolve (Haiku): disambiguation between focus/measurement
  → Response with options

User: "the measurement one"
  → Router (Haiku): classifies as RouteSelect ← THIS IS THE FRAGILE PART
  → Python dispatch resolves disambiguation
```

**Consolidated (single conversation-aware model with tools):**

```
User: "glucose studies"
  → Model calls search_concepts_by_embedding("glucose", facet="focus")
  → Model calls search_concepts_by_embedding("glucose", facet="measurement")
  → Model sees ambiguity, calls present_disambiguation(options=[...])

User: "the measurement one"
  → Model (same conversation) sees its own previous disambiguation
  → Model calls resolve_disambiguation(selected_id="glucose_biomarker")
  → Model calls search_studies(query=...)
```

No router. No classification. The model just **continues the conversation** and uses the right tool. It handles "dietary intake" → "Glucose Intake from Diet" naturally because it has the conversation context.

#### Cost & Latency

| Scenario                   | Current (4x Haiku)                                                | Consolidated (Sonnet)                                       |
| -------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------- |
| Fresh query                | Extract + Resolve(xN parallel) + Structure = 3-5 Haiku calls, ~2s | 1 Sonnet call with 2-4 tool rounds, ~4-8s                   |
| Follow-up                  | Router + maybe Pipeline re-run = 2-4 Haiku calls, ~2s             | 1 Sonnet call continuing conversation, ~3-5s                |
| **Token cost** (fresh)     | ~2K in + ~500 out x 4 calls = 10K tokens @ Haiku ($0.001)         | ~4K in + ~1K out x 2-3 rounds = 15K tokens @ Sonnet ($0.06) |
| **Token cost** (follow-up) | ~1.5K in + ~300 out x 2 calls = 4K tokens @ Haiku ($0.0004)       | Conversation grows; ~8K in + ~500 out ($0.03)               |

~60x more expensive per query. But the absolute cost is still small — $0.06 vs $0.001 per fresh query, or ~$60 vs ~$1 per 1,000 queries.

#### Pros

- **Simplest code.** ~200 lines of Python + one prompt replaces ~1,100 lines of agent code + 4 prompts + pipeline orchestration + merge logic
- **Disambiguation "just works."** The model said "did you mean X or Y?" — it remembers. No matching logic needed
- **No Router brittleness.** "dietary intake" matching "Glucose Intake from Diet" is trivial when the model has its own conversation context
- **New capabilities for free.** "Actually, go back to what I had before the diabetes filter" — conversational memory handles this

#### Cons

- **60x cost increase** — may matter at scale
- **2-3x latency increase** on fresh queries (tool call round trips through Sonnet)
- **Harder to eval independently** — can't unit-test Extract accuracy separately from Resolve accuracy
- **Conversation context grows** — 10-turn conversations could hit 20K+ input tokens per call
- **Resolve quality may drop** — Haiku with 11 specialized tools and a 200-line prompt is very good at concept grounding. Sonnet with a 50-line prompt and 9 tools has less guidance

---

### Option B: Hybrid (Haiku Workers + Sonnet Orchestrator)

Keep Extract and Resolve as cheap, fast, independently testable Haiku agents. Replace Router + Structure + dispatch logic with a Sonnet orchestrator that has conversation context.

#### Architecture

```
Fresh:     Sonnet orchestrator → calls run_search(query) → returns QueryModel
Follow-up: Sonnet orchestrator (with conversation) → decides action → calls tools
```

#### Tool Set for the Sonnet Orchestrator

| Tool                                                | Description                                                                                                                                                                |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run_search(query)`                                 | Run the full Extract → Resolve → Structure pipeline on text. Returns a QueryModel with resolved mentions. **This is a thick tool** — it wraps the existing Haiku pipeline. |
| `resolve_disambiguation(mention_text, selected_id)` | Pick a disambiguation option for a pending mention                                                                                                                         |
| `remove_filter(mention_text)`                       | Drop a mention from the active query                                                                                                                                       |
| `replace_filter(old_text, new_text)`                | Swap one mention for another (runs pipeline on new_text)                                                                                                                   |
| `get_current_filters()`                             | Return the active query state as human-readable text                                                                                                                       |
| `search_studies(query_model)`                       | Execute a QueryModel against the catalog and return results                                                                                                                |

#### What Changes

| Component                             | Status                                                |
| ------------------------------------- | ----------------------------------------------------- |
| Extract agent + prompt                | **Kept as-is** (wrapped inside `run_search`)          |
| Resolve agent + 11 tools + prompt     | **Kept as-is** (wrapped inside `run_search`)          |
| Structure agent + prompt              | **Kept as-is** (wrapped inside `run_search`)          |
| Router agent + prompt                 | **Deleted** — Sonnet orchestrator replaces it         |
| `_handle_route` dispatch (~110 lines) | **Deleted** — tool implementations replace it         |
| `_merge`, `_merge_with_previous`      | **Kept** (inside `run_search` and `replace_filter`)   |
| Pipeline orchestration                | **Kept** — `run_search` is essentially `run_pipeline` |

#### System Prompt for Orchestrator (~30 lines)

```markdown
You are a search assistant for the NCPI Dataset Catalog.

## Checklist

Before responding, consider:

- Is the user starting a new search, refining, or answering a disambiguation?
- If disambiguation is pending, is the user picking an option or changing direction?
- Does the user want to add, remove, or replace a filter?

Then use the appropriate tool. Use run_search for fresh queries and
refinements. Use resolve_disambiguation when the user picks from
offered options. Use remove_filter/replace_filter for modifications.

The search pipeline handles facet extraction, concept resolution,
and boolean logic automatically — you don't need to manage those details.
```

#### Cost & Latency

| Scenario                   | Current (4x Haiku)                       | Hybrid (Sonnet + Haiku workers)                      |
| -------------------------- | ---------------------------------------- | ---------------------------------------------------- |
| Fresh query                | 3-5 Haiku calls, ~2s                     | 1 Sonnet call + 3-5 Haiku calls = ~3-4s              |
| Follow-up (disambiguation) | Router(Haiku) + dispatch, ~1-2s          | 1 Sonnet call (no Haiku needed), ~2-3s               |
| Follow-up (refine)         | Router(Haiku) + pipeline(3-5 Haiku), ~3s | 1 Sonnet call + pipeline(3-5 Haiku), ~4-5s           |
| **Token cost** (fresh)     | ~$0.001                                  | Sonnet overhead ~$0.01 + Haiku ~$0.001 = **~$0.011** |
| **Token cost** (follow-up) | ~$0.0004                                 | Sonnet ~$0.01 + maybe Haiku ~$0.001 = **~$0.011**    |

~10x more expensive (vs 60x for full consolidation). Sonnet only runs once as the orchestrator, Haiku does the heavy lifting.

#### Pros

- **Router brittleness solved** — same benefit as Option A, Sonnet handles conversational intent natively
- **Existing evals still work** — Extract, Resolve, Structure agents unchanged, independently testable
- **10x cost vs 60x** — Sonnet only for orchestration, not for concept grounding
- **Minimal code change** — delete Router agent, wrap pipeline as a tool, add orchestrator
- **Resolve quality preserved** — the 200-line Resolve prompt + 11 specialized tools stay exactly as they are
- **Latency similar to current** for fresh queries (Sonnet overhead is one call, pipeline runs same as before)

#### Cons

- **Still adds Sonnet cost** per query (~$11/1000 queries vs ~$1/1000)
- **Two LLM frameworks in play** — Sonnet orchestrator + Haiku agents, slightly more complex than pure consolidation
- **Fresh queries are slower** — Sonnet → Haiku pipeline is serial, adds ~1-2s
- **Conversation context still grows** on long threads

## Comparison

|                           | Current                                 | A: Full Consolidation         | B: Hybrid                                                         |
| ------------------------- | --------------------------------------- | ----------------------------- | ----------------------------------------------------------------- |
| **Agents**                | 4 (Extract, Resolve, Structure, Router) | 1 (Sonnet)                    | 3 workers (Extract, Resolve, Structure) + 1 orchestrator (Sonnet) |
| **Router brittleness**    | High                                    | Eliminated                    | Eliminated                                                        |
| **Cost per 1K queries**   | ~$1                                     | ~$60                          | ~$11                                                              |
| **Fresh query latency**   | ~2s                                     | ~5-8s                         | ~3-4s                                                             |
| **Follow-up latency**     | ~1-2s                                   | ~3-5s                         | ~2-3s                                                             |
| **Code complexity**       | High (4 prompts + dispatch + merge)     | Low (1 prompt + tools)        | Medium (3 prompts + 1 orchestrator + tools)                       |
| **Eval coverage**         | Each agent unit-tested                  | E2E only                      | Workers unit-tested + E2E                                         |
| **Resolve accuracy**      | High (specialized prompt)               | Risk of regression            | Preserved                                                         |
| **New capability effort** | New rules per edge case                 | Mostly free from conversation | Free for routing, rules for workers                               |

## Recommendation

**Start with Option B (Hybrid).** Rationale:

1. **The problem is the Router, not Extract/Resolve.** Issue #327 says it explicitly — the Router is the fragile part. Extract and Resolve work well. Option B surgically replaces the problem component.

2. **We keep our eval safety net.** The 25 Router eval cases become E2E tests against the Sonnet orchestrator. Extract and Resolve evals stay untouched. With Option A, we would need to rebuild eval coverage from scratch.

3. **Option A is available as a future step.** If we find that Extract+Resolve are also creating friction, we can collapse them into the Sonnet orchestrator later. B → A is incremental. Current → A is a rewrite.

4. **The cost math works.** $11/1K queries is reasonable. $60/1K is also fine at our scale, but why pay it when the workers are doing their job well?

## Spike Plan

1. Delete `router_agent.py` and `ROUTER_PROMPT.md`
2. Add a `ConversationOrchestrator` with 5-6 tools that wrap the existing pipeline
3. Run the 25 router eval cases against it
4. If it matches or beats 25/25, ship it
