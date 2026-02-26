#!/usr/bin/env python3
"""Expand concept vocabulary with new phenotype categories and sub-concepts.

Scans v4 classification output for unclassified variables, groups them
by heuristic category, generates sub-concepts via Sonnet, and updates:

- concept-vocabulary.json (adds parent + sub-concept entries)
- concept-isa.json (adds parent → NCPI category + sub-concept → parent edges)

Does NOT re-tag study JSONs — the classifier handles that on re-run.

Usage:
    python expand_vocabulary.py                        # All categories
    python expand_vocabulary.py --category cancer      # Single category
    python expand_vocabulary.py --dry-run              # Show prompts only
    python expand_vocabulary.py --parents-only         # Add parents, skip sub-concepts
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Clear Claude Code sandbox proxy vars
for _proxy_var in ("ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)

import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR.parents[1] / ".env")

LLM_DIR = SCRIPT_DIR / "output" / "llm-concepts-v4"
VOCAB_PATH = SCRIPT_DIR / "output" / "concept-vocabulary.json"
ISA_PATH = SCRIPT_DIR / "output" / "concept-isa.json"

MODEL = "claude-sonnet-4-20250514"

# Max unique (name, description) pairs to send per category.
# Larger categories get sampled to stay within context limits.
MAX_SAMPLES_PER_CATEGORY = 2000


# ---------------------------------------------------------------------------
# Parent concept definitions
# ---------------------------------------------------------------------------


@dataclass
class ParentConcept:
    """Definition of a new parent concept to add to the vocabulary."""

    concept_id: str  # bare ID (gets topmed: prefix)
    name: str
    description: str
    domain: str
    ncpi_parent: str  # NCPI category this rolls up to
    pattern: re.Pattern  # heuristic for finding matching unclassified vars
    table_pattern: re.Pattern | None = None  # optional table name pattern
    min_subconcepts: int = 5
    max_subconcepts: int = 30


PARENT_CONCEPTS: list[ParentConcept] = [
    ParentConcept(
        concept_id="concomitant_medication",
        name="Concomitant Medications",
        description=(
            "General medication use including drug names, dosages, routes, "
            "frequencies, and therapeutic classes. Covers all medication types "
            "not specifically captured by narrower concepts like "
            "antihypertensive_medication or lipid_lowering_medication."
        ),
        domain="medications",
        ncpi_parent="ncpi:medications",
        pattern=re.compile(
            r"medication.use|taking.*med|drug.name|drug.dose|"
            r"prescription|pharmacy|concomitant|"
            r"anti-?(?:biotic|histamine|depressant|convulsant|psychotic|anxiety|"
            r"inflammatory|parkinson|coagul|ulcer)|"
            r"bronchodilator|sleeping.pill|eyedrop|"
            r"(?:beta|calcium.channel|ace).(?:blocker|inhibitor)|"
            r"diuretic|vasodilator|statin|insulin.(?:unit|dose)|"
            r"oral.(?:steroid|hypoglycemic|estrogen|glucocorticoid)|"
            r"sedative|hypnotic|thyroid.extract|"
            r"osteoporosis.med|bisphosphonate|raloxifene|calcitonin",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"concom|medic|pharma|drug",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="lung_ct_imaging",
        name="Lung CT Quantitative Imaging",
        description=(
            "Quantitative chest CT scan measurements including lung density "
            "in Hounsfield units (HU), percent emphysema, gas trapping, "
            "airway wall thickness and area, airway dimensions (Pi10), "
            "parametric response mapping (PRM), and lobar segmentation."
        ),
        domain="imaging",
        ncpi_parent="ncpi:imaging",
        pattern=re.compile(
            r"hounsfield|emphysema|gas.trapping|airway.wall|"
            r"air.trapping|lung.density|Pi10|"
            r"wall.area.percent|lumen|"
            r"parenchymal|CT.histogram|"
            r"(?:inspirat|expirat)ory.*(?:volume|density|percent)|"
            r"PRM.*(?:air|emph)|lobar|lobe.*(?:volume|density)",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"ct_air|lung_ct|airway|parenchym",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="polysomnography",
        name="Polysomnography",
        description=(
            "Sleep study measurements from polysomnography (PSG) including "
            "apnea-hypopnea index (AHI), oxygen desaturation (SpO2), "
            "arousal indices, sleep stage durations (NREM, REM), "
            "respiratory event counts, periodic limb movements, "
            "and EEG-derived sleep quality parameters."
        ),
        domain="sleep",
        ncpi_parent="ncpi:sleep",
        pattern=re.compile(
            r"apnea|hypopnea|AHI|arousal.*(?:hour|index|NREM|REM)|"
            r"(?:central|obstructive).apnea|desaturation|SpO2|"
            r"sleep.stage|NREM|REM.*(?:back|position|duration)|"
            r"periodic.limb|PLM|"
            r"(?:sleep|wake).*(?:efficiency|latency|onset)|"
            r"polysomnogra|PSG|"
            r"respiratory.disturbance|"
            r"EEG.*(?:sleep|spectral|power|delta|theta)",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"shhs|psg|polysom|sleep.*hhs",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="depression_anxiety_screening",
        name="Depression and Anxiety Screening",
        description=(
            "Standardized depression and anxiety screening instruments "
            "including CES-D (Center for Epidemiological Studies Depression), "
            "PHQ-9 (Patient Health Questionnaire), GAD-7, Beck Depression "
            "Inventory, SF-36 mental health subscales, and related "
            "item-level and summary scores."
        ),
        domain="mental_health",
        ncpi_parent="ncpi:mental_health",
        pattern=re.compile(
            r"CES-?D|PHQ-?[0-9]|GAD-?[0-9]|Beck.Depression|"
            r"depressed|depression.scale|"
            r"felt.hopeful|felt.fearful|felt.lonely|felt.sad|"
            r"crying.spell|bothered.by.things|shake.off.the.blues|"
            r"SF-?36.*mental|mental.health.index|"
            r"mental.component.scale|"
            r"emotional.problems.*(?:cut.down|accomplish)",
            re.IGNORECASE,
        ),
        min_subconcepts=3,
        max_subconcepts=15,
    ),
    ParentConcept(
        concept_id="psychiatric_interview",
        name="Structured Psychiatric Interview",
        description=(
            "Diagnostic psychiatric interview data from instruments "
            "like DIGS, CIDI, SCID, MINI, and NESARC/AUDADIS. Covers "
            "substance use disorders, mood disorders (bipolar, major "
            "depression), anxiety disorders, psychotic disorders, PTSD, "
            "ADHD, eating disorders, and personality disorders."
        ),
        domain="mental_health",
        ncpi_parent="ncpi:mental_health",
        pattern=re.compile(
            r"DIGS|CIDI|SCID|AUDADIS|"
            r"bipolar|schizophreni|psychotic|psychosis|"
            r"(?:substance|alcohol|drug).(?:use|abuse|depend)|"
            r"(?:panic|anxiety|phobic).disorder|"
            r"attention.deficit|ADHD|"
            r"(?:oppositional|conduct).disorder|"
            r"eating.disorder|anorexia|bulimia|"
            r"PTSD|post.traumatic|"
            r"obsessive.compulsive|"
            r"(?:antisocial|borderline|narcissistic).personality|"
            r"mania|manic.episode",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="cancer_diagnosis",
        name="Cancer Diagnosis and Screening",
        description=(
            "Cancer occurrence, type, histology, staging, and screening. "
            "Includes self-reported cancer history by site, cancer registry "
            "data (ICD-O morphology, behavior, grade, Gleason score), "
            "mammography, PSA testing, Pap smear, and colonoscopy screening."
        ),
        domain="disease_events",
        ncpi_parent="ncpi:disease_events",
        pattern=re.compile(
            r"cancer|neoplasm|tumor|tumour|malignant|carcinoma|"
            r"melanoma|lymphoma|leukemia|sarcoma|"
            r"(?:breast|lung|colon|prostate|ovarian|cervical|pancreatic|"
            r"bladder|kidney|liver|gastric|thyroid|brain).cancer|"
            r"mammogram|PSA.*(?:screen|test|blood)|"
            r"Pap.smear|colonoscopy.*screen|"
            r"ICD-?O|Gleason|histolog.*(?:grade|morphol)|"
            r"cancer.staging|TNM|"
            r"cancer.*in.situ",
            re.IGNORECASE,
        ),
        min_subconcepts=3,
        max_subconcepts=20,
    ),
    ParentConcept(
        concept_id="disease_diagnosis",
        name="Disease Diagnosis History",
        description=(
            "Non-cardiovascular, non-cancer disease diagnoses and medical "
            "history. Includes thyroid disease, arthritis (osteo, rheumatoid, "
            "gout), kidney disease, liver disease, gallbladder disease, "
            "seizure disorders, Parkinson's disease, asthma/COPD diagnosis, "
            "diabetes diagnosis, and other self-reported chronic conditions."
        ),
        domain="disease_events",
        ncpi_parent="ncpi:disease_events",
        pattern=re.compile(
            r"(?:doctor|physician).*(?:told|diagnos)|"
            r"ever.(?:been|had).*diagnos|"
            r"(?:thyroid|kidney|liver|gallbladder|lung|seizure|"
            r"parkinson|alzheimer|crohn|colitis|celiac|lupus|"
            r"rheumatoid|osteoarthritis|gout|asthma|COPD|"
            r"cirrhosis|hepatitis|pancreatitis|"
            r"multiple.sclerosis|epilepsy|"
            r"fibromyalgia|chronic.fatigue).(?:disease|disorder|history|diagnos)|"
            r"CDI:.*(?:disease|disorder)|"
            r"medical.history.*(?:disease|condition)|"
            r"ICD.(?:9|10)|"
            r"(?:prevalent|incident).(?:disease|condition)",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="ophthalmology",
        name="Ophthalmology Assessment",
        description=(
            "Eye examination findings and ophthalmologic measurements "
            "including visual acuity, intraocular pressure, slit-lamp "
            "findings, retinal exam (macular degeneration, diabetic "
            "retinopathy staging, drusen), cataract grading, glaucoma "
            "evaluation, corneal measurements, and fundus photography."
        ),
        domain="general_health",
        ncpi_parent="ncpi:general_health",
        pattern=re.compile(
            r"visual.acuity|intraocular.pressure|slit.lamp|"
            r"retin(?:al|opathy)|macular.degeneration|drusen|"
            r"cataract|glaucoma|cornea[l.]|fundus|"
            r"(?:right|left).eye|"
            r"lens.opacity|arcus.senilis|"
            r"iris.atrophy|pupil.reaction|"
            r"visual.field|color.vision|"
            r"optic.disc|cup.disc.ratio|"
            r"eye.exam|ophthalmol",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"ophthal|retina|areds|eye\d|_eye_",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="pregnancy_reproductive",
        name="Pregnancy and Reproductive Health",
        description=(
            "Reproductive health history including pregnancy count, "
            "outcomes, and complications (pre-eclampsia, gestational "
            "diabetes, miscarriage), menstrual history, age at menarche/"
            "menopause, contraception use, fertility/infertility, "
            "hysterectomy, hormone replacement therapy, and breastfeeding."
        ),
        domain="reproductive_health",
        ncpi_parent="ncpi:reproductive_health",
        pattern=re.compile(
            r"pregnan|menopaus|menstrual|menarche|"
            r"contracepti|oral.contraceptive|birth.control|"
            r"gestational|pre-?eclampsia|eclampsia|toxemia|"
            r"(?:live|still).birth|miscarriage|"
            r"number.of.(?:pregnanc|birth|deliver)|"
            r"hysterectomy|oophorectomy|"
            r"hormone.*(?:replac|therap)|HRT|"
            r"breastfeed|lactation|"
            r"fertili|infertili|"
            r"period.*stop|age.*period",
            re.IGNORECASE,
        ),
        min_subconcepts=3,
        max_subconcepts=15,
    ),
    ParentConcept(
        concept_id="proteomics_panel",
        name="Proteomics Panel",
        description=(
            "High-throughput protein measurements from platforms like "
            "SOMAscan (aptamer-based) and Olink (proximity extension "
            "assay). Measures hundreds to thousands of plasma proteins "
            "including cytokines, growth factors, enzymes, receptors, "
            "and structural proteins."
        ),
        domain="biomarkers",
        ncpi_parent="ncpi:biomarkers",
        pattern=re.compile(
            r"SOMAscan|aptamer|Olink|"
            r"(?:Citrated|EDTA|Heparin).plasma|"
            r"ubiquitin.*ligase|"
            r"interleukin.*receptor|"
            r"growth.factor.*(?:receptor|binding)|"
            r"metalloproteinase|"
            r"plasminogen.activator|"
            r"complement.(?:factor|component)",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"proapt|somascan|olink|proteom",
            re.IGNORECASE,
        ),
        min_subconcepts=5,
        max_subconcepts=40,
    ),
    ParentConcept(
        concept_id="brain_neuroimaging",
        name="Brain Neuroimaging",
        description=(
            "Brain MRI measurements including FreeSurfer-derived cortical "
            "thickness, surface area, and gray matter volume by region "
            "(Destrieux/Desikan atlas parcellations), subcortical volumes "
            "(hippocampus, amygdala, caudate, putamen, thalamus), white "
            "matter hyperintensities, total intracranial volume, and "
            "diffusion tensor imaging (DTI) metrics."
        ),
        domain="imaging",
        ncpi_parent="ncpi:imaging",
        pattern=re.compile(
            r"FreeSurfer|Destrieux|Desikan|"
            r"(?:cortical|cortex).*(?:thickness|volume|area)|"
            r"(?:gray|grey|white).matter|"
            r"hippocampu|amygdala|caudate|putamen|thalamus|"
            r"(?:lateral|third|fourth).ventricle|"
            r"intracranial.volume|"
            r"white.matter.hyper|"
            r"corpus.callosum|cerebellum|brain.stem|"
            r"sulc(?:us|i|al)|gyrus|gyri|"
            r"(?:mean|gaussian).curvature",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"mrbr|freesurfer|brain.*mri|neuroimag",
            re.IGNORECASE,
        ),
    ),
    ParentConcept(
        concept_id="pulmonary_function_detailed",
        name="Detailed Pulmonary Function Testing",
        description=(
            "Pulmonary function test parameters beyond basic spirometry "
            "(FEV1, FVC). Includes forced expiratory flow at 25%, 50%, "
            "75% of FVC (FEF25, FEF50, FEF75), peak expiratory flow "
            "(PEF), maximum mid-expiratory flow rate (MMEF/FEF25-75), "
            "diffusing capacity (DLCO), total lung capacity (TLC), "
            "residual volume (RV), and post-bronchodilator responses."
        ),
        domain="respiratory",
        ncpi_parent="ncpi:respiratory",
        pattern=re.compile(
            r"FEF.?(?:25|50|75)|peak.(?:expiratory|flow)|PEF|"
            r"mid.expiratory.flow|MMEF|FEF25-75|"
            r"DLCO|diffus(?:ing|ion).capacity|"
            r"total.lung.capacity|TLC|"
            r"residual.volume|"
            r"(?:vital|inspiratory).capacity|"
            r"post.(?:bronchodilator|albuterol)|"
            r"FEF.*best.effort",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"pft|pulmon|spirom|lung.func",
            re.IGNORECASE,
        ),
        min_subconcepts=3,
        max_subconcepts=10,
    ),
    ParentConcept(
        concept_id="metabolomics_lipidomics",
        name="Metabolomics and Lipidomics",
        description=(
            "Targeted and untargeted metabolomic and lipidomic profiling. "
            "Includes ceramides, sphingomyelins, phosphatidylcholines (PC), "
            "phosphatidylethanolamines (PE), diacylglycerols (DG), "
            "triacylglycerols (TAG/TG), acylcarnitines, cholesterol esters "
            "(CE), lysophospholipids, and other plasma metabolites measured "
            "by mass spectrometry."
        ),
        domain="biomarkers",
        ncpi_parent="ncpi:biomarkers",
        pattern=re.compile(
            r"ceramide|Cer\(|sphingomyelin|SM\(|"
            r"phosphatidylcholine|PC\(|"
            r"phosphatidylethanolamine|PE\(|"
            r"diacylglycerol|DG\(|"
            r"triacylglycerol|TAG\(|TG\(|"
            r"acylcarnitine|AC\(|"
            r"cholesterol.ester|CE\(|"
            r"lysophosph|LPC\(|LPE\(|"
            r"pmol/mL|nmol/mL|"
            r"metabolomi|lipidomic",
            re.IGNORECASE,
        ),
        table_pattern=re.compile(
            r"lipd|lipid.*profil|metabolom",
            re.IGNORECASE,
        ),
        min_subconcepts=3,
        max_subconcepts=15,
    ),
    ParentConcept(
        concept_id="bone_musculoskeletal",
        name="Bone Density and Musculoskeletal Health",
        description=(
            "Bone mineral density (BMD) by DEXA scan, fracture history "
            "and location, osteoporosis diagnosis and treatment, grip "
            "strength, joint replacement (knee, hip), kyphosis/scoliosis, "
            "back pain, musculoskeletal exam findings, and functional "
            "mobility assessments."
        ),
        domain="general_health",
        ncpi_parent="ncpi:general_health",
        pattern=re.compile(
            r"bone.(?:mineral|density)|BMD|DEXA|DXA|"
            r"fracture|broken.bone|"
            r"osteoporos|osteopenia|"
            r"(?:knee|hip|joint).replacement|"
            r"grip.strength|hand.grip|"
            r"kyphosis|scoliosis|"
            r"(?:knee|back|joint).pain|"
            r"arthritis.*(?:symptom|exam)|"
            r"musculoskeletal|connective.tissue|"
            r"(?:range|limit).*motion",
            re.IGNORECASE,
        ),
        min_subconcepts=3,
        max_subconcepts=15,
    ),
]


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class SubConceptDef(BaseModel):
    """A sub-concept category with its assigned variable names."""

    concept_id: str = Field(
        description="Short snake_case slug (e.g. 'breast_cancer', 'psg_respiratory')"
    )
    name: str = Field(description="Human-readable category name")
    description: str = Field(
        description=(
            "What this sub-concept covers — specific enough that a classifier "
            "reading only this description can decide if a variable matches."
        )
    )
    variables: list[str] = Field(
        description="Variable names assigned to this category (exact match from input)"
    )


class SubConceptTree(BaseModel):
    """LLM output: sub-concepts for a parent concept."""

    categories: list[SubConceptDef] = Field(
        description="Sub-concept categories with assigned variables"
    )

    @model_validator(mode="after")
    def validate_tree(self) -> SubConceptTree:
        """Check structural constraints."""
        ids = [c.concept_id for c in self.categories]
        if len(ids) != len(set(ids)):
            dupes = [x for x in ids if ids.count(x) > 1]
            msg = f"Duplicate concept_ids: {set(dupes)}"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a biomedical data cataloger creating a search navigation tree.

You will receive a list of (variable_name, description) pairs that belong to
a broad measurement category. Create sub-categories that a researcher could
use to drill down when searching for specific phenotypes.

Rules:
- Each category needs a short snake_case concept_id slug.
- Each category needs a human-readable name and a description that explains
  what it covers — be specific enough that an LLM reading ONLY the description
  can decide if a given variable belongs.
- Assign EVERY input variable to exactly one category.
- Use the variable's description (not just its name) to decide placement.
- Prefer categories that map to how researchers think about the domain.
- Merge tiny groups (< 5 variables); split very large ones.
- Return variable names EXACTLY as given (case-sensitive).
"""


