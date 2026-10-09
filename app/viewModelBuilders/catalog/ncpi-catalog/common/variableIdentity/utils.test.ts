import type { IdentityChipProps } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/components/Chips/components/Chip/types";
import type { ReactElement } from "react";
import type { Props as ChipLabelProps } from "../../../../../components/common/Table/components/IdentityCell/components/ChipLabel/types";
import { buildVariableIdentityChips } from "./utils";

/**
 * Returns a chip's "label: value" pair from its ChipLabel element.
 * @param chip - Identity chip props.
 * @returns Chip label and value.
 */
function getLabel(chip: IdentityChipProps): ChipLabelProps {
  return (chip.label as ReactElement<ChipLabelProps>).props;
}

describe("buildVariableIdentityChips", () => {
  it("builds one 'Variable: <name>' chip", () => {
    const chips = buildVariableIdentityChips("BMI");
    expect(chips.map(getLabel)).toEqual([{ label: "Variable", value: "BMI" }]);
  });

  it("returns no chips for an empty name", () => {
    expect(buildVariableIdentityChips("")).toEqual([]);
  });
});
