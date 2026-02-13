import {
  NCPICatalogStudy,
  PLATFORM,
} from "../apis/catalog/ncpi-catalog/common/entities";
import { buildStudyJsonLd, SchemaDataset } from "./schemaOrg";

const BROWSER_URL = "https://ncpi-data.org";

function makeStudy(
  overrides: Partial<NCPICatalogStudy> = {}
): NCPICatalogStudy {
  return {
    consentCode: ["GRU"],
    consentLongName: { GRU: "General Research Use" },
    dataType: ["WGS"],
    dbGapId: "phs000123",
    duosUrl: null,
    focus: "Cardiovascular",
    gdcProjectId: null,
    participantCount: 100,
    platform: [],
    publications: [],
    studyAccession: "phs000123.v1.p1",
    studyDescription: "<p>A <b>study</b> description.</p>",
    studyDesign: ["Case-Control"],
    title: "Test Study",
    ...overrides,
  };
}

describe("buildStudyJsonLd", () => {
  let result: SchemaDataset;

  beforeEach(() => {
    result = buildStudyJsonLd(makeStudy(), BROWSER_URL);
  });

  it("sets context and type", () => {
    expect(result["@context"]).toBe("https://schema.org");
    expect(result["@type"]).toBe("Dataset");
  });

  it("maps name from title", () => {
    expect(result.name).toBe("Test Study");
  });

  it("strips HTML from description", () => {
    expect(result.description).toBe("A study description.");
  });

  it("includes both identifiers", () => {
    expect(result.identifier).toEqual(["phs000123", "phs000123.v1.p1"]);
  });

  it("builds the study URL", () => {
    expect(result.url).toBe("https://ncpi-data.org/studies/phs000123");
  });

  it("includes data catalog info", () => {
    expect(result.includedInDataCatalog).toEqual({
      "@type": "DataCatalog",
      name: "NCPI Dataset Catalog",
      url: BROWSER_URL,
    });
  });

  it("sets isAccessibleForFree to false", () => {
    expect(result.isAccessibleForFree).toBe(false);
  });

  it("combines focus and studyDesign into keywords", () => {
    expect(result.keywords).toEqual(["Cardiovascular", "Case-Control"]);
  });

  it("maps dataType to measurementTechnique", () => {
    expect(result.measurementTechnique).toEqual(["WGS"]);
  });

  it("includes distribution with platform URLs", () => {
    const study = makeStudy({ platform: [PLATFORM.ANVIL, PLATFORM.BDC] });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.distribution).toEqual([
      {
        "@type": "DataDownload",
        contentUrl: `https://explore.anvilproject.org/datasets?filter=${encodeURIComponent(JSON.stringify([{ categoryKey: "datasets.registered_identifier", value: ["phs000123"] }]))}`,
      },
      {
        "@type": "DataDownload",
        contentUrl: "https://gen3.biodatacatalyst.nhlbi.nih.gov/discovery",
      },
    ]);
  });

  it("omits distribution when platform is empty", () => {
    expect(result.distribution).toBeUndefined();
  });

  it("sets sameAs to dbGaP study URL", () => {
    expect(result.sameAs).toBe(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=phs000123.v1.p1"
    );
  });

  it("parses version from studyAccession", () => {
    expect(result.version).toBe("1");
  });

  it("parses multi-digit version from studyAccession", () => {
    const study = makeStudy({ studyAccession: "phs000209.v13.p3" });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.version).toBe("13");
  });

  it("truncates description to 5000 characters", () => {
    const longDescription = "<p>" + "A".repeat(6000) + "</p>";
    const study = makeStudy({ studyDescription: longDescription });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.description.length).toBe(5000);
    expect(jsonLd.description.endsWith("\u2026")).toBe(true);
  });

  it("does not truncate short descriptions", () => {
    expect(result.description).toBe("A study description.");
  });

  it("omits keywords when focus and studyDesign are empty", () => {
    const study = makeStudy({ focus: "", studyDesign: [] });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.keywords).toBeUndefined();
  });

  it("omits measurementTechnique when dataType is empty", () => {
    const study = makeStudy({ dataType: [] });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.measurementTechnique).toBeUndefined();
  });

  it("omits measurementTechnique when dataType is only Unspecified", () => {
    const study = makeStudy({ dataType: ["Unspecified"] });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.measurementTechnique).toBeUndefined();
  });

  it("omits citation when publications is empty", () => {
    expect(result.citation).toBeUndefined();
  });

  it("includes top 5 most-cited publications", () => {
    const publications = Array.from({ length: 7 }, (_, i) => ({
      authors: `Author ${i}`,
      citationCount: i * 10,
      doi: `10.1234/test${i}`,
      journal: "Journal",
      title: `Paper ${i}`,
      year: 2020 + i,
    }));
    const study = makeStudy({ publications });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.citation).toHaveLength(5);
    expect(jsonLd.citation?.map((c) => c.name)).toEqual([
      "Paper 6",
      "Paper 5",
      "Paper 4",
      "Paper 3",
      "Paper 2",
    ]);
  });

  it("parses multiple authors into Person objects and filters et al.", () => {
    const study = makeStudy({
      publications: [
        {
          authors: "A. Smith, B. Jones, et al.",
          citationCount: 5,
          doi: "10.1234/test",
          journal: "Journal",
          title: "Paper",
          year: 2020,
        },
      ],
    });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.citation?.[0].author).toEqual([
      { "@type": "Person", name: "A. Smith" },
      { "@type": "Person", name: "B. Jones" },
    ]);
  });

  it("omits author and sameAs when not available", () => {
    const study = makeStudy({
      publications: [
        {
          authors: "",
          citationCount: 0,
          doi: "",
          journal: "Journal",
          title: "Untitled Paper",
          year: 2020,
        },
      ],
    });
    const jsonLd = buildStudyJsonLd(study, BROWSER_URL);
    expect(jsonLd.citation?.[0]).toEqual({
      "@type": "ScholarlyArticle",
      headline: "Untitled Paper",
      name: "Untitled Paper",
    });
  });
});