def build_user_prompt(
    parent: ParentConcept,
    variables: list[dict],
) -> str:
    """Build the user prompt with variable list."""
    lines = [
        f"## Parent concept: `{parent.concept_id}` — {parent.name}\n",
        f"Description: {parent.description}\n",
        f"Sort these {len(variables)} variables into "
        f"{parent.min_subconcepts}-{parent.max_subconcepts} sub-categories.\n",
        "## Variables\n",
    ]
    for v in variables:
        lines.append(f"- **{v['name']}**: {v['description']}")
    lines.append(
        f"\n\nProduce {parent.min_subconcepts}-{parent.max_subconcepts} "
        "sub-categories. Remember:\n"
        "- Every variable must be assigned to exactly one category\n"
        "- Return variable names exactly as shown above"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Variable collection (heuristic-based for unclassified vars)
# ---------------------------------------------------------------------------


def collect_unclassified_variables(
    parent: ParentConcept,
) -> list[dict]:
    """Scan v4 output and collect unclassified variables matching the heuristic.

    Returns deduplicated variable list: [{name, description, table_name}]
    """
    seen: dict[tuple[str, str], dict] = {}  # (name_lower, desc_lower) → entry

    for path in sorted(LLM_DIR.glob("phs*.json")):
        with open(path) as f:
            data = json.load(f)
        for table in data.get("tables", []):
            table_name = table.get("table_name", "") or ""
            table_desc = table.get("description", "") or ""
            table_matches = (
                parent.table_pattern
                and parent.table_pattern.search(table_name + " " + table_desc)
            )
            for var in table.get("variables", []):
                if var.get("concept_id") is not None:
                    continue  # already classified
                name = var.get("name", "")
                desc = var.get("description", "")
                if not desc:
                    continue
                # Check if variable matches the heuristic
                text = f"{name} {desc}"
                if parent.pattern.search(text) or table_matches:
                    key = (name.lower(), desc.lower())
                    if key not in seen:
                        seen[key] = {
                            "name": name,
                            "description": desc,
                            "table_name": table_name,
                        }

    variables = sorted(seen.values(), key=lambda v: v["name"].lower())
    return variables


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def generate_subconcepts(
    parent: ParentConcept,
    dry_run: bool = False,
) -> list[SubConceptDef] | None:
    """Generate sub-concepts for one parent concept.

    Returns list of sub-concepts, or None if dry_run or no variables.
    """
    print(f"\n{'='*60}")
    print(f"Expanding: {parent.concept_id} — {parent.name}")
    print(f"NCPI parent: {parent.ncpi_parent}")
    print(f"{'='*60}\n")

    # Step 1: Collect variables
    variables = collect_unclassified_variables(parent)
    print(f"Found {len(variables)} unique unclassified variables matching heuristic")

    if not variables:
        print("No variables found — skipping")
        return None

    # Sample if too many
    if len(variables) > MAX_SAMPLES_PER_CATEGORY:
        # Take an even spread (every Nth)
        step = len(variables) / MAX_SAMPLES_PER_CATEGORY
        variables = [variables[int(i * step)] for i in range(MAX_SAMPLES_PER_CATEGORY)]
        print(f"Sampled down to {len(variables)} variables")

    # Step 2: Build prompt
    user_prompt = build_user_prompt(parent, variables)

    if dry_run:
        print(f"\n--- SYSTEM PROMPT ({len(SYSTEM_PROMPT)} chars) ---")
        print(SYSTEM_PROMPT[:500])
        print(f"\n--- USER PROMPT ({len(user_prompt)} chars, "
              f"{len(variables)} variables) ---")
        print(user_prompt[:3000])
        if len(user_prompt) > 3000:
            print(f"... ({len(user_prompt) - 3000} more chars)")
        return None

    # Step 3: Call LLM
    client = AsyncAnthropic(
        timeout=httpx.Timeout(1800.0, connect=10.0)
    )
    model = AnthropicModel(
        MODEL,
        provider=AnthropicProvider(anthropic_client=client),
    )
    agent = Agent(
        model,
        output_type=SubConceptTree,
        system_prompt=SYSTEM_PROMPT,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            max_tokens=32768,
            temperature=0.0,
        ),
    )

    print("Calling Sonnet to generate sub-concept tree...")
    result = await agent.run(user_prompt)
    tree = result.output

    print(f"Generated {len(tree.categories)} sub-categories")

    # Validate coverage
    input_names = {v["name"] for v in variables}
    assigned: set[str] = set()
    for cat in tree.categories:
        assigned.update(cat.variables)

    missing = input_names - assigned
    extra = assigned - input_names
    if missing:
        print(f"WARNING: {len(missing)} variables not assigned")
        for m in sorted(missing)[:5]:
            print(f"  {m}")
    if extra:
        print(f"WARNING: {len(extra)} variable names not in input (typos?)")
        for e in sorted(extra)[:5]:
            print(f"  {e}")

    # Summary
    for cat in sorted(tree.categories, key=lambda c: -len(c.variables)):
        print(f"  {cat.concept_id}: {cat.name} ({len(cat.variables)} vars)")

    return tree.categories


