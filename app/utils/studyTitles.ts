import fs from "fs";

const MAX_DATA_TYPES_SHOWN = 2;
const STUDIES_PATH = "catalog/ncpi-platform-studies.json";

interface StudyMeta {
  dataTypes: string[];
  focus: string;
  participantCount: number;
  platforms: string[];
  title: string;
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
          title: string;
        };
        return [
          study.dbGapId,
          {
            dataTypes: study.dataTypes ?? [],
            focus: study.focus ?? "",
            participantCount: study.participantCount ?? 0,
            platforms: study.platforms ?? [],
            title: study.title,
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
 * Builds a generated OG description from study metadata.
 * @param meta - Study metadata.
 * @returns Description like "Autistic Disorder study with WXS data on AnVIL (12,772 participants)".
 */
function buildDescription(meta: StudyMeta): string | undefined {
  const parts: string[] = [];

  if (meta.focus) {
    parts.push(`${meta.focus} study`);
  }

  if (meta.dataTypes.length > 0) {
    const shown = meta.dataTypes.slice(0, MAX_DATA_TYPES_SHOWN);
    const more = meta.dataTypes.length - shown.length;
    let dt = shown.join(", ");
    if (more > 0) dt += ` + ${more} more`;
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
  return {
    pageDescription: meta ? buildDescription(meta) : undefined,
    pageTitle: buildPageTitle(meta, studyId, subpath),
  };
}
