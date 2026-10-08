import type { IdentityChipProps } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/components/Chips/components/Chip/types";
import { ChipLabel } from "./components/ChipLabel/chipLabel";

/**
 * Builds a "label: value" IdentityCell chip.
 * @param label - Field name.
 * @param value - Field value.
 * @returns Identity chip props.
 */
export function buildIdentityChip(
  label: string,
  value: string
): IdentityChipProps {
  return { label: <ChipLabel label={label} value={value} /> };
}
