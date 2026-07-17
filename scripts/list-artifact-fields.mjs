// Single source of truth for the studies list artifact field projection.
// Imported by scripts/slim-list-artifact.mjs (the build-time projector) and by
// the mapper drift test (app/apis/catalog/ncpi-catalog/common/utils.test.ts),
// so a new list column that reads a raw field not kept here fails the test
// instead of silently rendering an empty column. Data only — no side effects.
//
// These are the raw fields NCPIStudyInputMapper reads to build a list row.
// consentLongNames is kept so the consent-code column keeps its tooltip. The
// detail-only fields (description, publications, variableSummary) are omitted —
// detail pages source those from props. See epic #425 stage 3b (#430).
export const KEEP_FIELDS = [
  "consentCodes",
  "consentLongNames",
  "dataTypes",
  "dbGapId",
  "duosUrl",
  "focus",
  "gdcProjectId",
  "participantCount",
  "platforms",
  "studyAccession",
  "studyDesigns",
  "title",
];