def write_vocab_and_isa(
    parents_with_subs: list[tuple[ParentConcept, list[SubConceptDef] | None]],
) -> None:
    """Write parent concepts and sub-concepts to vocabulary and ISA files."""
    # Load existing files
    with open(VOCAB_PATH) as f:
        vocab = json.load(f)
    with open(ISA_PATH) as f:
        isa = json.load(f)

    existing_vocab_ids = {e["concept_id"] for e in vocab}
    existing_isa_pairs = {(e["child"], e["parent"]) for e in isa}

    new_vocab = 0
    new_isa = 0

    for parent, subconcepts in parents_with_subs:
        parent_full_id = f"topmed:{parent.concept_id}"

        # Add parent to vocabulary (bare ID)
        if parent.concept_id not in existing_vocab_ids:
            vocab.append({
                "concept_id": parent.concept_id,
                "cui": None,
                "description": parent.description,
                "domain": parent.domain,
                "example_variables": [],
                "name": parent.name,
            })
            existing_vocab_ids.add(parent.concept_id)
            new_vocab += 1

        # Add parent → NCPI category ISA edge
        pair = (parent_full_id, parent.ncpi_parent)
        if pair not in existing_isa_pairs:
            isa.append({"child": parent_full_id, "parent": parent.ncpi_parent})
            existing_isa_pairs.add(pair)
            new_isa += 1

        # Add sub-concepts
        if subconcepts:
            for sub in subconcepts:
                sub_full_id = f"topmed:{parent.concept_id}_{sub.concept_id}"
                sub_bare_id = f"{parent.concept_id}_{sub.concept_id}"

                # Add to vocabulary
                if sub_bare_id not in existing_vocab_ids:
                    vocab.append({
                        "concept_id": sub_bare_id,
                        "cui": None,
                        "description": sub.description,
                        "domain": parent.domain,
                        "example_variables": sub.variables[:5],
                        "name": sub.name,
                    })
                    existing_vocab_ids.add(sub_bare_id)
                    new_vocab += 1

                # Add sub → parent ISA edge
                pair = (sub_full_id, parent_full_id)
                if pair not in existing_isa_pairs:
                    isa.append({"child": sub_full_id, "parent": parent_full_id})
                    existing_isa_pairs.add(pair)
                    new_isa += 1

    # Write files
    with open(VOCAB_PATH, "w") as f:
        json.dump(vocab, f, indent=2)
    with open(ISA_PATH, "w") as f:
        json.dump(isa, f, indent=2)

    print(f"\nWrote {new_vocab} vocabulary entries, {new_isa} ISA edges")
    total_concepts = len(existing_vocab_ids)
    total_isa = len(existing_isa_pairs)
    print(f"Total vocabulary: {total_concepts} concepts, {total_isa} ISA edges")


