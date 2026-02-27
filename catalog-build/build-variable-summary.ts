import fs from "fs";
import path from "path";
import {
  Variable,
  VariableCategory,
  VariableSummary,
} from "../app/apis/catalog/ncpi-catalog/common/entities";

// Types for input data files (snake_case matches JSON)
interface NCPICategoryRaw {
  concept_id: string;
  description: string;
  name: string;
}

interface ConceptIsaEntryRaw {
  child: string;
  parent: string;
}

interface LLMVariableRaw {
  concept_id: string | null;
  confidence: string;
  description: string;
  id: string;
  name: string;
  source: string;
}

interface LLMTableRaw {
  datasetId: string;
  description: string | null;
  tableName: string;
  variables: LLMVariableRaw[];
}

interface LLMStudyDataRaw {
  studyId: string;
  studyName: string;
  tables: LLMTableRaw[];
}

// Internal types (camelCase)
interface NCPICategory {
  conceptId: string;
  description: string;
  name: string;
}

// Threshold for showing individual variables vs just counts
const VARIABLE_DETAIL_THRESHOLD = 200;

/**
 * Loads NCPI categories from ncpi-categories.json.
 * @param categoriesPath - Path to ncpi-categories.json.
 * @returns Map of category ID to category info.
 */
function loadCategories(categoriesPath: string): Map<string, NCPICategory> {
  const categories = new Map<string, NCPICategory>();
  if (!fs.existsSync(categoriesPath)) {
    console.log(`Warning: ${categoriesPath} not found`);
    return categories;
  }
  const data = JSON.parse(fs.readFileSync(categoriesPath, "utf-8")) as NCPICategoryRaw[];
  for (const cat of data) {
    categories.set(cat.concept_id, {
      conceptId: cat.concept_id,
      description: cat.description,
      name: cat.name,
    });
  }
  return categories;
}

/**
 * Loads concept ISA relationships and builds a child-to-parent map.
 * @param isaPath - Path to concept-isa.json.
 * @returns Map of child concept ID to parent concept ID.
 */
function loadConceptIsa(isaPath: string): Map<string, string> {
  const childToParent = new Map<string, string>();
  if (!fs.existsSync(isaPath)) {
    console.log(`Warning: ${isaPath} not found`);
    return childToParent;
  }
  const data = JSON.parse(fs.readFileSync(isaPath, "utf-8")) as ConceptIsaEntryRaw[];
  for (const entry of data) {
    childToParent.set(entry.child, entry.parent);
  }
  return childToParent;
}

/**
 * Walks the ISA hierarchy to find the NCPI category for a concept.
 * @param conceptId - The concept ID to resolve.
 * @param childToParent - Map of child to parent relationships.
 * @param ncpiCategories - Set of known NCPI category IDs.
 * @returns The NCPI category ID, or null if not found.
 */
function resolveToNCPICategory(
  conceptId: string,
  childToParent: Map<string, string>,
  ncpiCategories: Set<string>
): string | null {
  let current = conceptId;
  const visited = new Set<string>();

  // Walk up the hierarchy until we find an NCPI category
  while (current && !visited.has(current)) {
    visited.add(current);

    // Check if current is an NCPI category
    if (ncpiCategories.has(current)) {
      return current;
    }

    // Move to parent
    const parent = childToParent.get(current);
    if (!parent) {
      break;
    }
    current = parent;
  }

  return null;
}

/**
 * Builds a variable summary for a single study.
 * @param phsId - The study phs ID (e.g., "phs000007").
 * @param llmConceptsDir - Directory containing per-study JSON files.
 * @param categories - Map of NCPI category IDs to category info.
 * @param childToParent - Map of concept child to parent relationships.
 * @returns VariableSummary or null if no data found.
 */
