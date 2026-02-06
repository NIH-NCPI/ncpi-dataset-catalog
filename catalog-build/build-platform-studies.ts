import { DbGapStudy } from "../app/apis/catalog/common/entities";
import {
  NCPIStudy,
  PlatformStudy,
} from "../app/apis/catalog/ncpi-catalog/common/entities";
import { generateConsentDescriptions } from "./common/consent-codes";
import { getStudyFromCSVandFTP } from "./common/dbGapCSVandFTP";

/**
 * Build the catalog platform studies for NCPI.
 * @param platformStudies - a list of platform study values.
 * @param duosUrlByDbGapId - map from dbGap ID to DUOS study URL.
 * @returns NCPI catalog platform studies.
 */
export async function buildNCPIPlatformStudies(
  platformStudies: PlatformStudy[],
  duosUrlByDbGapId: Map<string, string>
): Promise<NCPIStudy[]> {
  const ncpiStudies: NCPIStudy[] = [];
  const studiesById: Map<string, NCPIStudy> = new Map();

  // build workspaces
  for (const stub of platformStudies) {
    const study = await getStudyFromCSVandFTP(stub.dbGapId);
    /* Continue when the study is incomplete. */

    if (!study || !isStudyFieldsComplete(study)) {
      continue;
    }

    // If a study with this ID has been seen already, add the platform to that existing object
    const existingPlatforms = studiesById.get(study.dbGapId)?.platforms;
    if (existingPlatforms) {
      if (!existingPlatforms.includes(stub.platform)) {
        existingPlatforms.push(stub.platform);
      }
      continue;
    }

    const consentLongNames: Record<string, string> = {};

    for (const code of study.consentCodes) {
      consentLongNames[code] = (
        await generateConsentDescriptions(code)
      ).consentLongName;
    }

    const ncpiStudy = {
      ...study,
      consentLongNames,
      dbGapUrl: `https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=${study.studyAccession}`,
      duosUrl: duosUrlByDbGapId.get(study.dbGapId) ?? null,
      platforms: [stub.platform],
    };

    studiesById.set(study.dbGapId, ncpiStudy);
    ncpiStudies.push(ncpiStudy);
    console.log(ncpiStudy.dbGapId, ncpiStudy.title);
  }

  // Compute numChildren by counting studies that reference each parent
  const childCounts = new Map<string, number>();
  for (const study of ncpiStudies) {
    if (study.parentStudyId) {
      childCounts.set(
        study.parentStudyId,
        (childCounts.get(study.parentStudyId) || 0) + 1
      );
    }
  }
  for (const study of ncpiStudies) {
    study.numChildren = childCounts.get(study.dbGapId) || 0;
  }

  return ncpiStudies;
}

/**
 * Returns true if the study has a valid study name and subjects total.
 * @param study - dbGaP study.
 * @returns true if the study is "complete" meaning it has at least a title and subjects.
 */
function isStudyFieldsComplete(study: DbGapStudy): boolean {
  return !!(study.title && study.participantCount);
}
