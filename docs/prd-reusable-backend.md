# PRD: Reusable Concept Search Backend

**Status**: Draft
**Author**: Dave
**Date**: 2026-03-19

## Problem

The NCPI Dataset Catalog backend (`backend/concept_search/`) implements a
powerful pattern: natural-language queries are decomposed by LLM agents into
structured faceted searches, then executed deterministically against an index.
This pattern is useful beyond NCPI — any catalog of structured records with a
concept hierarchy could use the same pipeline.

However, the current code is tightly coupled to:

1. **NCPI's facet enum** (platform, focus, measurement, consentCode, …)
2. **NCPI's schema** (dbGaP studies, TOPMed/PhenX variables, MeSH disease hierarchy)
3. **DuckDB** as the sole query backend (~8K concepts, ~170K variables)
4. **NCPI-specific resolve tools** (consent code eligibility, MeSH category browser)

The next deployment targets a larger biomedical catalog with **millions of rows**,
**multiple record types** (files, donors, samples, datasets, studies), a **mix
of standard and domain-specific ontologies** (MeSH + CARD/NCBI Taxonomy for
AMR), and eventually **geographic and temporal facets** (disease virulence
evolution, AMR location tracking). It needs OpenSearch (or similar) instead of
DuckDB, and multi-turn conversation from day one.

## Goals

1. Enable standing up a new concept-search site by providing **configuration +
   plugins**, not by forking the repo.
2. Support **DuckDB** (small catalogs, single-node) and **OpenSearch** (large
   catalogs, millions of rows) as query backends.
3. Allow each deployment to define its own **facets, record types, mention
   types, and resolve strategies** without modifying core pipeline code.
4. Share the **agent pipeline, caching, multi-turn routing, and response
   building** across deployments.
5. Keep the NCPI catalog working as-is — it becomes one "site" on the shared
   core.

## Non-Goals

