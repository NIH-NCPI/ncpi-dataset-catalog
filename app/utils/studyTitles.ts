import fs from "fs";

const MAX_CATEGORIES_SHOWN = 3;
const MAX_DATA_TYPES_SHOWN = 2;
const MAX_PUB_TITLE_LENGTH = 70;
const STUDIES_PATH = "catalog/ncpi-platform-studies.json";

interface Publication {
  citationCount?: number;
  title?: string;
}

interface VariableCategory {
  categoryId: string;
  categoryName: string;
  totalCount: number;
}

interface VariableSummary {
  categories?: VariableCategory[];
  totalVariables: number;
}

interface StudyMeta {
  dataTypes: string[];
  focus: string;
  participantCount: number;
  platforms: string[];
  publications: Publication[];
  title: string;
  variableSummary: VariableSummary | null;
}

/**
 * OG meta fields for a study page.
 */
export interface StudyPageMeta {
  pageDescription?: string;
  pageTitle: string;
}

// Parsed on first call, cached and reused across all subsequent calls.
let studyMetaCache: Map<string, StudyMeta> | null = null;

/**
 * Returns a cached dbGapId-to-metadata map built from the catalog JSON.
 * @returns Map from dbGapId to study metadata.
 */
function getStudyMeta(): Map<string, StudyMeta> {
  if (!studyMetaCache) {
    const raw = JSON.parse(fs.readFileSync(STUDIES_PATH, "utf-8"));
    studyMetaCache = new Map(
      Object.values(raw).map((s) => {
        const study = s as {
          dataTypes?: string[];
          dbGapId: string;
          focus?: string;
          participantCount?: number;
          platforms?: string[];
          publications?: Publication[];
          title: string;
          variableSummary?: VariableSummary | null;
        };
        return [
          study.dbGapId,
          {
            dataTypes: study.dataTypes ?? [],
            focus: study.focus ?? "",
            participantCount: study.participantCount ?? 0,
            platforms: study.platforms ?? [],
            publications: study.publications ?? [],
            title: study.title,
            variableSummary: study.variableSummary ?? null,
          },
        ];
      })
    );
  }
  return studyMetaCache;
}

const SUBPATH_LABELS: Record<string, string> = {
  "selected-publications": "Selected Publications",
  variables: "Variables",
};

/**
 * Builds a page title from study metadata.
 * @param meta - Study metadata (or undefined if not found).
 * @param studyId - The dbGaP study ID.
 * @param subpath - Optional subpath (e.g. "variables").
 * @returns Formatted title like "Variables — phs000220 — Study Name".
 */
function buildPageTitle(
  meta: StudyMeta | undefined,
  studyId: string,
  subpath?: string
): string {
  const base = meta ? `${studyId} — ${meta.title}` : studyId;
  const label = subpath ? SUBPATH_LABELS[subpath] : undefined;
  return label ? `${label} — ${base}` : base;
}

/**
 * Joins a list with a cap, appending "+ N more" if truncated.
 * @param items - Items to join.
 * @param max - Maximum items to show.
 * @returns Formatted string like "A, B + 3 more".
 */
function joinWithCap(items: string[], max: number): string {
  const shown = items.slice(0, max);
  const more = items.length - shown.length;
  let result = shown.join(", ");
  if (more > 0) result += ` + ${more} more`;
  return result;
}

/**
 * Builds an overview description from study metadata.
 * @param meta - Study metadata.
 * @returns Description like "Autistic Disorder study with WXS data on AnVIL (12,772 participants)".
 */
function buildOverviewDescription(meta: StudyMeta): string | undefined {
  const parts: string[] = [];

  if (meta.focus) {
    parts.push(`${meta.focus} study`);
  }

  if (meta.dataTypes.length > 0) {
    const dt = joinWithCap(meta.dataTypes, MAX_DATA_TYPES_SHOWN);
    parts.push(`${parts.length > 0 ? "with" : "Study with"} ${dt} data`);
  }

  if (meta.platforms.length > 0) {
    parts.push(`on ${meta.platforms.join(", ")}`);
  }

  if (meta.participantCount > 0) {
    parts.push(`(${meta.participantCount.toLocaleString()} participants)`);
  }

  return parts.length > 0 ? parts.join(" ") : undefined;
}

/**
 * Builds a variables page description from study metadata.
 * @param meta - Study metadata.
 * @returns Description like "29 variables across Demographics, Disease Events, Race and Ethnicity".
 */
function buildVariablesDescription(meta: StudyMeta): string | undefined {
  const vs = meta.variableSummary;
  if (!vs || !vs.totalVariables) return undefined;

  const categories = (vs.categories ?? [])
    .filter((c) => c.categoryId !== "unclassified")
    .map((c) => c.categoryName);

  const parts = [`${vs.totalVariables} variables`];

  if (categories.length > 0) {
    parts.push(`across ${joinWithCap(categories, MAX_CATEGORIES_SHOWN)}`);
  }

  return parts.join(" ");
}

/**
 * Builds a publications page description from study metadata.
 * @param meta - Study metadata.
 * @returns Description like '5 selected publications including "Synaptic..." (2,558 citations)'.
 */
function buildPublicationsDescription(meta: StudyMeta): string | undefined {
  if (meta.publications.length === 0) return undefined;

  const count = meta.publications.length;
  const parts = [`${count} selected publication${count !== 1 ? "s" : ""}`];

  const top = [...meta.publications].sort(
    (a, b) => (b.citationCount ?? 0) - (a.citationCount ?? 0)
  )[0];

  if (top?.title) {
    const truncated =
      top.title.length > MAX_PUB_TITLE_LENGTH
        ? `${top.title.substring(0, MAX_PUB_TITLE_LENGTH)}...`
        : top.title;
    const cited = top.citationCount
      ? ` (${top.citationCount.toLocaleString()} citations)`
      : "";
    parts.push(`including "${truncated}"${cited}`);
  }

  return parts.join(" ");
}

/**
 * Returns OG page title and description for a study page.
 * @param studyId - The dbGaP study ID (e.g. "phs000220").
 * @param subpath - Optional subpath (e.g. "variables", "selected-publications").
 * @returns Object with pageTitle and optional pageDescription.
 */
export function getStudyPageMeta(
  studyId: string,
  subpath?: string
): StudyPageMeta {
  const meta = getStudyMeta().get(studyId);
  let pageDescription: string | undefined;

  if (meta) {
    if (subpath === "variables") {
      pageDescription = buildVariablesDescription(meta);
    } else if (subpath === "selected-publications") {
      pageDescription = buildPublicationsDescription(meta);
    } else {
      pageDescription = buildOverviewDescription(meta);
    }
  }

  const result: StudyPageMeta = {
    pageTitle: buildPageTitle(meta, studyId, subpath),
  };
  if (pageDescription) {
    result.pageDescription = pageDescription;
  }
  return result;
}
