import type { IdentityChipProps } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/components/Chips/components/Chip/types";
import { buildIdentityChip } from "../../../../../components/common/Table/components/IdentityCell/utils";
import { VARIABLE_IDENTITY_CHIP_LABEL } from "./constants";

/**
 * Builds the IdentityCell chips for a variable: a "Variable: <name>" chip, or no chips when the name is empty.
 * @param variableName - Variable name.
 * @returns Identity chip props.
 */
export function buildVariableIdentityChips(
  variableName: string
): IdentityChipProps[] {
  if (!variableName) return [];
  return [buildIdentityChip(VARIABLE_IDENTITY_CHIP_LABEL.VARIABLE, variableName)];
}
