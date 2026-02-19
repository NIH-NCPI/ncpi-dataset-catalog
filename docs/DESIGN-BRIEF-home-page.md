# Design Brief: Home Page & Onboarding

> For: Kaspars | Status: DRAFT — Feb 2026
> Refs: [ROADMAP-chat-ux.md](ROADMAP-chat-ux.md) · [DESIGN-BRIEF-research-mode.md](DESIGN-BRIEF-research-mode.md) · cc-design #298 · cc-design #296

---

## 1. Context

The NCPI Dataset Catalog currently has no home page — `/` redirects to the Platforms list. A new user lands on a table of platforms with no explanation of what the site is, what data it contains, or what they can do. The `/chat` search POC exists but isn't linked from navigation.

We need a landing page that:

1. Tells the user what this is and what's here
2. Invites them into a research conversation (Research Mode)
3. Gives them a fallback path to browse directly (Search Mode)

This is Phase 1 — ships fast with no backend changes.

### What exists today

- **`/` → redirects to `/platforms`** — a table of the 4 NCPI platforms
- **`/studies`** — facet sidebar + studies table (2,944 studies)
- **`/chat`** — standalone chat POC (not linked in nav)
- **Header nav**: Data Dictionary, Visit ncpi-acc.org, GitHub, X, YouTube
- **No explanation anywhere** of what the catalog contains or how to use it

---

## 2. What We're Designing

A landing page on `/` that serves as the front door to both Research Mode and Search Mode.

### In scope

- Page layout and content hierarchy
- Hero section with chat input (primary CTA)
- "What's here" catalog summary
- Example research questions (clickable chips)
- Navigation to Search Mode (Studies/Platforms tables)
- Navigation to About page
- How the hero input transitions into Research Mode (connects to Q7 from the Research Mode brief)

### Out of scope

