"""Extract seed concept data from TOPMed harmonized variable documentation.

Reads the 78 harmonized variable JSONs, cross-references component phv IDs
against parsed-tables.json (75K dbGaP variables), and produces:
  - topmed-seed-concepts.json: full seed reference with component variables
    (each tagged with role: measurement or covariate via R-code parsing)
  - concept-vocabulary.json: LLM matching vocabulary with example variables
    (measurement-role variables only)
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HARMONIZED_DIR = Path(__file__).parent.parent / (
    "source/harmonization-sources/topmed-harmonized/"
    "harmonized-variable-documentation"
)
PHS_MAPPING_FILE = Path(__file__).parent.parent / (
    "source/harmonization-sources/topmed-harmonized/phs-mapping.tsv"
)
PARSED_TABLES_FILE = Path(__file__).parent / "output/parsed-tables.json"
OUTPUT_DIR = Path(__file__).parent / "output"

# Regex to parse "phs000280.v4.pht004063.v2.phv00204712.v1"
DBGAP_ID_RE = re.compile(
    r"(phs\d+)\.v\d+\.(pht\d+)\.v\d+\.(phv\d+\.v\d+)"
)


def load_phs_mapping():
    """Load phs number -> study name mapping from TSV.

    Returns:
        dict mapping phs accession (e.g. "phs000280") to study name.
    """
    mapping = {}
    with open(PHS_MAPPING_FILE) as f:
        header = True
        for line in f:
            if header:
                header = False
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                phs_num = parts[0]
                study_name = parts[1]
                # Pad phs number to match dbGaP format: "280" -> "phs000280"
                mapping[f"phs{int(phs_num):06d}"] = study_name
    return mapping


def parse_component_variable(var_string):
    """Parse a component_study_variables string into phs/pht/phv parts.

    Args:
        var_string: e.g. "phs000280.v4.pht004063.v2.phv00204712.v1"

    Returns:
        Dict with phs, pht, phv keys, or None if parsing fails.
    """
    m = DBGAP_ID_RE.match(var_string)
    if not m:
        return None
    return {"phs": m.group(1), "pht": m.group(2), "phv": m.group(3)}


def _phv_base(phv_id):
    """Extract the base phv ID without version or participant suffix.

    Args:
        phv_id: e.g. "phv00054139.v1.p1" or "phv00054139.v1"

    Returns:
        Base ID like "phv00054139".
    """
    return phv_id.split(".")[0] if phv_id else ""


# ---------------------------------------------------------------------------
# R-code parsing: identify measurement vs covariate columns
# ---------------------------------------------------------------------------

# R built-ins and dplyr verbs to exclude from identifier extraction
_R_NOISE = frozenset({
    # R keywords / constants
    "TRUE", "FALSE", "NA", "NULL", "NaN", "Inf", "T", "F",
    "if", "else", "for", "while", "in", "function", "return",
    # Type conversions
    "as", "numeric", "integer", "character", "factor", "logical", "double",
    # Common base R functions
    "c", "abs", "mean", "sum", "max", "min", "length", "nrow", "ncol",
    "round", "floor", "ceiling", "log", "exp", "sqrt",
    "rowMeans", "colMeans", "rowSums", "cbind", "rbind", "ifelse",
    "paste", "paste0", "which", "is", "na", "rm", "nchar",
    "grepl", "gsub", "sub", "tolower", "toupper", "trimws",
    "apply", "lapply", "sapply", "mapply", "do", "call",
    "order", "sort", "unique", "duplicated", "match",
    "matrix", "array", "list", "vector",
    "stop", "warning", "message", "print", "cat",
    "seq", "rep", "rev", "append",
    # dplyr / tidyverse verbs
    "select", "mutate", "filter", "transmute", "rename", "summarise",
    "group_by", "ungroup", "arrange", "slice", "distinct", "pull",
    "inner_join", "left_join", "right_join", "full_join", "anti_join",
    "mutate_if", "mutate_at", "mutate_all", "vars", "funs",
    # Data frame identifiers commonly used in harmonization code
    "dataset", "dat", "dat1", "dat2", "dat3", "data", "df",
    "source_data", "phen_list", "harmonized_data",
    "tbl_df", "tibble", "data.frame",
    # Always-excluded output columns
    "topmed_subject_id",
    # Packages
    "dplyr", "magrittr", "plyr", "tidyr", "library", "require",
})


def _extract_expression_text(r_code, start):
    """Extract text of an R expression starting at a given position.

    Scans forward, tracking balanced parentheses/brackets, and stops at:
    - A comma or closing delimiter at depth 0 (end of sub-expression)
    - A newline at depth 0 where neither the current line ends with a
      pipe operator nor the next non-comment line starts with one

    Args:
        r_code: Full R source code string.
        start: Character position to start scanning from.

    Returns:
        Extracted expression text.
    """
    depth = 0
    i = start
    while i < len(r_code):
        ch = r_code[i]
        if ch in ("(", "[", "{"):
            depth += 1
        elif ch in (")", "]", "}"):
            if depth == 0:
                return r_code[start:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return r_code[start:i]
        elif ch == "\n" and depth == 0:
            # Find current line (from last newline to here)
            prev_nl = r_code.rfind("\n", start, i)
            line_start = (prev_nl + 1) if prev_nl != -1 else start
            current_line = r_code[line_start:i].rstrip()
            if current_line.endswith("%>%") or current_line.endswith("%<>%"):
                i += 1
                continue
            # Check if next non-comment line starts with pipe
            rest = r_code[i + 1:]
            rest_stripped = rest.lstrip()
            while rest_stripped.startswith("#"):
                nl = rest_stripped.find("\n")
                if nl == -1:
                    break
                rest_stripped = rest_stripped[nl + 1:].lstrip()
            if rest_stripped.startswith("%>%") or rest_stripped.startswith("+"):
                i += 1
                continue
            return r_code[start:i]
        i += 1
    return r_code[start:]


def _extract_r_identifiers(text):
    """Extract R identifiers from an expression, filtering out noise.

    Args:
        text: R expression text.

    Returns:
        Set of identifier strings that may be column names.
    """
    tokens = set(re.findall(r"\b([a-zA-Z][a-zA-Z0-9_.]*)\b", text))
    return tokens - _R_NOISE


def _extract_concept_assignment_idents(concept_id, r_code):
    """Find identifiers in the RHS of assignments to concept_id.

    Handles three R patterns:
    - mutate/transmute: concept_id = <expr>
    - Direct assignment: $concept_id <- <expr>
    - Indexed assignment: $concept_id[...] <- <expr>

    Args:
        concept_id: The concept variable name (e.g. "cac_score").
        r_code: Full R harmonization function source.

    Returns:
        Set of identifiers found in RHS expressions, or empty set.
    """
    idents = set()
    esc = re.escape(concept_id)

    # Pattern 1: concept_id = <expr> (in mutate/transmute/rename)
    for m in re.finditer(rf"\b{esc}\s*=\s*", r_code):
        rhs_text = _extract_expression_text(r_code, m.end())
        idents.update(_extract_r_identifiers(rhs_text))

    # Pattern 2: $concept_id <- <expr>
    for m in re.finditer(rf"\${esc}\s*<-\s*", r_code):
        rhs_text = _extract_expression_text(r_code, m.end())
        idents.update(_extract_r_identifiers(rhs_text))

    # Pattern 3: $concept_id[...] <- <expr>
    for m in re.finditer(rf"\${esc}\s*\[.*?\]\s*<-\s*", r_code):
        rhs_text = _extract_expression_text(r_code, m.end())
        idents.update(_extract_r_identifiers(rhs_text))

    # Pattern 4: names(X)[names(X) %in% "old_name"] <- "concept_id"
    # Base R column rename: extract old_name from the %in% clause
    for m in re.finditer(
        rf'%in%\s*"(\w+)"[^"]*<-\s*"{esc}"', r_code
    ):
        idents.add(m.group(1))

    return idents


def _find_assignment_sources(ident, r_code):
    """Find identifiers on the RHS of assignments to a given variable.

    Args:
        ident: Variable name to look for assignments to.
        r_code: Full R source code.

    Returns:
        Set of identifiers found in RHS of assignments to ident.
    """
    sources = set()
    esc = re.escape(ident)

    # word boundary assignment: ident = <expr> or ident <- <expr>
    for m in re.finditer(rf"\b{esc}\s*(?:<-|=)\s*", r_code):
        rhs_text = _extract_expression_text(r_code, m.end())
        sources.update(_extract_r_identifiers(rhs_text))

    # $ prefix assignment: $ident <- <expr>
    for m in re.finditer(rf"\${esc}\s*<-\s*", r_code):
        rhs_text = _extract_expression_text(r_code, m.end())
        sources.update(_extract_r_identifiers(rhs_text))

    return sources


def parse_measurement_columns(concept_id, r_code, known_var_names):
    """Parse R harmonization code to identify measurement column names.

    Traces from the concept assignment backward through intermediate
    variables (up to 5 levels) to find which source columns (identified
    by known_var_names from component phvs) feed into the concept.

    Args:
        concept_id: The concept variable name (e.g. "cac_score").
        r_code: The R harmonization function source code.
        known_var_names: Set of variable names from this unit's component phvs.

    Returns:
        Set of variable names identified as measurements, or None if
        parsing fails (no concept assignment found or no matches).
    """
    if not r_code or not known_var_names:
        return None

    measurement_names = set()

    # Step 1: Find identifiers directly used in the concept assignment
    direct_idents = _extract_concept_assignment_idents(concept_id, r_code)

    if direct_idents:
        # Step 2: Check which known variable names appear directly
        measurement_names = direct_idents & known_var_names

        # Step 3: If no direct matches, trace through intermediate variables
        if not measurement_names:
            remaining = direct_idents - known_var_names
            for _ in range(5):  # max 5 levels of indirection
                if not remaining:
                    break
                next_idents = set()
                for ident in remaining:
                    upstream = _find_assignment_sources(ident, r_code)
                    next_idents.update(upstream)

                new_matches = next_idents & known_var_names
                measurement_names.update(new_matches)

                remaining = next_idents - known_var_names - measurement_names
                if measurement_names:
                    break

    # Step 4: Broad scan fallback — find known names anywhere in the R code
    # and classify based on whether they appear in age/covariate context
    if not measurement_names:
        measurement_names = _broad_scan_measurement_names(
            concept_id, r_code, known_var_names
        )

    # Step 5: Pass-through detection — if a known variable name matches the
    # concept_id exactly, it passes through the R code untouched as the
    # measurement column (e.g. column "current_smoker_baseline" in a table
    # where the concept is also "current_smoker_baseline")
    if not measurement_names and concept_id in known_var_names:
        measurement_names = {concept_id}

    # Final filter: backward tracing can pick up covariates that are
    # carried alongside measurements (e.g. age in a subset() call).
    # Remove any names that appear in age/covariate assignment context.
    if measurement_names:
        covariate_names = _find_covariate_names(r_code, known_var_names)
        measurement_names -= covariate_names

    return measurement_names if measurement_names else None


def _find_covariate_names(r_code, known_var_names):
    """Identify known variable names that appear in age/covariate context.

    Extracts specific identifiers from age-assignment patterns (rename,
    mutate, names() rename) rather than broad context scanning.  This
    avoids false positives where unrelated variable names happen to appear
    in the same rename() call as an age assignment.

    Args:
        r_code: Full R harmonization function source.
        known_var_names: Set of variable names from component phvs.

    Returns:
        Set of known variable names that are covariates.
    """
    covariate_names = set()

    # Pattern 1: age = <identifier> (in mutate, transmute, or rename)
    # Extracts only the RHS identifier, not surrounding context
    for m in re.finditer(r"\bage\s*=\s*(\w+)", r_code):
        ident = m.group(1)
        if ident in known_var_names:
            covariate_names.add(ident)

    # Pattern 2: $age <- <expr>  (direct assignment)
    for m in re.finditer(r"\$age\s*<-\s*", r_code):
        rhs_text = _extract_expression_text(r_code, m.end())
        for name in known_var_names:
            if re.search(rf"\b{re.escape(name)}\b", rhs_text):
                covariate_names.add(name)

    # Pattern 3: names(X)[names(X) %in% "old_name"] <- "age"
    # Extracts old_name from %in% clause when new name is "age"
    for m in re.finditer(r'%in%\s*"(\w+)"[^"]*<-\s*"age"', r_code):
        ident = m.group(1)
        if ident in known_var_names:
            covariate_names.add(ident)

    # Pattern 4: subcohort = <identifier> (rename of subcohort covariate)
    for m in re.finditer(r"\bsubcohort\s*=\s*(\w+)", r_code):
        ident = m.group(1)
        if ident in known_var_names:
            covariate_names.add(ident)

    return covariate_names


def _broad_scan_measurement_names(concept_id, r_code, known_var_names):
    """Fallback: scan entire R function for known variable names.

    Finds all known variable names mentioned anywhere in the R code, then
    classifies names in age-assignment context as covariates. The rest
    are presumed measurements.

    Args:
        concept_id: The concept variable name.
        r_code: Full R harmonization function source.
        known_var_names: Set of variable names from component phvs.

    Returns:
        Set of measurement names, or None if scan finds nothing useful.
    """
    found_names = set()
    for name in known_var_names:
        if re.search(rf"\b{re.escape(name)}\b", r_code):
            found_names.add(name)

    if not found_names:
        return None

    covariate_names = _find_covariate_names(r_code, known_var_names)
    measurement_names = found_names - covariate_names
    return measurement_names if measurement_names else None


def _heuristic_role(comp, concept_id):
    """Fallback heuristic to classify a variable as measurement or covariate.

    Used when R-code parsing fails or is unavailable for a harmonization
    unit. Checks variable name and description for common covariate
    patterns (age, date, consent).

    Args:
        comp: Component variable dict with variable_name, variable_description.
        concept_id: The concept this variable is listed under.

    Returns:
        "measurement" or "covariate".
    """
    desc = (comp.get("variable_description") or "").lower()
    name = (comp.get("variable_name") or "").lower()

    # Age concepts are fine if the concept is actually about age
    age_concepts = {"cad_followup_start_age", "vte_followup_start_age",
                    "age_at_index"}

    if concept_id not in age_concepts:
        if any(p in desc for p in ("age at", "age when", "age of",
                                   "calculated age")):
            return "covariate"
        if name in ("age1", "age2", "age3", "age_baseline", "agebl"):
            return "covariate"

    # Date/time covariates
    if any(p in desc for p in ("date of test", "days since", "days from",
                               "days enrollment", "number of days")):
        return "covariate"
    if name in ("studydat",):
        return "covariate"

    # Consent/admin covariates
    if name == "consent" and concept_id not in ("subcohort",):
        return "covariate"

    return "measurement"


def tag_variable_roles(concepts):
    """Tag each component variable with role: measurement or covariate.

    For each harmonization unit, parses the R code to identify which
    source columns feed into the concept variable (measurements) vs
    covariates (age, dates, etc.). Falls back to heuristic if parsing
    fails.

    Args:
        concepts: List of concept dicts (mutated in place). Each must
            have component_variables with variable_name set and
            _unit_r_codes with per-unit R code.

    Returns:
        Tuple of (units_parsed, units_fallback) counts.
    """
    units_parsed = 0
    units_fallback = 0

    for concept in concepts:
        concept_id = concept["concept_id"]
        unit_r_codes = concept.get("_unit_r_codes", {})

        # Group component variables by unit_name
        by_unit = defaultdict(list)
        for comp in concept["component_variables"]:
            by_unit[comp.get("_unit_name", "")].append(comp)

        for unit_name, unit_vars in by_unit.items():
            r_code = unit_r_codes.get(unit_name, "")

            # Build set of known variable names for this unit
            unit_var_names = {
                comp["variable_name"]
                for comp in unit_vars
                if comp.get("variable_name")
            }

            # Attempt R-code parsing
            measurement_names = parse_measurement_columns(
                concept_id, r_code, unit_var_names
            )

            if measurement_names is not None:
                units_parsed += 1
                for comp in unit_vars:
                    name = comp.get("variable_name", "")
                    comp["role"] = (
                        "measurement" if name in measurement_names
                        else "covariate"
                    )
            else:
                units_fallback += 1
                for comp in unit_vars:
                    comp["role"] = _heuristic_role(comp, concept_id)

    return units_parsed, units_fallback


def build_phv_lookup(parsed_tables):
    """Build a lookup from phv base ID -> (variable_name, variable_description).

    Harmonized variable JSONs reference specific phv versions (e.g.
    "phv00023194.v3") while parsed-tables.json may have different versions
    (e.g. "phv00023194.v7.p16"). We match on the base phv ID only since
    the variable identity is stable across versions.

    Args:
        parsed_tables: Parsed content of parsed-tables.json.

    Returns:
        Dict mapping base phv ID to (name, description) tuple.
    """
    lookup = {}
    for table in parsed_tables:
        for var in table.get("variables", []):
            raw_id = var.get("id", "")
            base = _phv_base(raw_id)
            if base.startswith("phv"):
                lookup[base] = (
                    var.get("name", ""),
                    var.get("description", ""),
                )
    return lookup


def derive_concept_name(concept_id, description):
    """Derive a human-readable concept name from concept_id and description.

    Uses the first sentence of the description if short enough, otherwise
    title-cases the concept_id.

    Args:
        concept_id: e.g. "bp_systolic"
        description: Full description text.

    Returns:
        Human-readable name string.
    """
    # Map of known concept_id prefixes to readable names
    name_overrides = {
        "annotated_sex": "Annotated Sex",
        "age_at_index": "Age at Index",
        "bmi": "Body Mass Index (BMI)",
        "current_smoker": "Current Smoker Status",
        "ever_smoker": "Ever Smoker Status",
        "height": "Standing Height",
        "weight": "Body Weight",
        "race": "Race",
        "hispanic_or_latino": "Hispanic or Latino Ethnicity",
    }
    if concept_id in name_overrides:
        return name_overrides[concept_id]

    # For most concepts, title-case the concept_id with underscores as spaces
    # e.g. "bp_systolic" -> "Bp Systolic" -> fix common abbreviations
    name = concept_id.replace("_", " ").title()
    # Fix common abbreviations
    abbrevs = {
        "Bp ": "Blood Pressure - ",
        "Hdl": "HDL",
        "Ldl": "LDL",
        "Vte": "VTE",
        "Wbc": "WBC",
        "Rbc": "RBC",
        "Mcv": "MCV",
        "Mch": "MCH",
        "Mchc": "MCHC",
        "Rdw": "RDW",
        "Mpv": "MPV",
        "Pmv": "PMV",
        "Crp": "CRP",
        "Hba1C": "HbA1c",
        "Cac": "CAC",
        "Cabg": "CABG",
        "Vte ": "VTE ",
        "Il6": "IL-6",
        "Il 6": "IL-6",
        "Icam1": "ICAM-1",
        "Cimt": "CIMT",
        "Ncnc Bld": "(Number Concentration in Blood)",
        "Mcnc Bld": "(Mass Concentration in Blood)",
        "Entmass Bld": "(Mass per Entity in Blood)",
        "Entvol Bld": "(Volume per Entity in Blood)",
        "Vfr Bld": "(Volume Fraction in Blood)",
    }
    for pattern, replacement in abbrevs.items():
        name = name.replace(pattern, replacement)
    return name


def extract_concepts():
    """Extract seed concepts from all harmonized variable JSON files.

    Returns:
        List of concept dicts with component variables.
    """
    phs_mapping = load_phs_mapping()
    concepts = []

    json_files = sorted(HARMONIZED_DIR.rglob("*.json"))
    if not json_files:
        print(f"ERROR: No JSON files found in {HARMONIZED_DIR}", file=sys.stderr)
        sys.exit(1)

    for json_path in json_files:
        with open(json_path) as f:
            data = json.load(f)

        concept_id = data["phenotype_concept"]
        description = data.get("description", "")
        measurement_units = data.get("measurement_units")
        domain = json_path.parent.name  # parent directory = domain

        # Extract UMLS CUI
        cui = None
        for cv in data.get("controlled_vocabulary", []):
            if cv.get("source") == "UMLS":
                cui = cv["id"]
                break

        # Extract component variables from all harmonization units,
        # storing per-unit R code for later role tagging
        component_variables = []
        unit_r_codes = {}
        for unit in data.get("harmonization_units", []):
            study_name = unit["name"]
            r_code = unit.get("harmonization_function", "")
            unit_r_codes[study_name] = r_code
            for var_str in unit.get("component_study_variables", []):
                parsed = parse_component_variable(var_str)
                if parsed:
                    # Try phs_mapping first, fall back to harmonization unit name
                    resolved_study = phs_mapping.get(parsed["phs"], study_name)
                    component_variables.append(
                        {
                            "phv": parsed["phv"],
                            "phs": parsed["phs"],
                            "pht": parsed["pht"],
                            "study_name": resolved_study,
                            "_unit_name": study_name,
                        }
                    )

        concepts.append(
            {
                "concept_id": concept_id,
                "description": description,
                "cui": cui,
                "domain": domain,
                "measurement_units": measurement_units,
                "component_variables": component_variables,
                "_unit_r_codes": unit_r_codes,
            }
        )

    return concepts


def enrich_with_parsed_tables(concepts, phv_lookup):
    """Add variable_name and variable_description from parsed-tables.json.

    Args:
        concepts: List of concept dicts (mutated in place).
        phv_lookup: Dict mapping phv ID to (name, description).

    Returns:
        Count of matched and unmatched phv IDs.
    """
    matched = 0
    unmatched = 0
    for concept in concepts:
        for comp in concept["component_variables"]:
            phv = _phv_base(comp["phv"])
            if phv in phv_lookup:
                name, desc = phv_lookup[phv]
                comp["variable_name"] = name
                comp["variable_description"] = desc
                matched += 1
            else:
                unmatched += 1
    return matched, unmatched


def _score_example_relevance(concept_id, variable_name, variable_description):
    """Score how relevant a component variable is as an example for its concept.

    Prefers variables whose name/description clearly relate to the concept,
    filtering out generic covariates (age, visit, consent) that happen to
    be co-referenced in harmonization units.

    Args:
        concept_id: e.g. "bp_systolic"
        variable_name: e.g. "SBPA21"
        variable_description: e.g. "SITTING SYSTOLIC BLOOD PRESSURE"

    Returns:
        Integer score (higher = more relevant).
    """
    desc_lower = variable_description.lower()
    name_lower = variable_name.lower()

    # Penalize generic covariates that are not about the concept itself
    generic_terms = ("age", "visit", "exam", "consent", "gender", "sex", "race")
    concept_lower = concept_id.lower()
    concept_keywords = set(concept_lower.replace("_", " ").split())
    for term in generic_terms:
        if term in name_lower or desc_lower.startswith(term):
            if term not in concept_lower:
                # Concept isn't about this term at all — penalize
                return -1
            # Concept IS about this term (e.g. "vte_followup_start_age" contains "age").
            # For compound concepts (3+ keywords), the example should demonstrate the
            # SPECIFIC kind, not just the generic term.  Require the variable to mention
            # at least one distinguishing keyword from the concept_id.
            # e.g. for vte_followup_start_age: need "vte" or "followup" in the description.
            # For simple concepts (1-2 keywords like annotated_sex, race_us), the generic
            # term IS the concept — no further check needed.
            stop_words = {"at", "of", "in", "the", "and", "or", "to", "a"}
            distinguishing = concept_keywords - {term} - stop_words
            if len(distinguishing) >= 2:
                has_distinguishing = any(
                    kw in desc_lower or kw in name_lower for kw in distinguishing
                )
                if not has_distinguishing:
                    return -1

    # Build keywords from concept_id: "bp_systolic" -> ["bp", "systolic"]
    keywords = concept_id.lower().replace("_", " ").split()

    score = 0
    for kw in keywords:
        if kw in desc_lower:
            score += 2
        if kw in name_lower:
            score += 1

    return score


def build_concept_vocabulary(concepts):
    """Build the LLM matching vocabulary from enriched seed concepts.

    Selects 2-3 example variables per concept. Expects component_variables
    to contain only measurements (covariates already stripped by
    _prepare_for_output).

    Args:
        concepts: List of enriched concept dicts.

    Returns:
        List of vocabulary entry dicts.
    """
    vocabulary = []
    for concept in concepts:
        candidates = []
        seen_names = set()
        for comp in concept["component_variables"]:
            vname = comp.get("variable_name", "")
            vdesc = comp.get("variable_description", "")
            if vname and vdesc and vname not in seen_names:
                score = _score_example_relevance(
                    concept["concept_id"], vname, vdesc
                )
                candidates.append((score, vname, vdesc))
                seen_names.add(vname)

        # Sort by relevance score descending, pick top 3 with non-negative scores
        candidates.sort(key=lambda x: x[0], reverse=True)
        examples = [f"{c[1]}: {c[2]}" for c in candidates[:3] if c[0] >= 0]

        vocabulary.append(
            {
                "concept_id": concept["concept_id"],
                "name": derive_concept_name(
                    concept["concept_id"], concept["description"]
                ),
                "description": concept["description"],
                "cui": concept["cui"],
                "domain": concept["domain"],
                "example_variables": examples,
            }
        )

    return vocabulary


def _prepare_for_output(concepts):
    """Strip covariates and internal fields before writing JSON output.

    Only measurement-role variables are kept in component_variables.
    The classifier receives measurements only and does not need to
    know about roles.

    Args:
        concepts: List of concept dicts (mutated in place).
    """
    for concept in concepts:
        concept.pop("_unit_r_codes", None)
        concept["component_variables"] = [
            comp for comp in concept["component_variables"]
            if comp.get("role") == "measurement"
        ]
        for comp in concept["component_variables"]:
            comp.pop("_unit_name", None)
            comp.pop("role", None)


def main():
    """Run the full extraction pipeline."""
    print("Step 1: Extracting concepts from harmonized variable JSONs...")
    concepts = extract_concepts()
    total_components = sum(len(c["component_variables"]) for c in concepts)
    all_studies = set()
    for c in concepts:
        for comp in c["component_variables"]:
            all_studies.add(comp["study_name"])

    print(f"  Found {len(concepts)} concepts, {total_components} component variables")
    print(f"  Across {len(all_studies)} studies")

    print("\nStep 2: Loading parsed-tables.json for cross-reference...")
    with open(PARSED_TABLES_FILE) as f:
        parsed_tables = json.load(f)
    print(f"  Loaded {len(parsed_tables)} tables")

    phv_lookup = build_phv_lookup(parsed_tables)
    print(f"  Built lookup with {len(phv_lookup)} unique phv IDs")

    print("\nStep 3: Enriching component variables with names/descriptions...")
    matched, unmatched = enrich_with_parsed_tables(concepts, phv_lookup)
    print(f"  Matched: {matched}, Unmatched: {unmatched}")

    print("\nStep 4: Tagging variable roles via R-code parsing...")
    units_parsed, units_fallback = tag_variable_roles(concepts)
    total_units = units_parsed + units_fallback
    parse_rate = units_parsed / total_units * 100 if total_units > 0 else 0
    print(f"  R-code parsed: {units_parsed}/{total_units} units ({parse_rate:.1f}%)")
    print(f"  Heuristic fallback: {units_fallback} units")

    # Count roles
    n_measurement = sum(
        1 for c in concepts for v in c["component_variables"]
        if v.get("role") == "measurement"
    )
    n_covariate = sum(
        1 for c in concepts for v in c["component_variables"]
        if v.get("role") == "covariate"
    )
    concepts_with_measurement = sum(
        1 for c in concepts
        if any(v.get("role") == "measurement" for v in c["component_variables"])
    )
    print(f"  Measurements: {n_measurement}, Covariates: {n_covariate}")
    print(f"  Concepts with >=1 measurement: {concepts_with_measurement}/{len(concepts)}")

    # Build stats
    stats = {
        "total_concepts": len(concepts),
        "total_component_variables": total_components,
        "total_studies": len(all_studies),
        "cross_reference_matched": matched,
        "cross_reference_unmatched": unmatched,
        "role_tagging": {
            "units_parsed_via_r_code": units_parsed,
            "units_heuristic_fallback": units_fallback,
            "parse_success_rate": round(parse_rate, 1),
            "measurement_variables": n_measurement,
            "covariate_variables": n_covariate,
        },
    }

    # Strip covariates and internal fields — only measurements go to output
    _prepare_for_output(concepts)

    # Write seed concepts
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seed_path = OUTPUT_DIR / "topmed-seed-concepts.json"
    with open(seed_path, "w") as f:
        json.dump({"concepts": concepts, "stats": stats}, f, indent=2)
    print(f"\nWrote {seed_path}")

    # Build and write concept vocabulary (measurement-role only for examples)
    print("\nStep 5: Building concept vocabulary for LLM matching...")
    vocabulary = build_concept_vocabulary(concepts)
    vocab_path = OUTPUT_DIR / "concept-vocabulary.json"
    with open(vocab_path, "w") as f:
        json.dump(vocabulary, f, indent=2)
    print(f"Wrote {vocab_path}")

    # Summary
    concepts_with_examples = sum(
        1 for v in vocabulary if len(v["example_variables"]) > 0
    )
    print(f"\n--- Summary ---")
    print(f"Concepts: {len(concepts)}")
    print(f"Component variables: {total_components}")
    print(f"  Measurements: {n_measurement}, Covariates: {n_covariate}")
    print(f"Studies: {len(all_studies)}")
    print(f"Cross-ref matched: {matched}/{total_components}")
    print(f"R-code parse rate: {parse_rate:.1f}% ({units_parsed}/{total_units} units)")
    print(f"Concepts with >=1 measurement: {concepts_with_measurement}/{len(concepts)}")
    print(f"Concepts with example variables: {concepts_with_examples}/{len(concepts)}")


if __name__ == "__main__":
    main()
