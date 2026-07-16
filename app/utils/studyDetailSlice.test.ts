import type { Publication } from "../apis/catalog/common/entities";
import {
  type NCPICatalogStudy,
  PLATFORM,
  type VariableSummary,
} from "../apis/catalog/ncpi-catalog/common/entities";
import { STUDY_DETAIL_SUBPATH } from "../views/StudyDetailView/constants";
import { sliceStudyBySubpath } from "./studyDetailSlice";

const PUBLICATIONS: Publication[] = [
  {
    authors: "Doe J, Roe R",
    citationCount: 42,
    doi: "10.1000/test.1",
    journal: "Test Journal",
    title: "A test publication",
    year: 2020,
  },
  {
    authors: "Roe R",
    citationCount: 7,
    doi: "10.1000/test.2",
    journal: "Test Journal",
    title: "Another test publication",
    year: 2021,
  },
];

const VARIABLE_SUMMARY: VariableSummary = {
  categories: [
    {
      categoryId: "demographics",
      categoryName: "Demographics",
      totalCount: 12,
      variables: [
        { description: "Age of participant", id: "phv1", name: "AGE" },
      ],
    },
  ],
  classifiedVariables: 38,
  totalVariables: 68,
};

const STUDY: NCPICatalogStudy = {
  consentCode: ["GRU", "HMB"],
  consentLongName: {
    GRU: "General Research Use",
    HMB: "Health/Medical/Biomedical",
  },
  dataType: ["WGS"],
  dbGapId: "phs000000",
  duosUrl: null,
  focus: "Test Disease",
  gdcProjectId: null,
  participantCount: 100,
  platform: [PLATFORM.ANVIL],
  publications: PUBLICATIONS,
  studyAccession: "phs000000.v1.p1",
  studyDescription: "A test study description.",
  studyDesign: ["Cohort"],
  title: "Test Study",
  variableSummary: VARIABLE_SUMMARY,
};

describe("sliceStudyBySubpath", () => {
  it("keeps light scalar fields on every subpath", () => {
    for (const subpath of Object.values(STUDY_DETAIL_SUBPATH)) {
      const sliced = sliceStudyBySubpath(STUDY, subpath);
      expect(sliced.consentCode).toEqual(STUDY.consentCode);
      expect(sliced.dataType).toEqual(STUDY.dataType);
      expect(sliced.dbGapId).toBe(STUDY.dbGapId);
      expect(sliced.focus).toBe(STUDY.focus);
      expect(sliced.participantCount).toBe(STUDY.participantCount);
      expect(sliced.platform).toEqual(STUDY.platform);
      expect(sliced.studyAccession).toBe(STUDY.studyAccession);
      expect(sliced.studyDesign).toEqual(STUDY.studyDesign);
      expect(sliced.title).toBe(STUDY.title);
    }
  });

  it("keeps overview-only fields on the overview subpath and strips the rest", () => {
    const sliced = sliceStudyBySubpath(STUDY, STUDY_DETAIL_SUBPATH.OVERVIEW);
    expect(sliced.consentLongName).toEqual(STUDY.consentLongName);
    expect(sliced.studyDescription).toBe(STUDY.studyDescription);
    expect(sliced.publications).toEqual([]);
    expect(sliced.variableSummary).toBeNull();
  });

  it("keeps the variable summary only on the variables subpath", () => {
    const sliced = sliceStudyBySubpath(STUDY, STUDY_DETAIL_SUBPATH.VARIABLES);
    expect(sliced.variableSummary).toEqual(VARIABLE_SUMMARY);
    expect(sliced.consentLongName).toEqual({});
    expect(sliced.studyDescription).toBe("");
    expect(sliced.publications).toEqual([]);
  });

  it("keeps publications only on the selected-publications subpath", () => {
    const sliced = sliceStudyBySubpath(
      STUDY,
      STUDY_DETAIL_SUBPATH.SELECTED_PUBLICATIONS
    );
    expect(sliced.publications).toEqual(PUBLICATIONS);
    expect(sliced.consentLongName).toEqual({});
    expect(sliced.studyDescription).toBe("");
    expect(sliced.variableSummary).toBeNull();
  });

  it("does not mutate the input study", () => {
    const study: NCPICatalogStudy = JSON.parse(JSON.stringify(STUDY));
    sliceStudyBySubpath(study, STUDY_DETAIL_SUBPATH.VARIABLES);
    expect(study).toEqual(STUDY);
  });
});
