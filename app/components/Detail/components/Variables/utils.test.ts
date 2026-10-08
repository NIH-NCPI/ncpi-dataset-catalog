import { buildDbGapVariableUrl } from "./utils";

describe("buildDbGapVariableUrl", () => {
  it("links to the dbGaP variable page with the numeric phv id", () => {
    expect(buildDbGapVariableUrl("phs000220.v2.p2", "phv00163107.v2.p2")).toBe(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi?study_id=phs000220.v2.p2&phv=00163107"
    );
  });

  it("handles a phv id without a version suffix", () => {
    expect(buildDbGapVariableUrl("phs000220.v2.p2", "phv00163107")).toBe(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi?study_id=phs000220.v2.p2&phv=00163107"
    );
  });
});
