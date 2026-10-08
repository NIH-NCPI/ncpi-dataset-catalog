import type { IdentityChipProps } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/components/Chips/components/Chip/types";
import { buildIdentityChip } from "../../../../../components/common/Table/components/IdentityCell/utils";
import { getDisplayConsentLongName } from "../../../../../components/Detail/components/ConsentTooltip/utils";
import { MAX_CONSENT_CHIPS, STUDY_IDENTITY_CHIP_LABEL } from "./constants";
import type { StudyIdentity } from "./types";

/**
 * Builds a consent chip, with the consent long name as its tooltip when one is available.
 * The chip is made focusable so keyboard users can open the tooltip.
 * @param consentCode - Consent code.
 * @param consentLongNames - Consent long names, keyed by consent code.
 * @returns Identity chip props.
 */
function buildConsentChip(
  consentCode: string,
  consentLongNames: Record<string, string>
): IdentityChipProps {
  const chip = buildIdentityChip(STUDY_IDENTITY_CHIP_LABEL.CONSENT, consentCode);
  const tooltip = getDisplayConsentLongName(consentLongNames[consentCode]);
  if (!tooltip) return chip;
  return { ...chip, slotProps: { tooltip: { title: tooltip } }, tabIndex: 0 };
}

/**
 * Builds the consent chips: one chip per consent code, or, above MAX_CONSENT_CHIPS codes, one
 * "N codes" summary chip whose tooltip lists the codes.
 * @param consentCodes - Consent codes.
 * @param consentLongNames - Consent long names, keyed by consent code.
 * @returns Identity chip props.
 */
function buildConsentChips(
  consentCodes: string[],
  consentLongNames: Record<string, string>
): IdentityChipProps[] {
  if (consentCodes.length <= MAX_CONSENT_CHIPS) {
    return consentCodes.map((consentCode) =>
      buildConsentChip(consentCode, consentLongNames)
    );
  }
  return [
    {
      ...buildIdentityChip(
        STUDY_IDENTITY_CHIP_LABEL.CONSENT,
        `${consentCodes.length} codes`
      ),
      slotProps: { tooltip: { title: consentCodes.join(", ") } },
      tabIndex: 0,
    },
  ];
}

/**
 * Builds the IdentityCell chips for a study: dbGaP Id, one chip per platform, and the consent
 * chips (see buildConsentChips). Empty values are left out.
 * @param studyIdentity - Study identity values.
 * @param studyIdentity.consentCodes - Consent codes.
 * @param studyIdentity.consentLongNames - Consent long names, keyed by consent code.
 * @param studyIdentity.dbGapId - dbGaP Id.
 * @param studyIdentity.platforms - Platforms.
 * @returns Identity chip props.
 */
export function buildStudyIdentityChips({
  consentCodes,
  consentLongNames,
  dbGapId,
  platforms,
}: StudyIdentity): IdentityChipProps[] {
  const chips: IdentityChipProps[] = [];
  if (dbGapId)
    chips.push(buildIdentityChip(STUDY_IDENTITY_CHIP_LABEL.DB_GAP, dbGapId));
  for (const platform of platforms.filter(Boolean)) {
    chips.push(buildIdentityChip(STUDY_IDENTITY_CHIP_LABEL.PLATFORM, platform));
  }
  chips.push(
    ...buildConsentChips(consentCodes.filter(Boolean), consentLongNames)
  );
  return chips;
}
