import { getDisplayConsentLongName } from "./utils";

describe("getDisplayConsentLongName", () => {
  it("returns the long name when it is a real description", () => {
    expect(getDisplayConsentLongName("General Research Use")).toBe(
      "General Research Use"
    );
  });

  it("returns undefined when the long name is missing or empty", () => {
    expect(getDisplayConsentLongName(undefined)).toBeUndefined();
    expect(getDisplayConsentLongName("")).toBeUndefined();
  });

  it("returns undefined for the 'Unspecified' placeholder, in any case", () => {
    expect(getDisplayConsentLongName("Unspecified")).toBeUndefined();
    expect(getDisplayConsentLongName("UNSPECIFIED")).toBeUndefined();
  });

  it("returns undefined for build error messages", () => {
    expect(
      getDisplayConsentLongName("ERROR: unknown consent code")
    ).toBeUndefined();
  });

  it("keeps long names that only contain 'unspecified' or 'error' later on", () => {
    expect(getDisplayConsentLongName("Use is unspecified")).toBe(
      "Use is unspecified"
    );
    expect(getDisplayConsentLongName("No error tolerance")).toBe(
      "No error tolerance"
    );
  });
});
