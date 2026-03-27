import fs from "fs";

const STUDIES_PATH = "catalog/ncpi-platform-studies.json";

// Parsed once at module load, reused across all getStaticProps calls.
let studyTitles: Map<string, string> | null = null;

/**
 * Returns a cached dbGapId-to-title map built from the catalog JSON.
 * @returns Map from dbGapId to study title.
 */
export function getStudyTitles(): Map<string, string> {
  if (!studyTitles) {
    const raw = JSON.parse(fs.readFileSync(STUDIES_PATH, "utf-8"));
    studyTitles = new Map(
      Object.values(raw).map((s) => {
        const study = s as { dbGapId: string; title: string };
        return [study.dbGapId, study.title];
      })
    );
  }
  return studyTitles;
}

/**
 * Returns a page title for a study detail page.
 * @param studyId - The dbGaP study ID (e.g. "phs000220").
 * @returns Formatted title like "phs000220 — Study Name", or just the studyId if not found.
 */
export function getStudyPageTitle(studyId: string): string {
  try {
    const title = getStudyTitles().get(studyId);
    return title ? `${studyId} — ${title}` : studyId;
  } catch {
    return studyId;
  }
}
