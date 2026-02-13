import {
  NCPICatalogStudy,
  PLATFORM,
} from "../apis/catalog/ncpi-catalog/common/entities";

/**
 * Returns the platform-specific URL for viewing a study, or null if unavailable.
 * @param study - NCPI catalog study.
 * @param platform - Platform to generate URL for.
 * @returns Platform URL or null.
 */
export function getPlatformUrl(
  study: NCPICatalogStudy,
  platform: PLATFORM
): string | null {
  const { dbGapId, gdcProjectId } = study;
  switch (platform) {
    case PLATFORM.ANVIL: {
      const params = encodeURIComponent(
        JSON.stringify([
          {
            categoryKey: "datasets.registered_identifier",
            value: [dbGapId],
          },
        ])
      );
      return `https://explore.anvilproject.org/datasets?filter=${params}`;
    }
    case PLATFORM.BDC:
      return "https://gen3.biodatacatalyst.nhlbi.nih.gov/discovery";
    case PLATFORM.CRDC:
      if (!gdcProjectId) return null;
      return `https://portal.gdc.cancer.gov/projects/${encodeURIComponent(gdcProjectId)}`;
    case PLATFORM.DBGAP:
      return `https://dbgap.ncbi.nlm.nih.gov/beta/study/${study.studyAccession}/#study`;
    case PLATFORM.KFDRC:
      return "https://portal.kidsfirstdrc.org/public-studies";
    default:
      return null;
  }
}
