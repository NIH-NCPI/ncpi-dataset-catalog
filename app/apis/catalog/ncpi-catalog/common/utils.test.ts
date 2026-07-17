import { KEEP_FIELDS } from "scripts/list-artifact-fields.mjs";
import {
  type NCPICatalogStudy,
  type NCPIStudy,
  type NCPIStudyMapperInput,
  PLATFORM,
} from "./entities";
import { NCPIStudyInputMapper } from "./utils";

// A full catalog record — every field the mapper can read is populated.
const FULL_STUDY: NCPIStudy = {
  consentCodes: ["GRU", "HMB"],
  consentLongNames: {
    GRU: "General Research Use",
    HMB: "Health/Medical/Biomedical",
  },
  dataTypes: ["WGS"],
  dbGapId: "phs000001",
  description: "A full study description.",
  duosUrl: "https://duos.example/phs000001",
  focus: "Test Disease",
  gdcProjectId: "GDC-1",
  numChildren: 2,
  parentStudyId: "phs000000",
  parentStudyName: "Parent Study",
  participantCount: 100,
  platforms: [PLATFORM.ANVIL],
  publications: [
    {
      authors: "Doe J",
      citationCount: 3,
      doi: "10.1000/x",
      journal: "J",
      title: "T",
      year: 2020,
    },
  ],
  studyAccession: "phs000001.v1.p1",
  studyDesigns: ["Cohort"],
  title: "Full Study",
  variableSummary: {
    categories: [],
    classifiedVariables: 0,
    totalVariables: 5,
  },
};

// The mapped fields that legitimately differ once the heavy raw fields are
// dropped from the slim artifact.
const HEAVY_MAPPED_FIELDS = [
  "publications",
  "studyDescription",
  "variableSummary",
] as const;

/**
 * Projects a full record down to the runtime list artifact's kept fields, the
 * same way scripts/slim-list-artifact.mjs does.
 * @param study - Full study record.
 * @returns Slim record with only KEEP_FIELDS present.
 */
function slim(study: NCPIStudy): NCPIStudyMapperInput {
  const src = study as unknown as Record<string, unknown>;
  const record: Record<string, unknown> = {};
  for (const field of KEEP_FIELDS) {
    if (field in src) record[field] = src[field];
  }
  return record as NCPIStudyMapperInput;
}

/**
 * Returns a copy of the mapped study without the heavy fields that the slim
 * artifact intentionally drops.
 * @param mapped - Mapped catalog study.
 * @returns Mapped study minus the heavy fields.
 */
function withoutHeavyFields(
  mapped: NCPICatalogStudy
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(mapped).filter(
      ([key]) => !HEAVY_MAPPED_FIELDS.includes(key as never)
    )
  );
}

describe("NCPIStudyInputMapper — slim vs full drift", () => {
  it("maps a slimmed record identically to the full record, except the dropped heavy fields", () => {
    const fromFull = NCPIStudyInputMapper(FULL_STUDY);
    const fromSlim = NCPIStudyInputMapper(slim(FULL_STUDY));

    // Guards against KEEP_FIELDS/mapper drift: if a list column starts reading a
    // raw field that KEEP_FIELDS does not keep, the slim record loses it and
    // this equality fails instead of the column silently rendering empty.
    expect(withoutHeavyFields(fromSlim)).toEqual(withoutHeavyFields(fromFull));
  });

  it("defaults the dropped heavy fields on a slim record", () => {
    const fromSlim = NCPIStudyInputMapper(slim(FULL_STUDY));
    expect(fromSlim.studyDescription).toBeUndefined();
    expect(fromSlim.publications).toEqual([]);
    expect(fromSlim.variableSummary).toBeNull();
  });

  it("preserves the heavy fields on a full record", () => {
    const fromFull = NCPIStudyInputMapper(FULL_STUDY);
    expect(fromFull.studyDescription).toBe(FULL_STUDY.description);
    expect(fromFull.publications).toEqual(FULL_STUDY.publications);
    expect(fromFull.variableSummary).toEqual(FULL_STUDY.variableSummary);
  });
});