- About / methodology page content (separate brief)
- Research Mode layout itself (cc-design #298)
- The studies/platforms table pages (existing, unchanged)

---

## 3. Page Sections

### Hero: Research Input

The dominant element. A large chat input that invites the user into a **research intent-driven search** over NCPI and dbGaP datasets. This is the primary CTA — typing and submitting transitions the user into the Research Mode two-panel layout.

- **Headline**: something like "Research intent-driven search over NCPI datasets" or "What are you studying?" — communicate that this is smarter than keyword search
- **Chat input**: large text area, same styling as the Research Mode chat input so it feels continuous
- **Placeholder text**: e.g., "Describe your research question..." or "What population, exposure, or outcome are you interested in?"
- **Submit**: enter key or send button → transitions to Research Mode with the query pre-loaded as the first message

### Example Queries

Clickable chips below the hero input showing example research questions. Clicking one fills the input and transitions to Research Mode.

Examples (calibrated to what the catalog can actually answer today):

- "Diabetes studies with whole genome sequencing"
- "Pediatric cancer on KFDRC"
- "Cardiovascular cohorts with longitudinal follow-up"
- "Studies measuring blood pressure and BMI"
- "What data types are available for lung disease?"

These should be real queries that return useful results — not aspirational. We can rotate or randomize them.

### Catalog Summary ("What's Here")

Prominent counts that communicate scale and make the catalog feel tangible. These should be the first numbers the user sees — big, bold, near the hero:

- **4 platforms** (AnVIL, BDC, CRDC, KFDRC) — with logos
- **~2,944 studies** from NCPI and dbGaP
- **~X million participants**

These three numbers are the headline stats. Secondary details (65 data types, 15 study designs, 843 consent codes) can appear below or on hover.

This section answers "is this worth my time?" in 2 seconds and establishes that this is a cross-platform catalog spanning the NCPI ecosystem and dbGaP.

### How It Works (brief explainer)

A short paragraph or 3–4 bullet points explaining what makes this different from a keyword search:

- **Research intent-driven** — describe your research question in natural language and the system maps it to available data, metadata, demographics, and variables across the catalog
- **Optimized for recall over precision** — we surface more potential matches rather than fewer, so you don't miss relevant datasets. You can always narrow from there.
- **NCPI + dbGaP coverage** — searches across all four NCPI platforms and dbGaP study metadata, data types, study designs, consent codes, and (where available) variable-level annotations

This sets expectations: the system will cast a wide net and help you refine, rather than giving you 3 exact results. It also signals that the depth of matching varies — some studies have rich variable metadata, others only have study-level annotations.

### Mode Entry Points

Two clear paths below the hero:

1. **Research Mode** (already the hero CTA) — "Describe your research question and we'll find matching datasets"
2. **Search Mode** — "Or browse all studies directly" → links to `/studies`

Search Mode is the escape hatch for users who know exactly what they want or prefer manual filtering.

### Navigation Links

- **About** — link to the methodology/about page (how the data was collected, alpha disclaimer)
- **Data Dictionary** — existing link, keep it
- **Platforms** — brief mention of the 4 platforms, links to `/platforms`

---

## 4. The Hero-to-Research-Mode Transition

This is the key interaction and connects to Q7 from the Research Mode brief (cc-design #298).

When the user types a query in the hero input and submits:

**Option A: Route transition**

- Navigate to `/research` (or similar route) which renders the two-panel Research Mode layout
- The user's query is pre-loaded as the first chat message
- The system immediately starts processing (thinking indicator)
- Clean URL change, browser back button returns to home page

**Recommendation**: Option A — simplest and most predictable. The home page is a landing page, Research Mode is a workspace — they're different contexts and a route change communicates that clearly. Open to other proposals from Kaspars.

---

## 5. Visual References

| Reference                               | What to look at                                                        |
| --------------------------------------- | ---------------------------------------------------------------------- |
| **Claude.ai home**                      | Hero input with example prompts, transitions into chat                 |
| **ChatGPT home**                        | Similar pattern — input + example chips                                |
| **BRC Analytics home** (cc-design #296) | The "fancy" version with colorful input and entry into inside-out mode |
| **Hugging Face datasets**               | Stats summary + search input                                           |
| **Current NCPI `/studies`**             | What the user sees today (no home page)                                |

The Claude.ai and ChatGPT home pages are the closest references — both are "single input with examples" that transition into a two-panel workspace.

---

## 6. Conversation Example: Home → Research Mode

```
[Home page]
User sees: headline, large input, example chips, catalog stats

User clicks chip: "Cardiovascular cohorts with longitudinal follow-up"

[Transition: route change to /research]
[Research Mode: two-panel layout appears]
[Chat panel: "Cardiovascular cohorts with longitudinal follow-up" shown as first user message]
[System thinking indicator: 4-5 seconds]

[Artifact area: PICOT card fills]
  P: Cardiovascular diseases
  T: Longitudinal

[System responds in chat:]
"Found 89 cardiovascular studies with longitudinal design across all
 platforms. 34 are on BDC, 28 on AnVIL.

 Would you like to narrow by data type or specific condition
 (e.g., heart failure, atrial fibrillation, coronary artery disease)?"
```

---

## 7. Constraints & Notes

- **No backend changes** — this page uses only data we already have (study counts, platform counts, facet value counts). These can be pulled from the static catalog JSON at build time.
- **Example queries must work** — every chip should return meaningful results with the current search pipeline. Test them before shipping.
- **Alpha disclaimer** — include a subtle note that this is an alpha/preview. Could be a small banner or a line in the footer rather than something prominent that scares users away.
- **The input must not feel like a search box** — it's an invitation to describe a research question, not to type keywords. The placeholder text and examples should model natural language ("I'm studying..." not "diabetes WGS").
- **Keep it light** — this is a landing page, not a dashboard. One screen, minimal scrolling, fast to scan.

---

## 8. Work Plan

### Step 1: Layout + hero + stats

**Deliverable**: Page layout with hero section (headline, input, example chips) and catalog summary stats. Show the page in context with the site header (updated nav from Research Mode brief).

**Decisions**: Headline copy. How prominent are the stats? Above or below the fold?

### Step 2: Transition + mode entry

**Deliverable**: Show the hero-to-Research-Mode transition (pick from options A/B/C or propose alternative). Show the Search Mode entry point ("browse all studies"). Show what happens when clicking an example chip.

**Decisions**: Route change vs. in-place morph. How does the input animate or carry over into the chat panel?

### Step 3: Polish + responsive

**Deliverable**: Final layout with real copy, responsive behavior (what does this look like on a laptop vs. wide monitor?). Include the alpha disclaimer treatment.
