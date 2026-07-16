export const STUDY_DETAIL_SUBPATH = {
  OVERVIEW: "",
  SELECTED_PUBLICATIONS: "selected-publications",
  VARIABLES: "variables",
} as const;

export type StudyDetailSubpath =
  (typeof STUDY_DETAIL_SUBPATH)[keyof typeof STUDY_DETAIL_SUBPATH];

/**
 * Type guard narrowing a raw route string to a known study detail subpath.
 * @param value - Candidate subpath from the route.
 * @returns True if the value is a known study detail subpath.
 */
export function isStudyDetailSubpath(
  value: string
): value is StudyDetailSubpath {
  return Object.values(STUDY_DETAIL_SUBPATH).includes(
    value as StudyDetailSubpath
  );
}
