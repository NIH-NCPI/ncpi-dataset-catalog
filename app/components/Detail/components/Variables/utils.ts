/**
 * Build a dbGaP variable page URL.
 * @param studyAccession - Study accession with version (e.g., "phs000007.v1.p1").
 * @param phvId - Variable PHV ID (e.g., "phv00481718.v2.p1").
 * @returns Full URL to the variable page on dbGaP.
 */
export function buildDbGapVariableUrl(
  studyAccession: string,
  phvId: string
): string {
  const phvNum = phvId.split(".")[0].replace("phv", "");
  return `https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi?study_id=${studyAccession}&phv=${phvNum}`;
}
