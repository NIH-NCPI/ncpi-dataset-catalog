import { ListItemTextProps } from "@mui/material";
import { NCPICatalogStudy } from "app/apis/catalog/ncpi-catalog/common/entities";

/**
 * Generates a list of request access menu options based on the provided study.
 * This function extracts identifiers (DUOS URL and dbGaP ID) from the study and returns an array of menu option objects.
 * Each menu option contains a link `href` and title `primary` and description text `secondary`, to be used in Material UI's `MenuItem` and `ListItemText` component.
 * @param ncpiCatalogStudy - Response model return from datasets API.
 * @returns menu option objects with `href`, `primary`, and `secondary` properties.
 */
export function getRequestAccessOptions(
  ncpiCatalogStudy: NCPICatalogStudy
): (Pick<ListItemTextProps, "primary" | "secondary"> & { href: string })[] {
  // Get the dbGaP ID and DUOS ID from the study.
  const { dbGapId, duosUrl } = ncpiCatalogStudy;

  // Build up the request access options based on the presence of dbGaP ID and DUOS URL.
  const options = [];
  if (duosUrl) {
    // If a DUOS ID is present, add a menu option for DUOS.
    options.push({
      href: duosUrl,
      primary: "DUOS",
      secondary:
        "Request access via DUOS, which streamlines data access for NHGRI-sponsored studies, both registered and unregistered in dbGaP.",
    });
  }
  if (dbGapId) {
    // If a dbGaP ID is present, add a menu option for dbGaP.
    options.push({
      href: `https://dbgap.ncbi.nlm.nih.gov/aa/wga.cgi?adddataset=${dbGapId}`,
      primary: "dbGaP",
      secondary:
        "Request access via the dbGaP Authorized Access portal for studies registered in dbGaP, following the standard data access process.",
    });
  }
  return options;
}
