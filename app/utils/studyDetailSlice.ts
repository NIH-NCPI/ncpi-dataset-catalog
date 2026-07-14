import type { NCPICatalogStudy } from "../apis/catalog/ncpi-catalog/common/entities";
import { STUDY_DETAIL_SUBPATH } from "../views/StudyDetailView/constants";

/**
 * Returns the study sliced down to what the given subpath's page renders, so
 * that each prerendered page serializes only its own heavy fields into
 * __NEXT_DATA__ rather than the full study three times over. Light scalar
 * fields are kept everywhere; the heavy fields (study description with
 * consent long names, variable summary, publications) are kept only on the
 * subpath that renders them. The publications and variables counts the Hero
 * tabs consume on every subpath are threaded separately as the
 * publicationsCount and variablesCount page props.
 * @param study - Study.
 * @param subpath - Study detail subpath.
 * @returns Study with heavy fields sliced for the given subpath.
 */
export function sliceStudyBySubpath(
  study: NCPICatalogStudy,
  subpath: string
): NCPICatalogStudy {
  return {
    ...study,
    consentLongName:
      subpath === STUDY_DETAIL_SUBPATH.OVERVIEW ? study.consentLongName : {},
    publications:
      subpath === STUDY_DETAIL_SUBPATH.SELECTED_PUBLICATIONS
        ? study.publications
        : [],
    studyDescription:
      subpath === STUDY_DETAIL_SUBPATH.OVERVIEW ? study.studyDescription : "",
    variableSummary:
      subpath === STUDY_DETAIL_SUBPATH.VARIABLES ? study.variableSummary : null,
  };
}