- Building a general-purpose search engine (we stay in the "LLM-decomposed
  faceted search" lane).
- Supporting non-Python deployments.
- Migrating NCPI off DuckDB (it stays on DuckDB unless data volume demands
  otherwise).
- Multi-tenant deployment (sites run as separate services).

---

## Decisions (resolved)

| Question                    | Answer                                                                                                                                         |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| New site's facets vs. NCPI? | Superset — same core types (study, dataset) plus files, donors, samples. Similar facet shape initially, with geo/temporal facets coming later. |
| Multi-turn needed?          | Yes, from day one.                                                                                                                             |
| Deployment model?           | Separate deployments per site. No multi-tenant routing.                                                                                        |
| Embedding models?           | Start with one shared model across sites. Design for per-site or per-facet model swaps later.                                                  |
| Who maintains site code?    | Same team for now. Monorepo is fine.                                                                                                           |
| Search backend?             | OpenSearch likely for the new site. Open to alternatives. DuckDB stays for NCPI.                                                               |
| Ontologies?                 | Mix — shared biomedical (MeSH, SNOMED, HPO) plus domain-specific (CARD, NCBI Taxonomy, antibiotic classes for AMR).                            |
| Record type search UX?      | Unified search with intent detection. One endpoint, LLM picks record type from query. Frontend can traverse links between related records.     |

---

## Current Architecture (reference)

```
User Query
  → Extract Agent    (query → RawMention[] + intent)
  → Resolve Agent    (RawMention → ResolveResult, using tools)
  → Structure Agent  (RawMention[] → exclude flags)
  → Merge            (zip resolved values + flags → ResolvedMention[])
  → Lookup           (ResolvedMention[] → store query → results)
  → Response Summary (results → human-readable message)
```

Key files: `pipeline.py`, `extract_agent.py`, `resolve_agent.py`,
`structure_agent.py`, `index.py`, `store.py`, `models.py`.

---

## Extension Points

### 1. Site Schema (`SiteSchema`)

A site declares its record types, facets, and how each facet behaves.

```python
@dataclass
class RecordType:
    name: str                    # "study", "sample", "file", "donor"
    applicable_facets: list[str] # which facets can constrain this type
    display_name: str            # for response messages
    display_plural: str          # "studies", "samples", "files"

@dataclass
class FacetSpec:
    name: str                          # e.g. "disease", "assay", "tissue"
    resolve_strategy: ResolveStrategy  # inline | tool | embedding
    values: list[str] | None          # for inline: full value list
    hierarchy: HierarchySpec | None   # ISA closure config
    display: DisplaySpec              # label prefix, plural, etc.

class SiteSchema:
    record_types: list[RecordType]    # what kinds of rows exist
    facets: list[FacetSpec]           # all searchable dimensions
    default_intent: str               # fallback record type
```

**Why `RecordType` matters**: The new site has files, donors, samples, datasets,
and studies. Not all facets apply to all record types (e.g., "assay" applies to
files and samples but not donors). The extract agent needs this mapping to
produce valid constraints for the detected intent. NCPI currently has two
implicit record types ("study" and "variable"); this makes it explicit.

**Resolve strategies** control how a mention gets grounded:

| Strategy    | When to use                    | How it works                                                                                            |
| ----------- | ------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `inline`    | Small value sets (<200 values) | Full value list injected into extract prompt; resolved at extraction time, no resolve agent call needed |
| `tool`      | Domain-specific logic          | Resolve agent calls a site-provided tool function                                                       |
| `embedding` | Large concept vocabularies     | KNN search over pre-computed embeddings, with optional ISA closure                                      |

This replaces the current hardcoded `Facet` enum and the implicit
small-vs-large facet split in `extract_agent.py`.

### 2. Store Backend (`StoreBackend` protocol)

Already partially abstracted as `StudyStore`. Needs to become a full protocol
that is record-type-aware:

```python
class StoreBackend(Protocol):
    def query_records(
        self,
        record_type: str,
        include: list[Constraint],
        exclude: list[Constraint],
        limit: int = 500,
    ) -> QueryResult: ...

    def get_record(self, record_type: str, record_id: str) -> dict | None: ...

    def get_facet_values(self, facet: str) -> list[str]: ...

    def count_records(
        self, record_type: str, include, exclude
    ) -> int: ...
```

Note: `query_variables` is NCPI-specific (ISA closure search over a secondary
table). The new site may not have "variables" at all. Site-specific query
methods can be added as mixins or registered as additional store capabilities.

Implementations:

- `DuckDBBackend` — current code, good for <1M rows
- `OpenSearchBackend` — new, for millions of rows

The choice is per-site configuration, not a code change.

### 3. Resolve Tools (`ResolveToolkit`)

Each site registers a set of tools the resolve agent can call. Core provides
generic tools; sites add domain-specific ones.

```python
# Core tools (always available)
search_by_keyword(query, facet) -> list[Match]
search_by_embedding(query, facet, k) -> list[Match]
get_children(concept_id) -> list[ConceptNode]

# Site-specific tool example (NCPI)
compute_consent_eligibility(purpose, disease) -> list[str]
get_focus_category_terms(category) -> list[ConceptNode]
list_variables_for_concept(concept_id) -> list[Variable]

# Site-specific tool example (AMR/genomics site)
resolve_ncbi_taxonomy(organism_name) -> list[TaxonNode]
resolve_antibiotic_class(name) -> list[AntibioticEntry]
search_card_database(query) -> list[AMRGene]
```

Tools are registered via a simple decorator or list:

```python
class NCPISite(SiteConfig):
    resolve_tools = [
        compute_consent_eligibility,
        get_focus_category_terms,
        get_consent_code_categories,
    ]
```

The resolve agent prompt is auto-generated from the tool list + site schema.
Each tool's docstring becomes part of the prompt, so the LLM knows when and how
to call it.

### 4. Prompt Templates

Currently: `EXTRACT_PROMPT.md`, `RESOLVE_PROMPT.md`, `STRUCTURE_PROMPT.md` are
NCPI-specific (they reference specific facets, consent codes, etc.).

Proposed: **Prompt = base template + site-specific sections**.

```
EXTRACT_PROMPT = core_extract_preamble
              + record_type_descriptions(site.schema)
              + facet_descriptions(site.schema)
              + site.extract_examples        # few-shot examples
              + core_extract_output_format
```

Sites provide:

- Record type descriptions (what each type represents)
- Facet descriptions (what each facet means in their domain)
- Few-shot examples (domain-specific query → mention mappings)
- Optional: custom resolve instructions per facet

Core provides:

- Output format instructions
- Multi-turn handling
- Intent detection logic (generalized to N record types)

### 5. Response Building

`response_summary.py` currently hardcodes NCPI label prefixes ("in focus",
"measuring", "on platform"). Sites need to configure:

```python
class DisplaySpec:
    label_prefix: str       # "in focus" / "for disease" / "in tissue"
    plural: str             # "foci" / "diseases" / "tissues"
    empty_label: str        # "any focus" / "any disease"
```

The `build_message()` and `build_query_structure()` functions become generic
over the site schema. Record type names and facet display specs drive the
English summary.

### 6. Embedding Configuration

Per-facet embedding config, with site-level defaults:

```python
class EmbeddingSpec:
    model_name: str              # e.g. "pritamdeka/S-PubMedBert-MS-MARCO"
    dimensions: int              # 768
    source: EmbeddingSource      # file (.npy) | opensearch (native kNN)
    embeddings_path: str | None  # for file source: path to .npy
    node_ids_path: str | None    # for file source: concept ID list
    ancestors: dict | None       # optional ISA ancestors for drill-down

class SiteConfig:
    default_embedding_model: str = "pritamdeka/S-PubMedBert-MS-MARCO"
    # per-facet overrides possible in FacetSpec.embedding
```

Start with one shared model. When a facet needs a specialized model (e.g., a
chemistry model for antibiotic compounds), override at the facet level.

For OpenSearch deployments, embeddings can live inside the index (native kNN)
rather than in separate .npy files — a significant simplification.

### 7. Data Loaders

Each site needs to load its catalog data into the store. This is inherently
site-specific:

```python
class SiteDataLoader(Protocol):
    def load_records(self, record_type: str) -> Iterator[Record]: ...
    def load_hierarchies(self) -> dict[str, HierarchyData]: ...
    def load_embeddings(self) -> dict[str, EmbeddingData]: ...
```

NCPI's loader reads from `ncpi-platform-studies.json` + classification output.
The new site might read from a database, CSV, FHIR API, or Gen3 metadata
service.

---

## Decision: Framework vs. Shared Package

### Option A: Python Framework (installable package)

```
pip install concept-search-core

# my_site/config.py
from concept_search_core import SiteConfig, DuckDBBackend

class MySite(SiteConfig):
    schema = SiteSchema(facets=[...], record_types=[...])
    store = DuckDBBackend(path="my-catalog.duckdb")
    resolve_tools = [my_custom_tool]
    ...

# my_site/app.py
from concept_search_core import create_app
app = create_app(MySite())
```

**Pros**:

- Clean separation: core is versioned, sites are independent repos
- Standard Python packaging (pip install, semver, changelogs)
- Forces good API boundaries
- Sites can pin core version, upgrade on their schedule

**Cons**:

- Overhead of maintaining a separate package (CI, releases, docs)
- Premature if we only have 1-2 sites
- Framework boundary decisions are hard to get right upfront
- Changes that touch core + site require coordinated releases

### Option B: Monorepo with site directories (recommended)

```
backend/
  core/              # shared pipeline, agents, caching
  sites/
    ncpi/            # NCPI-specific config, tools, loaders
    new_site/        # new site config, tools, loaders
  concept_search/    # keep as-is for now, refactor incrementally
```

**Pros**:

- Single repo, single CI, atomic commits across core + sites
- Easier to refactor boundaries incrementally
- No packaging overhead
- Can extract to a package later when boundaries are stable
- Same team maintains both — no coordination overhead

**Cons**:

- Tempting to reach across boundaries
- Harder for external teams to use without the full repo
- No independent versioning

### Recommendation

**Start with Option B.** Same team, two sites, boundaries not yet proven. The
monorepo forces us to define clean interfaces (via the extension points above)
without the overhead of managing a separate package. When boundaries stabilize
after the second site is running, extracting `core/` to a package (Option A) is
a straightforward mechanical step.

---

## Implementation Strategy: pydantic-ai native mechanisms

Pydantic-ai already provides the plugin/composition primitives we need. No
external DI framework, plugin registry, or agent orchestration library is
required.

### What we use from pydantic-ai

#### 1. `SiteDeps` dataclass via `deps_type` — site config injection

The resolve agent already uses `deps_type=ConceptIndex`. We expand this to a
richer `SiteDeps` that carries the full site configuration. Every agent, tool,
and prompt function receives it via `RunContext[SiteDeps]`.

```python
@dataclass
class SiteDeps:
    schema: SiteSchema                     # facets, record types, display config
    store: StoreBackend                     # DuckDB or OpenSearch
    index: ConceptIndex                     # concept lookups, embeddings
    expand_tags: TagExpander | None = None  # consent logic (NCPI) or None

# At startup:
deps = SiteDeps(
    schema=ncpi_schema,
    store=DuckDBBackend(path="catalog/concept-search.duckdb"),
    index=get_index(),
    expand_tags=ncpi_expand_consent_tags,
)

# At run time:
result = await pipeline.run(query, deps=deps)
```

This replaces scattered module-level imports of NCPI-specific code. Tools access
`ctx.deps.store` instead of importing `DuckDBStore` directly. The consent hook
is `ctx.deps.expand_tags` instead of a hardcoded import from `consent_logic`.

#### 2. `AbstractToolset` composition — core + site tools

Currently all resolve tools are registered with `@_agent.tool` decorators on a
single agent. Pydantic-ai's toolset system lets us compose core and site tools:

```python
from pydantic_ai.toolsets import AbstractToolset

class CoreResolveTools(AbstractToolset[SiteDeps]):
    """Keyword search, embedding search, tree navigation."""
    # search_concepts, search_concepts_by_embedding, get_concept_children

class NCPIResolveTools(AbstractToolset[SiteDeps]):
    """Consent eligibility, MeSH categories, measurement namespaces."""
    # compute_consent_eligibility, get_focus_category_terms, ...

# Agent creation composes them:
resolve_agent = Agent(
    model,
    deps_type=SiteDeps,
    toolsets=[CoreResolveTools(), site_config.resolve_toolset],
)
```

Sites that don't need consent tools simply omit `NCPIResolveTools`. The LLM
only sees the tools that are registered — no "tool not applicable" confusion.

Pydantic-ai also provides `FilteredToolset` for per-step filtering (e.g., hide
consent tools when resolving a non-consent mention) and `PreparedToolset` for
modifying tool definitions at runtime.

#### 3. `@agent.system_prompt` with `RunContext` — dynamic prompts

Currently prompts are loaded from static `.md` files. Pydantic-ai supports
dynamic prompt functions that receive the deps and build prompts from the site
schema:

```python
@extract_agent.system_prompt
async def build_extract_prompt(ctx: RunContext[SiteDeps]) -> str:
    schema = ctx.deps.schema
    sections = [CORE_EXTRACT_PREAMBLE]

    # Record types
    for rt in schema.record_types:
        sections.append(f"- **{rt.name}**: {rt.description}")

    # Inline facets get their values injected automatically
    for facet in schema.facets:
        if facet.resolve_strategy == "inline":
            values = ", ".join(facet.values)
            sections.append(f"**{facet.name}** (resolve immediately): {values}")
        else:
            sections.append(f"**{facet.name}** (resolve via tools)")

    # Site-specific few-shot examples
    sections.append(schema.extract_examples)
    sections.append(CORE_EXTRACT_OUTPUT_FORMAT)
    return "\n\n".join(sections)
```

The resolve prompt works similarly — core instructions are static, but the
facet-specific guidance and tool documentation are generated from the schema and
registered toolset.

#### 4. `StoreBackend` as a Python Protocol — passed via deps

No framework needed. Standard Python `Protocol` + `@runtime_checkable`:

```python
@runtime_checkable
class StoreBackend(Protocol):
    def query_records(self, record_type: str, ...) -> QueryResult: ...
    def get_facet_values(self, facet: str) -> list[str]: ...
    def count_records(self, record_type: str, ...) -> int: ...
```

DuckDB and OpenSearch both implement this. The store is passed into `SiteDeps`
at startup. Tools access it via `ctx.deps.store`. No service locator, no DI
container — just a dataclass field.

#### 5. `agent.override()` — testing and dev

Pydantic-ai's `override()` context manager (currently unused in this project)
is ideal for testing site swaps:

```python
with resolve_agent.override(deps=mock_site_deps, model="test"):
    result = await resolve_agent.run("cancer")
```

This lets us test the NCPI site config against the new site config without
changing any agent code. Also useful for running evals with different models.

### What we evaluated and don't need

| Approach                                               | Why not                                                                                        |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| External DI framework (dependency-injector, etc.)      | `deps` dataclass handles injection; adding a container adds complexity without benefit         |
| Entry points / plugin discovery (`importlib.metadata`) | Same team, monorepo, explicit imports — discovery is overkill                                  |
| Decorator registry pattern                             | pydantic-ai toolsets already provide typed tool registration                                   |
| LangChain / LangGraph                                  | Different paradigm (graph-based orchestration); our pipeline is simpler and already works well |
| Git submodules for code sharing                        | Painful merge conflicts; monorepo is simpler for same-team ownership                           |

### How this maps to Phase 1 tickets

| Ticket              | pydantic-ai mechanism                                          |
| ------------------- | -------------------------------------------------------------- |
| 1. SiteSchema       | `@dataclass` passed as field on `SiteDeps`                     |
| 2. Dynamic prompts  | `@agent.system_prompt` with `RunContext[SiteDeps]`             |
| 3. Resolve tools    | `AbstractToolset` subclasses, composed via `toolsets=[...]`    |
| 4. Consent plugin   | Optional `expand_tags` callable on `SiteDeps`                  |
| 5. Response labels  | `DisplaySpec` from `ctx.deps.schema`                           |
| 6. Data loading     | `SiteDataLoader` Protocol, called at startup to populate store |
| 7. Store protocol   | Python `Protocol`, passed via `SiteDeps.store`                 |
| 8. Intent detection | `RecordType` list from `ctx.deps.schema` in dynamic prompt     |
| 9. Move JSON files  | Site loader resolves its own data paths                        |
| 10. Eval gate       | `agent.override()` for testing both configs                    |

---

## Scope: What Changes for OpenSearch

DuckDB works well for NCPI's scale (~3K studies, ~170K variables). OpenSearch
becomes necessary when:

- Row counts exceed ~1M (DuckDB in-memory becomes expensive)
- Full-text search is needed (DuckDB's string matching is basic)
- Aggregations across large datasets (OpenSearch is optimized for this)
- High-concurrency query load (OpenSearch handles this natively)

### OpenSearchBackend implementation notes

```python
class OpenSearchBackend(StoreBackend):
    """
    Maps Constraint-based queries to OpenSearch bool queries.

    Constraint(facet="disease", values=["cancer", "diabetes"], exclude=False)
    →
    {"bool": {"must": [{"terms": {"disease": ["cancer", "diabetes"]}}]}}
    """
```

Key differences from DuckDB:

- **ISA closure**: stored as a keyword array field, queried with `terms`
- **Embedding search**: OpenSearch has native kNN (`script_score` or HNSW plugin)
  — embeddings live in the index, not separate .npy files
- **Aggregations**: `terms` agg replaces `SELECT DISTINCT` for facet values
- **Pagination**: `search_after` instead of `OFFSET`

### Index strategy

**One index per record type**, with the primary query target (files)
**denormalized** — each file document carries its donor's disease, sample's
tissue, study's platform, etc. This means the most common queries hit a single
fat index with no joins, which is critical at million-row scale.

```
files index (denormalized — primary query target):
  file_id, format, size, assay,
  donor_disease, donor_sex, donor_ancestry,    # from donor
  sample_tissue, sample_type,                   # from sample
  study_platform, study_design, dataset_name,   # from study/dataset
  concept_ids_closure[]                         # ISA closure for faceted search

donors index:   {disease, sex, ancestry, ...}
samples index:  {tissue, assay, donor_id, ...}
datasets index: {platform, focus, ...}
studies index:  {design, consent, PI, ...}
```

The smaller indices (donor, sample, study, dataset) exist for direct searches
on those types but are not the hot path.

### Embedding search in OpenSearch

OpenSearch supports dense vector fields with approximate kNN (HNSW). This means
embeddings live inside the index rather than in separate .npy files:

```json
{
  "concept_embedding": {
    "type": "knn_vector",
    "dimension": 768,
    "method": { "name": "hnsw", "engine": "faiss" }
  }
}
```

The `search_by_embedding` tool would call OpenSearch's kNN endpoint instead of
doing in-memory cosine similarity. This is a significant simplification for
large catalogs and avoids the separate embedding generation pipeline.

---

## Phased Rollout

### Phase 1: Extract clean interfaces (this repo, no new sites)

1. Define `StoreBackend` protocol formally (generalize current `StudyStore`)
2. Define `RecordType`, `FacetSpec`, `SiteSchema` — extract hardcoded facet
   knowledge from agents and index into declarative config
3. Move NCPI-specific resolve tools into a `sites/ncpi/` directory
4. Templatize prompts: split into core + site-specific sections
5. Make `response_summary.py` generic over site schema
6. Generalize intent detection from 2 types (study/variable) to N record types
7. **Test**: NCPI must pass all existing evals unchanged

### Phase 2: Add OpenSearch backend

1. Implement `OpenSearchBackend` conforming to `StoreBackend` protocol
2. Index NCPI data into OpenSearch for functional equivalence testing
3. Benchmark: DuckDB vs OpenSearch at NCPI scale
4. Implement native kNN embedding search in OpenSearch
5. Document when to choose which backend

### Phase 3: Second site

1. Create `sites/new_site/` with its own schema, tools, loader
2. Define record types: file, donor, sample, dataset, study
3. Wire up mixed ontologies (MeSH + CARD/NCBI Taxonomy)
4. Validate that core pipeline works without modification
5. Identify any remaining NCPI assumptions baked into core
6. Load test at target scale (millions of rows)

### Phase 4: Geo/temporal facets

1. Design constraint semantics for geographic facets (point, region, distance)
2. Design constraint semantics for temporal facets (range, before/after, period)
3. Extend `FacetSpec` with `constraint_type` (keyword | numeric | geo | temporal)
4. Add resolve strategies for geo/temporal (geocoding, date parsing)
5. Implement OpenSearch geo_point / date_range query support

### Phase 5: Extract package (if justified)

1. Move `core/` to its own repo with proper packaging
2. Both sites depend on `concept-search-core` package
3. Establish release cadence and compatibility policy

---

## Phase 1 Tickets (detailed)

### NCPI coupling analysis

The following table summarizes every location where NCPI-specific knowledge is
hardcoded in the backend. Phase 1 tickets are scoped to extract each of these
into site-specific config.

| Component                  | Location                                  | Coupling Type                                   |
| -------------------------- | ----------------------------------------- | ----------------------------------------------- |
| Facet enum                 | `models.py:30–42`                         | 9 hardcoded facet values                        |
| Small facets set           | `models.py:44–53`                         | Hardcoded inline-resolve set                    |
| Extract prompt values      | `EXTRACT_PROMPT.md:50–65`                 | Platform, dataType, sex, etc. baked into prompt |
| Resolve tools (consent)    | `resolve_agent.py:80–238`                 | 6 NCPI-specific tool functions                  |
| Resolve prompt (consent)   | `RESOLVE_PROMPT.md:25–70`                 | Consent code examples and tag table             |
| Index path resolution      | `index.py:21–72`                          | `NCPI_*` env vars, default paths                |
| Index facet field map      | `index.py:725–732`                        | `consentCodes`, `dataTypes`, `platforms`        |
| Index namespace prefixes   | `index.py:237–244`                        | `topmed:`, `phenx:`, `ncpi:`                    |
| Index demographics         | `index.py:148–152`                        | Dimension config tuples                         |
| Store schema               | `store.py:85–110`                         | `db_gap_id`, `phv_id`, dbGaP-specific columns   |
| Store JSON field access    | `store.py:329–330`                        | `$.title`, `$.studyAccession`                   |
| Response labels            | `response_summary.py:15–33`               | `_PLATFORM_DISPLAY`, `_FACET_PREFIX` dicts      |
| Consent logic              | `consent_logic.py` (240 LOC)              | GA4GH base codes, modifiers, eligibility rules  |
| Bundled JSON: focus        | `focus_categories.json`, `focus_isa.json` | MeSH disease hierarchy                          |
| Bundled JSON: consent      | `consent_codes.json`                      | GA4GH consent definitions                       |
| Bundled JSON: demographics | `demographic_mappings.json`               | Sex/race/ancestry normalization                 |

**Already generic** (no changes needed):

- `pipeline.py` — orchestration and merge logic
- `structure_agent.py` / `STRUCTURE_PROMPT.md` — boolean logic
- `router_agent.py` / `ROUTER_PROMPT.md` — multi-turn routing
- `cache.py` — generic LRU with TTL
- `embeddings.py` — facet-aware KNN search

### Ticket 1: Define `SiteSchema` and `FacetSpec` dataclasses

Extract the hardcoded `Facet` enum and `SMALL_FACETS` set (`models.py:30–53`)
into a declarative `SiteSchema` config. Each facet gets a `FacetSpec` with its
name, resolve strategy (`inline` | `tool` | `embedding`), and optional inline
values. Add `RecordType` dataclass. Create an NCPI site config that reproduces
the current behavior exactly.

**Touches**: `models.py`, new `site_schema.py`, new `sites/ncpi/config.py`

### Ticket 2: Dynamically inject facet values into prompts

The extract prompt (`EXTRACT_PROMPT.md:50–65`) hardcodes platform names, data
types, study designs, sex/race/ancestry values. Split the prompt into a core
template + site-injected sections. At agent creation time, build the prompt from
`SiteSchema` — inline facets get their value lists rendered automatically.

**Touches**: `extract_agent.py`, `EXTRACT_PROMPT.md`, `sites/ncpi/prompts/`

### Ticket 3: Split resolve tools into core vs. site-specific

Generic tools stay in core: `search_concepts`, `search_concepts_by_embedding`,
`get_concept_children`, `list_variables_for_concept`. NCPI-specific tools move
to site config: `get_focus_category_terms`, `get_consent_code_categories`,
`get_disease_specific_codes`, `get_consent_codes_for_base`,
`compute_consent_eligibility`, `get_measurement_category_concepts`
(`resolve_agent.py:80–238`). The resolve agent registers tools from
`SiteConfig.resolve_tools` at creation time.

**Touches**: `resolve_agent.py`, `RESOLVE_PROMPT.md`, `sites/ncpi/tools.py`

### Ticket 4: Extract consent logic into a site plugin

`consent_logic.py` (240 LOC) and `consent_codes.json` are entirely
GA4GH/NCPI-specific. Move them under `sites/ncpi/`. The core
`mention_constraints.py` gets a hook — if the site provides an `expand_tags`
function, it's called; otherwise tag expansion is a no-op.

**Touches**: `consent_logic.py` → `sites/ncpi/consent.py`,
`mention_constraints.py`, `consent_codes.json`

### Ticket 5: Make response summary generic over site schema

Replace hardcoded `_PLATFORM_DISPLAY` and `_FACET_PREFIX` dicts
(`response_summary.py:15–33`) with lookups into `FacetSpec.display`. The
`build_message()` function uses `DisplaySpec.label_prefix` instead of a
hardcoded mapping.

**Touches**: `response_summary.py`, `site_schema.py` (DisplaySpec)

### Ticket 6: Abstract data loading paths and field mappings

`index.py` has ~50 lines of NCPI-specific path resolution (`NCPI_REPO_ROOT`,
`NCPI_LLM_CONCEPTS_DIR`, etc.) and hardcoded field mappings (`consentCodes`,
`dataTypes`, `platforms` at line 725–732). Also namespace prefixes (`topmed:`,
`phenx:`, `ncpi:` at lines 237–244). Extract all of this into a
`SiteDataLoader` that the NCPI site implements.

**Touches**: `index.py`, `sites/ncpi/loader.py`

### Ticket 7: Formalize `StoreBackend` protocol

Generalize the current `StudyStore` into a `StoreBackend` protocol with
`query_records(record_type, ...)` instead of `query_studies(...)`. Rename
`db_gap_id` to a generic `record_id` internally. The DuckDB implementation
stays as-is functionally but conforms to the new protocol. NCPI's
variable-specific query becomes a site mixin rather than a core method.

**Touches**: `store.py`, `index.py`, `api.py`

### Ticket 8: Generalize intent detection to N record types

Currently intent is hardcoded to `"study"` | `"variable"` | `"auto"`.
Generalize to N record types from `SiteSchema.record_types`. The extract
prompt's intent section is generated from the record type list. The API's
lookup dispatch (`api.py:419–451`) routes on record type name instead of a
hardcoded if/else.

**Touches**: `extract_agent.py`, `api.py`, `models.py`

### Ticket 9: Move NCPI bundled JSON to site directory

Move `focus_categories.json`, `focus_isa.json`, `consent_codes.json`,
`demographic_mappings.json` from `backend/concept_search/` to
`backend/sites/ncpi/data/`. The site loader knows where to find them; core code
doesn't reference them.

**Touches**: file moves, `sites/ncpi/loader.py`

### Ticket 10: Verify — NCPI evals pass unchanged

Run the full eval suite (`make evals`) and confirm all extract, resolve, and
pipeline evals produce identical results. This is the gate for the entire phase.

**Touches**: nothing (validation only)

### Suggested ordering

```
Ticket 1 (schema)
  ├─→ Ticket 2 (prompts)         ─┐
  ├─→ Ticket 3 (resolve tools)   ─┤
  ├─→ Ticket 4 (consent plugin)  ─┤── can parallelize
  ├─→ Ticket 5 (response labels) ─┤
  ├─→ Ticket 6 (data loading)    ─┘
  │
  ├─→ Ticket 7 (store protocol)
  ├─→ Ticket 8 (intent detection)
  ├─→ Ticket 9 (move JSON files)
  │
  └─→ Ticket 10 (eval gate)
```

---

## Decisions (resolved — implementation)

| Question                                | Answer                                                                                                                                                                  |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OpenSearch managed or self-hosted?      | Decide later. The `StoreBackend` protocol abstracts this — it's a deployment decision, not a design decision.                                                           |
| Index-per-record-type or single index?  | Index per record type. Primary query target (files) is **denormalized** with donor/sample/study fields inlined. Other indices exist for direct searches on those types. |
| Geo/temporal constraint semantics?      | Defer to Phase 4. Add a `constraint_type` field to `FacetSpec` now (keyword \| numeric \| geo \| temporal) but don't implement geo/temporal until needed.               |
| Resolve cache keys across record types? | Cache on `(facet, text)` — facets are universal across record types. No need for record_type in the key.                                                                |

## Open Questions

1. **Denormalization update strategy**: When a donor's metadata changes, how do
   we propagate that to all their file documents in the denormalized index?
   Options: full reindex (simple, slow), partial update by donor_id (fast,
   more complex), or event-driven pipeline. Depends on how often metadata
   changes vs. how stale is acceptable.

2. **Cross-type result linking**: The search returns records of one type (e.g.,
   files). How does the frontend discover related records (the donor, sample,
   study)? Options: include foreign keys in results and let frontend fetch,
   or return a pre-joined response with nested related records.
