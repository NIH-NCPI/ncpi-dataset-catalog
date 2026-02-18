# NCPI Dataset Catalog — Research Mode Roadmap

> Roadmap for evolving the NCPI Dataset Catalog from a browse-and-filter tool into a research planning workbench.
> Status: DRAFT — Feb 2026

---

## Two Modes

| Mode              | Interface                                            | User mindset                                                          |
| ----------------- | ---------------------------------------------------- | --------------------------------------------------------------------- |
| **Search Mode**   | Traditional table + filters (current site)           | "I know what I'm looking for — let me filter and browse"              |
| **Research Mode** | Chat (left) + artifact area (right), Claude.ai-style | "I have a research question — help me find data and plan my analysis" |

Search Mode is the current `/studies` page — it stays as a fallback for power users who want direct facet control. Research Mode is the new primary experience.

---

## Research Mode

Two-panel layout following the Claude.ai artifacts pattern (cc-design #296 "inside-out mode"). Chat on the left drives a general-purpose **artifact area** on the right.

---

## Research Intent Capture (PICOT)

**This is the central idea.** The chat isn't just filtering a table — it's building a structured research plan. Every conversation progressively fills in a **PICOT schema** that the system uses to find data, check feasibility, and suggest next steps.

### The PICOT Card

The primary artifact in Research Mode is an **editable PICOT card** — a live, visible representation of "what the system thinks you're trying to do." It has five slots:

| Slot                            | What it captures                                            | Example                                            | Catalog mapping                           |
| ------------------------------- | ----------------------------------------------------------- | -------------------------------------------------- | ----------------------------------------- |
| **P** — Population              | Disease focus + demographics                                | "Adults with T2D, diverse ancestry, n > 1000"      | Focus/Disease, Participants, demographics |
| **I/E** — Intervention/Exposure | Independent variable — what you're studying the effect _of_ | "Smoking status, pack-years; GLP-1 medication use" | Measurement facet (variable-level)        |
| **C** — Comparator              | Strata/groups needed to make comparisons                    | "Current/former/never smokers; dose groups"        | Variable granularity (coded value level)  |
| **O** — Outcome                 | Dependent variable — what you're measuring the effect _on_  | "HbA1c, body weight, CV events"                    | Measurement facet (variable-level)        |
| **T** — Time                    | Whether longitudinal measures are needed                    | "Repeated measures over 2+ years"                  | Study Design facet                        |

### How It Works in Conversation

The system elicits PICOT slots naturally, without making the user fill out a form:

```
User:  "I'm studying whether smoking modifies the effect of GLP-1 agonists
        on glycemic control in T2D patients."

System: [Fills P: T2D, I/E: GLP-1 agonists + smoking, O: glycemic control]
        [Shows PICOT card in artifact area with 3 slots filled, 2 unfilled]

        "Got it. I've captured your research question. A couple of things
         I'd like to clarify:

         - For the Comparator: do you need current/former/never smoker
           groups, or pack-years bins?
         - For Time: do you need longitudinal follow-up (pre/post GLP-1),
           or is cross-sectional OK?"

User:  "Current/former/never, and yes I need longitudinal."

System: [Fills C: current/former/never, T: longitudinal]
        [PICOT card now fully filled → switches artifact to Dataset Results]

        "Found 3 studies with all five PICOT requirements met, and 14 more
         with partial coverage. The top match is ACCORD (phs000209) —
         it has smoking status, GLP-1 medication records, and HbA1c at
         baseline + 6-month follow-up."
```

### Key Behaviors

- **Unfilled slots** are shown as gentle prompts on the card, not blockers — partial intent always returns results
- User can **click to edit any slot** directly on the card, or keep chatting to refine
- Slot changes **immediately update** the Dataset Results artifact
- System **proactively asks** about empty slots based on what's already filled
- **I/E + O together** determine variable-level matching — the system checks studies have measurements on _both_ sides of the question
- **C** (Comparator) requires the deepest metadata — not just "has smoking data" but "distinguishes current/former/never at the variable level"
- The schema supports domain-specific **modules** (GWAS, eQTL, DEG, etc.) — see [SCHEMA-research-intent.md](SCHEMA-research-intent.md) for the full definition

### Match Depth Tiers

How well we can fill each slot depends on the depth of our metadata:

| Tier                                  | Available                                                                    | Slots it serves                     |
| ------------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------- |
| **Study-level** (now)                 | Focus/Disease, Study Design, Platform, Data Type, Consent Code, Participants | P (condition), T, data requirements |
| **Variable-level** (concept pipeline) | Variable concept classification                                              | I/E, O, covariates                  |
| **Value-level** (future)              | Coded variable categories                                                    | C (comparator strata)               |

---

## Artifact Types

The right panel renders different artifacts as the conversation progresses:

| Artifact                   | When shown                      | Content                                                                                     |
| -------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------- |
| **Research Plan**          | Default / early conversation    | PICOT card — auto-fills from chat context and system questions; user can also edit directly |
| **Dataset Results**        | After plan has filterable slots | Studies table with filter chips; column-header filters                                      |
| **Study Detail**           | User clicks into a study        | Study metadata, variables, publications                                                     |
| **Workflow Selection**     | "I want to analyze this"        | Available workflows for selected data                                                       |
| **Workflow Configuration** | User picks a workflow           | Stepper UI — uploads, parameters, design formula                                            |

Chat messages trigger artifact transitions. The user can also click to switch directly.

---

## Research Mode Phases

Research Mode evolves through four phases, each adding a new capability to the conversation:

```
Discovery → What's Here → Hypothesis → Prior Art
```

### Phase A: Discovery (now → next)

The user has a research question and wants to find matching datasets.

- Chat elicits PICOT slots through conversation
- System fills slots, asks clarifying questions, filters datasets
- Artifact area shows Research Plan → Dataset Results
- "These 8 studies have both smoking status and HbA1c with longitudinal follow-up"

### Phase B: What's Here

The user doesn't have a specific question yet — they want to explore what the catalog contains.

- "What diseases are most studied?" → facet distribution summaries
- "What data types are available for cancer?" → scoped histograms
- "What's the overlap between AnVIL and BDC?" → platform comparisons
- Artifact area renders charts, distributions, summaries (not just tables)

### Phase C: Hypothesis Generation

The system helps the user _form_ a research question from the data.

- "I'm interested in cardiovascular outcomes — what exposures are well-represented?"
- System identifies gaps and opportunities in the catalog
- Suggests PICOT framings: "There are 12 longitudinal cohorts with both smoking and CV outcomes — you could study effect modification by ancestry"
- Builds toward a publishable research plan

### Phase D: Prior Art Review

The system connects dataset discovery to the existing literature.

- "Have these datasets been used to study smoking and diabetes?"
- Surface publications linked to studies (we already have dbGaP publications)
- Identify what's been done vs. what's novel
- "phs000179 (FHS) has 47 publications on cardiovascular outcomes, but none examine GLP-1 effect modification by smoking status"

---

## Site-Level Roadmap Items

### 1. Home Page & Onboarding

A landing page on `/` that orients visitors and invites them into Research Mode.

- **What's here** summary (study count, platform count, data types, participant total)
- **Prominent chat input** — the primary CTA; typing transitions into the two-panel Research Mode layout
- **Example research questions** as clickable chips (e.g., "I'm studying the genetics of Type 2 diabetes in diverse populations")
- Toggle to enter Search Mode directly (browse the table)
- Links to About page

### 2. About / Methodology Page

Explains how the catalog was built, scoped, and where it stands.

- Data sources (AnVIL, BDC, CRDC, KFDRC, dbGaP)
- How studies are ingested and classified (concept extraction, variable classification pipeline)
- Alpha disclaimer: focused on **recall over precision** — we surface more results rather than fewer
- Known limitations and what's coming next

### 3. Research Mode Layout

The two-panel layout itself.

- **Layout**: Chat panel on the **left (~40%)**, artifact area on the **right (~60%)**
- **Thin icon sidebar** on far left: new conversation, session history, settings
- **Session title** at top of chat panel, derived from research context (e.g., "T2D Genetics in Diverse Populations")
- Chat input pinned to bottom of left panel
- Panel widths resizable via drag handle

#### Artifact Types

| Artifact                   | When shown                      | Content                                                                                     |
| -------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------- |
| **Research Plan**          | Default / early conversation    | PICOT card — auto-fills from chat context and system questions; user can also edit directly |
| **Dataset Results**        | After plan has filterable slots | Studies table with active filter chips; column-header filters                               |
| **Study Detail**           | User clicks into a study        | Study metadata, variables, publications                                                     |
| **Workflow Selection**     | "I want to analyze this"        | Available analysis workflows for selected data                                              |
| **Workflow Configuration** | User picks a workflow           | Stepper UI — uploads, parameters, design formula                                            |

### 4. Table-Header Facet Filtering

Move facet filtering into the table column headers within the Dataset Results artifact. Excel/Google Sheets style.

- **Column headers show unique-value count** (e.g., "Platform (5)", "Focus / Disease (954)")
- Clicking a column header opens a **histogram/value-list dropdown**
- Active filters shown as removable chips above the table
- Chat-applied filters and manual column filters coexist in the chip bar

### 5. Chat Entry Points & Persistence

- **Home page hero input** is the primary entry into Research Mode
- **Persistent chat icon** in header nav on all pages
- Study detail pages: "Find similar studies" opens Research Mode with context
- Conversation and PICOT state persist across navigation
- Session history accessible from the icon sidebar

---

## Sequencing

```
Phase 1 (now)        Phase 2                      Phase 3              Phase 4
─────────────        ───────                      ───────              ───────
1. Home Page         3. Research Mode Layout       What's Here          Workflow Artifacts
2. About Page        4. Table-Header Facets        Hypothesis Gen.      Workflow Config
                     5. Chat Persistence           Prior Art Review     Cross-platform Launch
```

- **Phase 1**: Content and orientation — no backend changes, fast to ship.
- **Phase 2**: The core UX — Research Mode with Discovery (Phase A).
- **Phase 3**: Research Mode gains exploration and intelligence (Phases B, C, D).
- **Phase 4**: From "I found my data" to "I'm running my analysis."

> Long-term product name candidate: **NCPI Research Workbench**

---

## Design Briefs Needed

| #   | Brief                             | Covers                                                                                                          |
| --- | --------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 1   | Home page & onboarding            | Home page, mode entry, example chips                                                                            |
| 2   | About / methodology page          | About page                                                                                                      |
| 3   | Research Mode layout + PICOT card | Two-panel layout, artifact transitions, PICOT card design, slot-filling UX, proactive prompts, chat persistence |
| 4   | Table-header facet filtering      | Column filters, chip bar, chat+manual filter coexistence                                                        |
