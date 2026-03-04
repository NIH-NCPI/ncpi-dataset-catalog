import fs from "fs";
import { buildVariableSummaryForStudy } from "./build-variable-summary";

// Mock fs module
jest.mock("fs");
const mockFs = fs as jest.Mocked<typeof fs>;

describe("buildVariableSummaryForStudy", () => {
  const mockCategories = new Map([
    [
      "ncpi:demographics",
      {
        conceptId: "ncpi:demographics",
        description: "Demographic variables",
        name: "Demographics",
      },
    ],
    [
      "ncpi:biomarkers",
      {
        conceptId: "ncpi:biomarkers",
        description: "Biomarker variables",
        name: "Biomarkers",
      },
    ],
    [
      "ncpi:disease_events",
      {
        conceptId: "ncpi:disease_events",
        description: "Disease event variables",
        name: "Disease Events",
      },
    ],
  ]);

  const mockChildToParent = new Map([
    ["loinc:age", "ncpi:demographics"],
    ["loinc:bmi", "ncpi:biomarkers"],
    ["loinc:gender", "ncpi:demographics"],
    ["snomed:diagnosis", "ncpi:disease_events"],
  ]);

  beforeEach(() => {
    mockFs.existsSync.mockReset();
    mockFs.readFileSync.mockReset();
  });

  it("uses 'Other' as category name for unclassified variables with null concept_id", () => {
    const studyData = {
      studyId: "phs000001",
      studyName: "Test Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown variable",
              id: "phv00000001.v1.p1",
              name: "UNKNOWN_VAR",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000001",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.categories).toHaveLength(1);
    expect(result!.categories[0].categoryName).toBe("Other");
    expect(result!.categories[0].categoryId).toBe("unclassified");
    expect(result!.categories[0].totalCount).toBe(1);
  });

  it("uses 'Other' for variables with unresolvable concept_id", () => {
    const studyData = {
      studyId: "phs000002",
      studyName: "Test Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "unknown:concept",
              confidence: "high",
              description: "Unknown concept",
              id: "phv00000002.v1.p1",
              name: "VAR1",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000002",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.categories[0].categoryName).toBe("Other");
    expect(result!.categories[0].categoryId).toBe("unclassified");
  });

  it("assigns correct category names to classified variables", () => {
    const studyData = {
      studyId: "phs000003",
      studyName: "Test Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age at enrollment",
              id: "phv00000003.v1.p1",
              name: "AGE",
              source: "llm",
            },
            {
              concept_id: "loinc:bmi",
              confidence: "high",
              description: "Body mass index",
              id: "phv00000004.v1.p1",
              name: "BMI",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000003",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.categories).toHaveLength(2);
    const categoryNames = result!.categories.map((c) => c.categoryName).sort();
    expect(categoryNames).toEqual(["Biomarkers", "Demographics"]);
  });

  it("handles mix of classified and unclassified variables", () => {
    const studyData = {
      studyId: "phs000004",
      studyName: "Test Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age",
              id: "phv00000005.v1.p1",
              name: "AGE",
              source: "llm",
            },
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown",
              id: "phv00000006.v1.p1",
              name: "UNKNOWN",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000004",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.categories).toHaveLength(2);
    expect(result!.classifiedVariables).toBe(1);
    expect(result!.totalVariables).toBe(2);

    const otherCategory = result!.categories.find(
      (c) => c.categoryId === "unclassified"
    );
    expect(otherCategory?.categoryName).toBe("Other");
    expect(otherCategory?.totalCount).toBe(1);
  });

  it("sorts 'Other' category last in the list", () => {
    const studyData = {
      studyId: "phs000005",
      studyName: "Test Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown",
              id: "phv00000007.v1.p1",
              name: "UNKNOWN",
              source: "llm",
            },
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age",
              id: "phv00000008.v1.p1",
              name: "AGE",
              source: "llm",
            },
            {
              concept_id: "loinc:bmi",
              confidence: "high",
              description: "BMI",
              id: "phv00000009.v1.p1",
              name: "BMI",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000005",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    const lastCategory = result!.categories[result!.categories.length - 1];
    expect(lastCategory.categoryName).toBe("Other");
    expect(lastCategory.categoryId).toBe("unclassified");
  });

  it("returns null when study file does not exist", () => {
    mockFs.existsSync.mockReturnValue(false);

    const result = buildVariableSummaryForStudy(
      "phs999999",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).toBeNull();
  });

  it("returns null for study with no variables", () => {
    const studyData = {
      studyId: "phs000006",
      studyName: "Empty Study",
      tables: [],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000006",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).toBeNull();
  });

  it("returns null for study with empty variable arrays", () => {
    const studyData = {
      studyId: "phs000007",
      studyName: "Empty Variables Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000007",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).toBeNull();
  });

  it("counts variables correctly per category", () => {
    const studyData = {
      studyId: "phs000008",
      studyName: "Test Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age 1",
              id: "phv00000010.v1.p1",
              name: "AGE1",
              source: "llm",
            },
            {
              concept_id: "loinc:gender",
              confidence: "high",
              description: "Gender",
              id: "phv00000011.v1.p1",
              name: "GENDER",
              source: "llm",
            },
            {
              concept_id: "loinc:bmi",
              confidence: "high",
              description: "BMI",
              id: "phv00000012.v1.p1",
              name: "BMI",
              source: "llm",
            },
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown 1",
              id: "phv00000013.v1.p1",
              name: "UNK1",
              source: "llm",
            },
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown 2",
              id: "phv00000014.v1.p1",
              name: "UNK2",
              source: "llm",
            },
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown 3",
              id: "phv00000015.v1.p1",
              name: "UNK3",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000008",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.totalVariables).toBe(6);
    expect(result!.classifiedVariables).toBe(3);

    const demographics = result!.categories.find(
      (c) => c.categoryName === "Demographics"
    );
    expect(demographics?.totalCount).toBe(2);

    const biomarkers = result!.categories.find(
      (c) => c.categoryName === "Biomarkers"
    );
    expect(biomarkers?.totalCount).toBe(1);

    const other = result!.categories.find((c) => c.categoryName === "Other");
    expect(other?.totalCount).toBe(3);
  });

  it("includes individual variables for studies with ≤200 variables", () => {
    const studyData = {
      studyId: "phs000009",
      studyName: "Small Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age at enrollment",
              id: "phv00000016.v1.p1",
              name: "AGE",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000009",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.categories[0].variables).toBeDefined();
    expect(result!.categories[0].variables).toHaveLength(1);
    expect(result!.categories[0].variables![0].name).toBe("AGE");
    expect(result!.categories[0].variables![0].description).toBe(
      "Age at enrollment"
    );
    expect(result!.categories[0].variables![0].id).toBe("phv00000016.v1.p1");
  });

  it("excludes individual variables for studies with >200 variables", () => {
    // Create 201 variables
    const variables = Array.from({ length: 201 }, (_, i) => ({
      concept_id: "loinc:age",
      confidence: "high",
      description: `Variable ${i}`,
      id: `phv${String(i).padStart(8, "0")}.v1.p1`,
      name: `VAR${i}`,
      source: "llm",
    }));

    const studyData = {
      studyId: "phs000010",
      studyName: "Large Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables,
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000010",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.totalVariables).toBe(201);
    expect(result!.categories[0].variables).toBeUndefined();
    expect(result!.categories[0].totalCount).toBe(201);
  });

  it("resolves concept hierarchy to find NCPI category", () => {
    // loinc:age -> ncpi:demographics (via mockChildToParent)
    const studyData = {
      studyId: "phs000011",
      studyName: "Hierarchy Test",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age",
              id: "phv00000017.v1.p1",
              name: "AGE",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000011",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.categories[0].categoryName).toBe("Demographics");
    expect(result!.categories[0].categoryId).toBe("ncpi:demographics");
  });

  it("handles variables across multiple tables", () => {
    const studyData = {
      studyId: "phs000012",
      studyName: "Multi-table Study",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age",
              id: "phv00000018.v1.p1",
              name: "AGE",
              source: "llm",
            },
          ],
        },
        {
          datasetId: "ds2",
          description: null,
          tableName: "table2",
          variables: [
            {
              concept_id: "loinc:bmi",
              confidence: "high",
              description: "BMI",
              id: "phv00000019.v1.p1",
              name: "BMI",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000012",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    expect(result!.totalVariables).toBe(2);
    expect(result!.categories).toHaveLength(2);
  });

  it("sorts categories alphabetically with Other last", () => {
    const studyData = {
      studyId: "phs000013",
      studyName: "Sort Test",
      tables: [
        {
          datasetId: "ds1",
          description: null,
          tableName: "table1",
          variables: [
            {
              concept_id: "snomed:diagnosis",
              confidence: "high",
              description: "Diagnosis",
              id: "phv00000020.v1.p1",
              name: "DX",
              source: "llm",
            },
            {
              concept_id: "loinc:age",
              confidence: "high",
              description: "Age",
              id: "phv00000021.v1.p1",
              name: "AGE",
              source: "llm",
            },
            {
              concept_id: "loinc:bmi",
              confidence: "high",
              description: "BMI",
              id: "phv00000022.v1.p1",
              name: "BMI",
              source: "llm",
            },
            {
              concept_id: null,
              confidence: "high",
              description: "Unknown",
              id: "phv00000023.v1.p1",
              name: "UNK",
              source: "llm",
            },
          ],
        },
      ],
    };

    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(JSON.stringify(studyData));

    const result = buildVariableSummaryForStudy(
      "phs000013",
      "/mock/dir",
      mockCategories,
      mockChildToParent
    );

    expect(result).not.toBeNull();
    const categoryNames = result!.categories.map((c) => c.categoryName);
    // Should be alphabetical, with Other last
    expect(categoryNames).toEqual([
      "Biomarkers",
      "Demographics",
      "Disease Events",
      "Other",
    ]);
  });
});