async def main_async(args: argparse.Namespace) -> None:
    """Run vocabulary expansion."""
    if args.category:
        targets = [p for p in PARENT_CONCEPTS if p.concept_id == args.category]
        if not targets:
            names = [p.concept_id for p in PARENT_CONCEPTS]
            print(f"Unknown category: {args.category}")
            print(f"Known: {names}")
            sys.exit(1)
    else:
        targets = PARENT_CONCEPTS

    results: list[tuple[ParentConcept, list[SubConceptDef] | None]] = []

    for parent in targets:
        if args.parents_only:
            print(f"\n{'='*60}")
            print(f"Adding parent: {parent.concept_id} — {parent.name}")
            print(f"NCPI parent: {parent.ncpi_parent}")
            print(f"{'='*60}")
            # Count matching variables for info
            variables = collect_unclassified_variables(parent)
            print(f"  {len(variables)} matching unclassified variables")
            results.append((parent, None))
        else:
            subconcepts = await generate_subconcepts(parent, dry_run=args.dry_run)
            results.append((parent, subconcepts))

    if not args.dry_run:
        write_vocab_and_isa(results)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Expand concept vocabulary with new phenotype categories"
    )
    parser.add_argument(
        "--category", type=str, help="Specific category to expand"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print prompts without calling LLM"
    )
    parser.add_argument(
        "--parents-only", action="store_true",
        help="Add parent concepts only, skip sub-concept generation"
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
