import type { IdentityChipProps } from "@databiosphere/findable-ui/lib/components/Table/components/TableCell/components/IdentityCell/components/Chips/components/Chip/types";
import type { ReactElement } from "react";
import type { Props as ChipLabelProps } from "../../../../../components/common/Table/components/IdentityCell/components/ChipLabel/types";
import { MAX_CONSENT_CHIPS } from "./constants";
import type { StudyIdentity } from "./types";
import { buildStudyIdentityChips } from "./utils";

const STUDY: StudyIdentity = {
  consentCodes: ["GRU", "HMB-IRB"],
  consentLongNames: {
    GRU: "General Research Use",
    "HMB-IRB": "Unspecified",
  },
  dbGapId: "phs000001",
  platforms: ["AnVIL", "BDC"],
};

/**
 * Returns a chip's "label: value" pair from its ChipLabel element.
 * @param chip - Identity chip props.
 * @returns Chip label and value.
 */
function getLabel(chip: IdentityChipProps): ChipLabelProps {
  return (chip.label as ReactElement<ChipLabelProps>).props;
}

describe("buildStudyIdentityChips", () => {
  it("builds dbGaP, platform and consent chips in order", () => {
    const chips = buildStudyIdentityChips(STUDY);
    expect(chips.map(getLabel)).toEqual([
      { label: "dbGaP", value: "phs000001" },
      { label: "Platform", value: "AnVIL" },
      { label: "Platform", value: "BDC" },
      { label: "Consent", value: "GRU" },
      { label: "Consent", value: "HMB-IRB" },
    ]);
  });

  it("leaves out empty values", () => {
    const chips = buildStudyIdentityChips({
      consentCodes: ["", "GRU"],
      consentLongNames: {},
      dbGapId: "",
      platforms: ["", "AnVIL"],
    });
    expect(chips.map(getLabel)).toEqual([
      { label: "Platform", value: "AnVIL" },
      { label: "Consent", value: "GRU" },
    ]);
  });

  it("returns no chips when every value is empty", () => {
    expect(
      buildStudyIdentityChips({
        consentCodes: [],
        consentLongNames: {},
        dbGapId: "",
        platforms: [],
      })
    ).toEqual([]);
  });

  it("gives a consent chip a focusable tooltip only when it has a displayable long name", () => {
    const chips = buildStudyIdentityChips(STUDY);
    const [gru, hmbIrb] = chips.slice(-2);
    expect(gru.slotProps?.tooltip?.title).toBe("General Research Use");
    expect(gru.tabIndex).toBe(0);
    expect(hmbIrb.slotProps).toBeUndefined();
    expect(hmbIrb.tabIndex).toBeUndefined();
  });

  it("gives platform and dbGaP chips no tooltip", () => {
    const chips = buildStudyIdentityChips(STUDY);
    for (const chip of chips.slice(0, 3)) {
      expect(chip.slotProps).toBeUndefined();
      expect(chip.tabIndex).toBeUndefined();
    }
  });

  it(`shows a chip per consent code up to ${MAX_CONSENT_CHIPS} codes`, () => {
    const consentCodes = ["C1", "C2", "C3"].slice(0, MAX_CONSENT_CHIPS);
    const chips = buildStudyIdentityChips({ ...STUDY, consentCodes });
    expect(chips.slice(3).map(getLabel)).toEqual(
      consentCodes.map((value) => ({ label: "Consent", value }))
    );
  });

  it(`collapses more than ${MAX_CONSENT_CHIPS} consent codes into one summary chip`, () => {
    const consentCodes = ["C1", "C2", "C3", "C4"];
    const chips = buildStudyIdentityChips({ ...STUDY, consentCodes });
    const consentChips = chips.slice(3);
    expect(consentChips).toHaveLength(1);
    expect(getLabel(consentChips[0])).toEqual({
      label: "Consent",
      value: "4 codes",
    });
    expect(consentChips[0].slotProps?.tooltip?.title).toBe(
      "C1, C2, C3, C4"
    );
    expect(consentChips[0].tabIndex).toBe(0);
  });
});