export function buildVariableSummaryForStudy(
  phsId: string,
  llmConceptsDir: string,
  categories: Map<string, NCPICategory>,
  childToParent: Map<string, string>
): VariableSummary | null {
  const studyPath = path.join(llmConceptsDir, `${phsId}.json`);

  if (!fs.existsSync(studyPath)) {
    return null;
  }

  const studyData = JSON.parse(fs.readFileSync(studyPath, "utf-8")) as LLMStudyDataRaw;
  const ncpiCategoryIds = new Set(categories.keys());

  // Flatten all variables from all tables
  const allVariables: LLMVariableRaw[] = [];
  for (const table of studyData.tables) {
    allVariables.push(...table.variables);
  }

  if (allVariables.length === 0) {
    return null;
  }

  // Group variables by NCPI category
  const variablesByCategory = new Map<string, LLMVariableRaw[]>();
  let classifiedCount = 0;

  for (const variable of allVariables) {
    let categoryId: string | null = null;

    if (variable.concept_id) {
      // First check if the concept_id itself is an NCPI category
      if (ncpiCategoryIds.has(variable.concept_id)) {
        categoryId = variable.concept_id;
      } else {
        // Walk the hierarchy to find the NCPI category
        categoryId = resolveToNCPICategory(
          variable.concept_id,
          childToParent,
          ncpiCategoryIds
        );
      }

      if (categoryId) {
        classifiedCount++;
      }
    }

    // Use "unclassified" for variables without a resolved category
    const key = categoryId ?? "unclassified";

    if (!variablesByCategory.has(key)) {
      variablesByCategory.set(key, []);
    }
    variablesByCategory.get(key)!.push(variable);
  }

  // Build category summaries
  const categoryList: VariableCategory[] = [];
  const showDetails = allVariables.length <= VARIABLE_DETAIL_THRESHOLD;

  // Sort categories by name, with "unclassified" last
  const sortedCategoryIds = Array.from(variablesByCategory.keys()).sort((a, b) => {
    if (a === "unclassified") return 1;
    if (b === "unclassified") return -1;
    const nameA = categories.get(a)?.name ?? a;
    const nameB = categories.get(b)?.name ?? b;
    return nameA.localeCompare(nameB);
  });

  for (const categoryId of sortedCategoryIds) {
    const vars = variablesByCategory.get(categoryId)!;
    const category = categories.get(categoryId);

    const categoryEntry: VariableCategory = {
      categoryId,
      categoryName: category?.name ?? "Other",
      totalCount: vars.length,
    };

    // Include individual variables only for small studies
    if (showDetails) {
      categoryEntry.variables = vars.map((v): Variable => ({
        description: v.description,
        id: v.id,
        name: v.name,
      }));
    }

    categoryList.push(categoryEntry);
  }

  return {
    categories: categoryList,
    classifiedVariables: classifiedCount,
    totalVariables: allVariables.length,
  };
}

/**
 * Loads variable summaries for all studies.
 * @param sourceDir - Directory containing classification source files.
 * @returns Map of phs ID to VariableSummary.
 */
export function loadVariableSummaries(
  sourceDir: string
): Map<string, VariableSummary> {
  const summaries = new Map<string, VariableSummary>();

  const categoriesPath = path.join(sourceDir, "ncpi-categories.json");
  const isaPath = path.join(sourceDir, "concept-isa.json");
  const llmConceptsDir = path.join(sourceDir, "llm-concepts-v4");

  // Check if required files exist
  if (!fs.existsSync(categoriesPath) || !fs.existsSync(isaPath)) {
    console.log("Variable classification files not found, skipping variable summaries");
    return summaries;
  }

  if (!fs.existsSync(llmConceptsDir)) {
    console.log("llm-concepts-v4 directory not found, skipping variable summaries");
    return summaries;
  }

  // Load reference data
  const categories = loadCategories(categoriesPath);
  const childToParent = loadConceptIsa(isaPath);

  console.log(`Loaded ${categories.size} NCPI categories and ${childToParent.size} ISA relationships`);

  // Process each study file
  const studyFiles = fs.readdirSync(llmConceptsDir).filter(f => f.endsWith(".json"));

  for (const file of studyFiles) {
    const phsId = file.replace(".json", "");
    const summary = buildVariableSummaryForStudy(
      phsId,
      llmConceptsDir,
      categories,
      childToParent
    );

    if (summary) {
      summaries.set(phsId, summary);
    }
  }

  console.log(`Built variable summaries for ${summaries.size} studies`);

  return summaries;
}
