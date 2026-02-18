# Design Brief: Research Mode Layout + PICOT Card

> For: Kaspars | Status: DRAFT — Feb 2026
> Refs: [ROADMAP-chat-ux.md](ROADMAP-chat-ux.md) · [SCHEMA-research-intent.md](SCHEMA-research-intent.md) · cc-design #296 · cc-design #247

---

## 1. Context

The NCPI Dataset Catalog currently has ~2,944 studies from four NIH cloud platforms (AnVIL, BDC, CRDC, KFDRC). Today it's a browse-and-filter table with a facet sidebar on the left. We've built a chat-based search POC on a separate `/chat` page, but it's disconnected from the main site.

We want to replace the browse-first experience with a **Research Mode** — a conversational interface where the user describes their research question and the system progressively builds a structured research plan, finds matching datasets, and eventually guides them into analysis workflows.

### Reference patterns

- **Claude.ai artifacts mode** — chat on the left, artifact on the right. The primary reference for our two-panel layout.
- **BRC Analytics inside-out prototype** (cc-design #296) — Kaspars's Figma prototype showing chat-driven assembly selection + workflow configuration. Same layout, different domain.
- **Current NCPI `/chat` page** — standalone chat with inline results table. This gets absorbed into Research Mode.
- **Current NCPI `/studies` page** — facet sidebar + table. This becomes "Search Mode" (a fallback).

---

## 2. What We're Designing

A two-panel **Research Mode** layout with:

1. **Chat panel** (left) — the conversation where the user describes their research
2. **Artifact area** (right) — a general-purpose display that changes based on conversation state
3. **PICOT card** — the primary artifact, a live structured representation of the user's research intent

### What's in scope for this brief

- Two-panel layout (proportions, resize, responsive behavior)
- Chat panel design (message bubbles, input, session management)
- PICOT card design (slot layout, filled/unfilled states, editing, auto-fill animations)
- Artifact transitions (how the right panel moves between Research Plan → Dataset Results → Study Detail)
- Table-header facet filtering (within the Dataset Results artifact)
- Chat entry and persistence (how you get into Research Mode, how state survives navigation)

### Site context

Research Mode lives within the existing NCPI Dataset Catalog site — it's not a separate app. The site header, navigation, and branding remain visible.

**Navigation update**: Move entity tabs (Studies, Platforms) from their current position into the **top header nav** — similar to BRC Analytics (which has Organisms, Assemblies in the header). This frees the main content area for the two-panel Research Mode layout and gives clean navigation between:

```
[NCPI Logo]  Studies  Platforms  Data Dictionary  About  [Visit ncpi-acc.org]  [Research Mode icon]
```

"Research Mode" entry could be a prominent icon/button in the header (always visible) or replace the current default route entirely.

### Design system reuse

This layout and its components must be designed as **reusable building blocks** that work across multiple Clever Canary sites with different data models and capabilities:

| Site                     | Data entities                    | Has workflows? | PICOT card differences                                                 |
| ------------------------ | -------------------------------- | -------------- | ---------------------------------------------------------------------- |
| **NCPI Dataset Catalog** | Studies, Platforms               | No (future)    | Full PICOT — population, exposure, outcome, comparator, time           |
| **BRC Analytics**        | Organisms, Assemblies, Workflows | Yes (Galaxy)   | Simpler intent — organism + analysis goal → assembly → workflow config |
| **AnVIL**                | Datasets, Workspaces             | No             | PICOT variant — population, data type, consent, workspace context      |
| **HCA Data Explorer**    | Projects, Samples, Files         | No             | PECO variant — tissue, disease, assay type, developmental stage        |

**Reusable components:**

- Two-panel layout shell (chat left, artifact right, icon sidebar)
- Chat panel (message history, input, session management)
- Intent card (generic slot-based card — PICOT is one configuration; BRC Analytics uses a simpler organism/workflow card)
- Artifact area frame (tab/breadcrumb navigation between artifact types)
- Column-header filter dropdowns (histogram + select + sort)
- Filter chip bar (with provenance tooltips and unresolved mentions)

The intent card slot schema should be **configurable per site** — NCPI uses 5 PICOT slots, BRC Analytics might use 3 (Organism, Analysis Type, Data), HCA might use 4 (Tissue, Disease, Assay, Stage). The layout and interaction patterns stay the same.

### What's out of scope (later briefs)

- Home page / landing page design
- About / methodology page
- Workflow Selection and Workflow Configuration artifacts (Phase 4)
- Mobile / narrow-screen adaptation (unless Kaspars wants to address it early)

---

## 3. The PICOT Card

This is the novel UI element. It's a structured, editable card that shows the user's research intent as five labeled slots.

### Slots

| Slot    | Label                   | Example content                                                                                 |
| ------- | ----------------------- | ----------------------------------------------------------------------------------------------- |
| **P**   | Population              | Adults with Type 2 diabetes, diverse ancestry, n > 1,000                                        |
| **I/E** | Exposure / Intervention | Cigarette smoking (pack-years, current/former/never); GLP-1 agonists (semaglutide, liraglutide) |
| **C**   | Comparator              | Smoking strata: never / former / current                                                        |
| **O**   | Outcome                 | Glycemic response (HbA1c, delta from baseline); Weight response (body weight, delta)            |
| **T**   | Time                    | Longitudinal, baseline + follow-up at 3–12 months                                               |

### Fields within each slot

Each slot contains structured sub-fields. The card may display these as a single free-text summary, but the system parses them into these fields internally. Direct editing should allow the user to modify individual fields where practical.

**P — Population**

| Field                 | Example          | Notes                        |
| --------------------- | ---------------- | ---------------------------- |
| `condition_focus`     | Type 2 diabetes  | Maps to Focus/Disease facet  |
| `age_range`           | Adults (18–65)   | Not yet filterable           |
| `sex`                 | Both             | Not yet filterable           |
| `ancestry`            | African American | Not yet filterable           |
| `minimum_sample_size` | 1,000            | Filters on participant count |

**I/E — Intervention / Exposure**

| Field                | Example                                          | Notes                                   |
| -------------------- | ------------------------------------------------ | --------------------------------------- |
| `concept`            | Cigarette smoking                                | The exposure/intervention being studied |
| `operationalization` | pack-years (primary), current/former/never (alt) | How it must be measured in the data     |

Each operationalization entry has: `measurement` (variable name), `role` (primary / alternative), `threshold` (e.g., ">= 10 pack-years"), `optional` flag.

**C — Comparator**

| Field    | Example                | Notes                                                     |
| -------- | ---------------------- | --------------------------------------------------------- |
| `type`   | Smoking strata         | What dimension is being compared                          |
| `levels` | never, former, current | The specific groups — requires variable-level granularity |

**O — Outcome**

| Field                | Example                                      | Notes                               |
| -------------------- | -------------------------------------------- | ----------------------------------- |
| `concept`            | Glycemic response                            | The outcome being measured          |
| `operationalization` | HbA1c, delta from baseline, 3–6 month window | How it must be measured in the data |
| `priority`           | Primary                                      | Primary / secondary / exploratory   |

Each operationalization entry has: `measurement`, `delta` (change from baseline?), `time_window`.

**T — Time**

| Field                 | Example             | Notes                                      |
| --------------------- | ------------------- | ------------------------------------------ |
| `design_requirement`  | Longitudinal        | Longitudinal / cross-sectional / either    |
| `timepoints_required` | Baseline, follow-up | Specific timepoints needed                 |
| `minimum_follow_up`   | 6 months            | Minimum duration of longitudinal follow-up |

See [SCHEMA-research-intent.md](SCHEMA-research-intent.md) for the full JSON schema with all field definitions, intent types, and domain modules.

### Not a form

These fields exist in the data model, but the card should **not** render as a form with labeled inputs. The challenge: we have structured data but want a conversational feel. Some principles:

- **Start as prose, expand on interaction.** When a slot is first filled from chat, show it as a natural-language summary ("Adults with T2D, diverse ancestry, n > 1,000"). Only reveal the individual fields (condition, age, ancestry, sample size) when the user clicks to edit.
- **Don't show empty field labels.** An unfilled slot says "What population are you studying?" — not "Condition: **_, Age: _**, Sex: **_, Ancestry: _**". The sub-fields only appear after the slot has content.
- **Progressive disclosure.** The card starts compact (maybe just P visible) and grows as the conversation fills slots. A fully filled card with all 5 slots expanded is the end state, not the starting state.
- **Editing is inline, not modal.** Clicking a slot expands it in place. The sub-fields appear as editable chips or inline text, not as a separate form dialog. Think of editing a tag in a note-taking app — light, fast, dismissible.
- **The chat is always the primary input.** The card is a mirror of the conversation. Most users will fill it by chatting. Direct editing is a power-user shortcut, not the expected path.
- **Use the field labels as gentle structure, not form labels.** Instead of "Condition Focus:" as a form label, consider lighter treatments like a subtle "condition" tag next to "Type 2 diabetes", or group fields visually without labeling each one.

### States

Each slot can be in one of these states:

| State                | Visual treatment                                                         | Example                                                      |
| -------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------ |
| **Empty**            | Placeholder prompt text, muted                                           | _"What population are you studying?"_                        |
| **Filling**          | Typing indicator or shimmer while system parses                          | (brief, after user message)                                  |
| **Filled**           | Solid content, editable on click                                         | "Adults with T2D, diverse ancestry"                          |
| **Ambiguous**        | Highlight with clarification prompt                                      | "Did you mean current smokers only, or all smoking history?" |
| **Over-constrained** | Warning indicator — this slot (combined with others) yields zero results | See "Zero results & backoff" below                           |

### Zero results & backoff

A common scenario: the combination of filled PICOT slots is too specific and returns zero studies. This is especially likely for poorly annotated datasets (e.g., many AnVIL studies have minimal metadata). The system must **never just show an empty table** — it should actively help the user understand what's available and back off gracefully.

**Backoff strategy:**

1. **Identify the constraining slot** — which slot, when removed, brings results back? Highlight it on the PICOT card.
2. **Show what we do have** — "0 studies match all 5 slots, but **14 studies** match P + I/E + O (without the longitudinal requirement)" — offer to relax specific constraints.
3. **Suggest relaxations** — "Try removing the Time constraint, or broadening Population from 'African American' to all ancestries."
4. **Tiered results** — show results at decreasing match levels:
   - Full PICOT match: 0 studies
   - 4-slot match (drop T): 3 studies
   - 3-slot match (drop T + C): 14 studies
   - P-only match: 127 studies
5. **Annotation gap callout** — when relevant, note that some platforms have sparser metadata: "Some AnVIL studies may match but lack detailed variable annotations — consider browsing them directly."

The Dataset Results artifact should support this visually — e.g., a banner above the table saying "No exact matches. Showing 14 studies matching 4 of 5 criteria" with the relaxed slot indicated, and a one-click way to restore the full constraint.

### Input channels

The card fills via three channels — the design needs to handle all three gracefully:

1. **Auto-fill from chat** — user says something, system extracts PICOT slots, card updates. This is the primary channel.
2. **Auto-fill from system questions** — system asks "Do you need longitudinal data?", user answers, slot fills.
3. **Direct edit** — user clicks a slot on the card and types/selects. This should feel lightweight (inline edit, not a modal).

### Conversation-to-card flow

```
User message → system parses → PICOT card updates → (optional: system asks clarifying question)
                                    ↑
                            user can also click
                            to edit card directly
```

When enough slots are filled to produce useful results, the artifact area should offer to transition to Dataset Results (or do so automatically with a way to go back to the plan).

---

## 4. Artifact Area

The right panel renders different content depending on conversation state.

### Artifact types (Phase 2 scope)

| Artifact            | Trigger                           | Content                                          |
| ------------------- | --------------------------------- | ------------------------------------------------ |
| **Research Plan**   | Default on new conversation       | PICOT card (see above)                           |
| **Dataset Results** | PICOT has filterable slots filled | Studies table + column-header filters + chip bar |
| **Study Detail**    | User clicks a study row           | Full study metadata, variables, publications     |

### Questions to resolve: Artifact transitions

These are the key UX questions for this brief:

**Q1: When does the artifact switch from Research Plan to Dataset Results?**

- Option A: **Automatic** — as soon as any PICOT slot maps to a filterable facet, show results. The PICOT card collapses to a summary bar above the table.
- Option B: **User-triggered** — PICOT card stays until user says "show me results" or clicks a button. More control, but adds friction.
- Option C: **Split view** — PICOT card stays visible as a compact strip at the top of the artifact area, with Dataset Results below it. No transition, both visible at once.

**Q2: How does the user get back to the Research Plan from Dataset Results?**

- Option A: **Tab/toggle** at the top of the artifact area ("Plan" | "Results" | "Detail")
- Option B: **Breadcrumb trail** (Plan → Results → Study Detail) with click-to-navigate
- Option C: **Chat-driven** — user says "show my plan" or "go back to the plan"
- Option D: **Always-visible summary** — the PICOT card is always shown as a collapsed bar above whatever artifact is active; click to expand

**Q3: Can the user view Dataset Results and the PICOT card simultaneously?**

- If yes: how do we split the vertical space? Collapsible card above the table?
- If no: how do we keep the user oriented about what filters are active?

**Q4: What happens when the user clicks a study row in Dataset Results?**

- Option A: **Replace** the artifact area with Study Detail (breadcrumb to go back)
- Option B: **Slide-over panel** on top of the results (dismiss to return)
- Option C: **Navigate** to the existing study detail page (leaves Research Mode — probably bad)

**Q5: How do chat-applied filters and manual column filters interact?**

- Chat says "diabetes studies with WGS" → chips appear for Focus: Diabetes, DataType: WGS
- User then clicks the Platform column header and selects "BDC"
- Are these the same chip bar? Can the user remove chat-applied chips manually?
- If the user removes a chat-applied chip, does the PICOT card update?

**Q6: What's the empty state?**

- New conversation, no messages yet. What does the artifact area show?
- Option A: Empty PICOT card with all placeholder prompts
- Option B: A welcome/onboarding message ("Describe your research question to get started")
- Option C: Catalog summary stats (2,944 studies, 5 platforms, 65 data types...) as an invitation

**Q7: How do we handle the transition from home page into Research Mode?**

- User types in the home page hero input and hits enter
- What's the animation/transition into the two-panel layout?
- Does the home page dissolve into Research Mode, or is it a navigation to a new route?

---

## 5. Two-Panel Layout

### Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│ [NCPI Logo]  Studies  Platforms  Data Dictionary  About    [🔬 Research Mode] │
├──────┬────────────────────┬──────────────────────────────────────────┤
│ Icon │                    │                                          │
│ bar  │   Chat Panel       │     Artifact Area                        │
│      │                    │                                          │
│ [+]  │  [Session Title]   │  [Research Plan]                         │
│ [📋] │                    │  or                                      │
│ [⚙]  │  Message history   │  [Dataset Results]                       │
│      │  ...               │  or                                      │
│      │  ...               │  [Study Detail]                          │
│      │                    │                                          │
│      │  ┌──────────────┐  │                                          │
│      │  │ Chat input   │  │                                          │
│      │  └──────────────┘  │                                          │
└──────┴────────────────────┴──────────────────────────────────────────┘
```

The site header with navigation is always visible above the two-panel layout. When on a Studies or Platforms page (Search Mode), the full-width table renders below the header as it does today. When in Research Mode, the two-panel layout fills the space below the header.

### Proportions

- **Icon sidebar**: ~48px fixed
- **Chat panel**: ~35–40% of remaining width (min ~320px)
- **Artifact area**: ~60–65% of remaining width
- **Drag handle** between panels for resizing

### Icon sidebar

Thin vertical bar on the far left:

| Icon         | Action                                        |
| ------------ | --------------------------------------------- |
| **+**        | New conversation (clears PICOT, fresh start)  |
| **History**  | Session list (past conversations with titles) |
| **Settings** | Preferences (not designed yet)                |

### Chat panel

- **Session title** at top — auto-generated from PICOT context (e.g., "T2D + Smoking + GLP-1 Study")
- **Message history** — scrollable, newest at bottom
- **Message types**: user bubbles, system responses, system clarifying questions
- **Chat input** pinned to bottom — text area with send button
- System messages may include inline elements: clickable study references, slot-fill confirmations

### Artifact area

- **Top bar**: artifact type indicator + navigation (tab bar, breadcrumbs, or toggle — see Q1/Q2)
- **Content area**: renders the current artifact (PICOT card, studies table, study detail)
- When showing Dataset Results: includes chip bar for active filters and column-header filter controls

---

## 6. Dataset Results Artifact

When the artifact area shows the studies table:

### Table columns

Same as current `/studies` page:

| Column          | Content                      | Filter type            |
| --------------- | ---------------------------- | ---------------------- |
| Platform        | Tag chips (AnVIL, BDC, etc.) | Checkbox list          |
| Study           | Linked title                 | Text search            |
| dbGaP Id        | phs number                   | Text search            |
| Focus / Disease | Text                         | Value list / histogram |
| Data Type       | Tag chips                    | Checkbox list          |
| Study Design    | Text                         | Checkbox list          |
| Consent Code    | Tag chips                    | Checkbox list          |
| Participants    | Number                       | Range slider           |

### Column-header filters (Excel-style)

- Each column header shows the **count of unique values** in the current result set
- Clicking opens a **dropdown** with value list, counts, and checkboxes
- For high-cardinality columns (Focus/Disease: 954 values), include a search box in the dropdown
- The dropdown should include a **mini histogram or sparkline chart** showing the value distribution — this gives the user an at-a-glance sense of the data shape before they select filters (e.g., Platform dropdown shows a bar chart of study counts per platform; Participants shows a distribution curve)
- Within the dropdown, the user can:
  - **Sort** values (alphabetical, by count descending, by count ascending)
  - **Select / deselect** individual values as filters (checkboxes)
  - **See distribution** — histogram bars or count badges next to each value, updated live as other filters change
- Active filters appear as **removable chips** in a bar above the table

### Filter chip bar

- Shows all active filters from both chat and manual column selection
- Each chip shows facet + value (e.g., "Platform: BDC", "Focus: Diabetes Mellitus")
- Chat-originated chips could be visually distinguished (different color or icon) — see Q5
- Removing a chip updates the table immediately

#### Provenance & unresolved mentions

Chat-originated chips should support a **detail view** (tooltip, popover, or expandable) showing:

- **User text → resolved term**: what the user actually said and how it mapped (e.g., _"diabetes" → Focus: Diabetes Mellitus_; _"whole genome" → Data Type: WGS_)
- **Confidence indicator**: how confident the mapping was (high = exact match, medium = semantic match, low = best guess)

If any user mentions could **not** be mapped to a catalog term, these should appear as a visible **"Unresolved" section** in the chip bar — e.g., an amber chip or a callout:

> _Could not match: "pack-years bins" — Can you clarify what you meant by "pack-years bins"? Did you mean a specific measurement variable?_

This keeps the user informed about what the system understood vs. what it dropped, and gives them a path to fix it.

---

## 7. Conversation Examples

### Example 1: Focused research question → results → study drill-down

```
[Artifact: empty PICOT card with placeholder prompts]

User: "I'm studying whether smoking modifies the effect of GLP-1 agonists
       on glycemic control in T2D patients."

[Artifact: PICOT card fills P, I/E, O — C and T show prompts]

System: "I've captured your research question:
         P: Type 2 diabetes
         I/E: Smoking + GLP-1 agonists
         O: Glycemic control (HbA1c)

         Two things to clarify:
         - Comparator: current/former/never smokers, or pack-years bins?
         - Time: do you need longitudinal follow-up?"

User: "Current/former/never, and yes, longitudinal."

[Artifact: PICOT card fully filled → transitions to Dataset Results]

System: "Found 3 studies matching all PICOT requirements, plus 14 with
         partial coverage. The top match is ACCORD (phs000209)."

User: (clicks ACCORD / phs000209 row in the table)

[Artifact: transitions to Study Detail for ACCORD]
[Study Detail shows tabbed or sectioned view:]
  - Overview: title, dbGaP ID, platforms, consent codes, description
  - Demographics: participant count, age distribution, sex breakdown,
    ancestry/ethnicity summary
  - Publications: linked publications from dbGaP (47 CV-related papers,
    none on GLP-1 + smoking interaction)
  - Variables: summary of measured variables, grouped by concept —
    highlights which PICOT slots this study covers
    (✓ smoking status, ✓ HbA1c, ✓ medication records, ✓ longitudinal)

System: "ACCORD has 10,251 participants with T2D. It includes smoking
         status (current/former/never), HbA1c at baseline and follow-up,
         and medication records including GLP-1 agonists. 47 publications
         on cardiovascular outcomes, but none examine GLP-1 effect
         modification by smoking status — this could be a novel angle."

User: "What about the other two full matches?"

[Artifact: transitions back to Dataset Results, scrolled to the 3 matches]
```

### Example 2: Exploratory start (gradual slot filling)

```
[Artifact: empty PICOT card]

User: "What diabetes studies do you have?"

[Artifact: PICOT card fills P: diabetes — other slots empty]

System: "There are 127 studies with a diabetes focus across all platforms.
         42 on BDC, 38 on AnVIL, 29 on CRDC, 18 on KFDRC.

         Would you like to narrow by data type, or are you looking
         for something specific?"

User: "I need studies with whole genome sequencing."

[Artifact: PICOT card adds data requirement: WGS — shows in data context]
[Artifact: may now show Dataset Results alongside or below the card]

System: "Found 8 diabetes studies with WGS data. 5 are longitudinal
         cohorts. Would you like to see them?"

User: "Yes, show me."

[Artifact: Dataset Results — 8 studies in table]
```

### Example 3: Direct card editing (free text → concept mapping)

Slots are **free text fields** — the user types natural language and the system attempts to map it to known catalog concepts. This means we need to handle partial matches and misses gracefully.

```
[Artifact: PICOT card partially filled from earlier conversation]

User: (clicks the P slot on the PICOT card, changes "diabetes" to
       "Type 2 diabetes, adults, African American ancestry")

[System maps: "Type 2 diabetes" → Focus: Diabetes Mellitus, Type 2 ✓
              "adults" → Age range: 18+ (no catalog facet yet — stored
              in intent but not filterable)
              "African American ancestry" → no catalog facet yet — stored
              in intent but not filterable]

[Artifact: Dataset Results update — filtered by T2D focus + WGS]
[Chip bar shows: Focus: Diabetes Mellitus Type 2 (mapped ✓)
                 Adults (intent only, not filterable — dimmed chip)
                 African American ancestry (intent only — dimmed chip)]

System: "Narrowed to 12 studies matching T2D with WGS. Note: we don't
         yet have demographic filtering by age or ancestry — I've
         recorded these in your research plan but can't filter on them
         today. Both ACCORD and MESA include African American cohorts
         based on their study descriptions."
```

#### When concept mapping fails

| Scenario                                                               | Behavior                                                                                                           |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **Exact match**                                                        | Green chip, filters immediately                                                                                    |
| **Semantic match** (e.g., "heart disease" → "Cardiovascular Diseases") | Chip shows mapped term, tooltip shows user's original text                                                         |
| **Partial match** (e.g., "adults" — understood but not filterable)     | Dimmed/outline chip, stored in intent for future use                                                               |
| **No match** (e.g., "CRISPR editing data")                             | Amber chip with message: "No studies match 'CRISPR editing data' — try different terms or ask me what's available" |
| **Ambiguous** (e.g., "cancer" → 30+ specific cancer types)             | System asks: "There are 34 cancer-related focus areas — did you mean a specific type, or all cancer studies?"      |

---

## 8. Visual References

| Reference                   | What to look at                                     | Link                                           |
| --------------------------- | --------------------------------------------------- | ---------------------------------------------- |
| Claude.ai                   | Two-panel layout, artifact rendering, chat input    | claude.ai (log in)                             |
| BRC Analytics inside-out    | Kaspars's prototype — chat driving assemblies table | cc-design #296 Figma                           |
| BRC Analytics scenario flow | Chat → filtered list → workflow config              | cc-design #296 comments (Figma prototype link) |
| Current NCPI `/studies`     | The table + facet sidebar we're replacing           | ncpi-dataset-catalog.dev                       |
| Current NCPI `/chat`        | The chat POC being absorbed                         | ncpi-dataset-catalog.dev/chat                  |
| HCA Explorer AI UI          | Right-side chat panel, query builder                | cc-design #247 Figma                           |

---

## 9. Work Plan

Step-by-step breakdown. Each step is roughly a day of design work and produces a reviewable deliverable.

### Step 1: Layout + nav + empty state

**Deliverable**: The full Research Mode frame — site header with updated nav (Studies, Platforms, Data Dictionary, About in top bar; Research Mode entry point), two-panel layout below (icon sidebar, chat panel, artifact area), proportions, and the **empty state** before the user types anything.

**Decisions**: Where does Research Mode live in the nav? What does the artifact area show on a fresh conversation (blank PICOT card vs. welcome message vs. catalog stats)?

### Step 2: PICOT card + artifact transitions

**Deliverable**: The PICOT card in all five states (empty, filling, filled, ambiguous, over-constrained) with progressive slot reveal and inline editing. Plus the transitions between artifacts — how does the right panel move from Research Plan → Dataset Results → Study Detail and back? Answer Q1–Q5 from section 4.

**Decisions**: This is the core UX. How do slots reveal progressively? When does Plan auto-switch to Results? Can both be visible? How does the user navigate back? How do chat-applied and manual filters interact?

### Step 3: Dataset Results + chat panel + Study Detail

**Deliverable**: The Dataset Results table with column-header filter dropdowns (histogram, sort, select), chip bar (provenance, unresolved mentions, backoff banner). Chat message types (user, system, thinking indicator, slot-fill confirmations). Study Detail view (overview, demographics, publications, variables with PICOT coverage).

**Decisions**: Column filter dropdown layout. Chat-chip vs. manual-chip distinction. Study Detail: tabbed vs. scrolling sections.

### Step 4: Clickable prototype

**Deliverable**: Figma prototype linking steps 1–3 into a walkthrough of Example 1 (focused question → results → study drill-down) and Example 2 (exploratory start → gradual slot filling). Note reusable components for other CC sites (BRC Analytics, AnVIL, HCA).

---

## 10. Constraints & Notes

- **Alpha quality** — we're focused on recall over precision. The system may over-match. Design should communicate "here's what we found, let's refine" rather than "here are your exact results."
- **Response time** — the chat response takes ~4–5 seconds (LLM pipeline for intent extraction + dataset lookup). We need a "thinking" indicator in the chat panel during this time (e.g., animated dots, pulsing shimmer, or a status message like "Searching 2,944 studies..."). The PICOT card and artifact area should also show a loading/updating state while the response is in flight.
- **PICOT is invisible to most users** — they shouldn't need to know the acronym. The card should feel like a natural summary of their research question, not a medical framework they need to learn. Labels like "Population," "Exposure," "Outcome" are fine, but avoid jargon beyond that.
- **Slot filling is progressive** — don't show all 5 slots as empty form fields from the start. Consider revealing slots as they become relevant to the conversation.
- **The chat must never feel like a form** — the system asks natural questions, not "Please fill in the Comparator field." The PICOT card is a reflection of the conversation, not a form the conversation is filling out.
- **Design for reuse** — components should work across CC sites with different data models. The two-panel shell, intent card, column filters, and chip bar are all candidates for the shared component library.
