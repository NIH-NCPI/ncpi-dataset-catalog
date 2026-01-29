// Mock dependencies that use ESM syntax
jest.mock("node-fetch", () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock("./dbGaP", () => ({
  markdownToHTML: jest.fn((s: string) => s),
}));

jest.mock("./utils", () => ({
  delayFetch: jest.fn(),
}));

import {
  getLatestVersionXmlUrl,
  parseCommaSeparated,
  parseConsentCodes,
  parseDataTypes,
  parseDescriptionFromXml,
  parseFocusDisease,
  parseParticipantCount,
  parseStudyDesigns,
  parseVersionsFromHtml,
  processDescription,
  sortVersions,
} from "./dbGapCSVandFTP";

describe("parseConsentCodes", () => {
  it("parses multiple consent codes with complex descriptions", () => {
    const input =
      "DS-CRM-PUB-MDS --- Disease-Specific (Cancer Research and Methods, PUB, MDS), GRU --- General Research Use";
    expect(parseConsentCodes(input)).toEqual(["DS-CRM-PUB-MDS", "GRU"]);
  });

  it("parses consent codes with nested parentheses containing commas", () => {
    const input =
      "HMB-IRB-NPU --- Health/Medical/Biomedical (IRB, NPU), DS-FDO-IRB-NPU --- Disease-Specific (Focused Disease Only, IRB, NPU), HMB-IRB --- Health/Medical/Biomedical (IRB), DS-FDO-IRB --- Disease-Specific (Focused Disease Only, IRB)";
    expect(parseConsentCodes(input)).toEqual([
      "HMB-IRB-NPU",
      "DS-FDO-IRB-NPU",
      "HMB-IRB",
      "DS-FDO-IRB",
    ]);
  });

  it("parses a single consent code", () => {
    const input = "GRU --- General Research Use";
    expect(parseConsentCodes(input)).toEqual(["GRU"]);
  });

  it("returns empty array for 'Not Provided'", () => {
    expect(parseConsentCodes("Not Provided")).toEqual([]);
  });

  it("returns empty array for empty string", () => {
    expect(parseConsentCodes("")).toEqual([]);
  });

  it("returns empty array for null/undefined input", () => {
    expect(parseConsentCodes(null as unknown as string)).toEqual([]);
    expect(parseConsentCodes(undefined as unknown as string)).toEqual([]);
  });

  it("parses consent codes with PUB suffix", () => {
    const input =
      "DS-CA-PUB --- Disease-Specific (Cancer, PUB), HMB-PUB --- Health/Medical/Biomedical (PUB)";
    expect(parseConsentCodes(input)).toEqual(["DS-CA-PUB", "HMB-PUB"]);
  });

  it("parses consent codes with IRB and COL modifiers", () => {
    const input = "HMB-IRB-COL --- Health/Medical/Biomedical (IRB, COL)";
    expect(parseConsentCodes(input)).toEqual(["HMB-IRB-COL"]);
  });

  it("handles descriptions with commas outside parentheses", () => {
    const input =
      "HMB-PUB --- Health/Medical/Biomedical (PUB), GRU --- General Research Use, CADM --- Cancer in all age groups, other diseases in adults only, and methods, DS-CA-MDS --- Disease-Specific (Cancer, MDS), HMB --- Health/Medical/Biomedical, HMB-IRB-NPU-GSO --- Health/Medical/Biomedical (IRB, NPU, GSO), DS-COC-MDS --- Disease-Specific (Colon Cancer, MDS)";
    expect(parseConsentCodes(input)).toEqual([
      "HMB-PUB",
      "GRU",
      "CADM",
      "DS-CA-MDS",
      "HMB",
      "HMB-IRB-NPU-GSO",
      "DS-COC-MDS",
    ]);
  });
});

describe("parseParticipantCount", () => {
  it("parses subject count from standard format", () => {
    const input =
      "4 phenotype datasets, 21 variables, 1 molecular datasets, 705 subjects, 705 samples";
    expect(parseParticipantCount(input)).toBe(705);
  });

  it("parses subject count when samples sequenced appears before subjects", () => {
    const input =
      "7 phenotype datasets, 38 variables, 3 molecular datasets, 7173 samples sequenced, 1290 subjects, 9876 samples";
    expect(parseParticipantCount(input)).toBe(1290);
  });

  it("parses large subject counts", () => {
    const input =
      "4 phenotype datasets, 24 variables, 2 molecular datasets, 61182 subjects, 61182 samples";
    expect(parseParticipantCount(input)).toBe(61182);
  });

  it("returns 0 for empty string", () => {
    expect(parseParticipantCount("")).toBe(0);
  });

  it("returns 0 for null/undefined input", () => {
    expect(parseParticipantCount(null as unknown as string)).toBe(0);
    expect(parseParticipantCount(undefined as unknown as string)).toBe(0);
  });

  it("returns 0 when no subjects field present", () => {
    const input = "4 phenotype datasets, 21 variables";
    expect(parseParticipantCount(input)).toBe(0);
  });

  it("parses subject count with minimal format", () => {
    const input = "100 subjects";
    expect(parseParticipantCount(input)).toBe(100);
  });

  it("handles single subject", () => {
    const input = "1 subjects, 1 samples";
    expect(parseParticipantCount(input)).toBe(1);
  });
});

describe("parseCommaSeparated", () => {
  it("parses many data types including duplicates", () => {
    const input =
      "Allele-Specific Expression, Allele-Specific Expression, SNP Genotypes (Array), mRNA Expression (Array), SNP Genotypes (imputed), RNA-Seq, CNV Genotypes, SNP/CNV Genotypes (NGS), RNA Seq (NGS), MAF (NGS), WGS, WXS";
    expect(parseCommaSeparated(input)).toEqual([
      "Allele-Specific Expression",
      "Allele-Specific Expression",
      "SNP Genotypes (Array)",
      "mRNA Expression (Array)",
      "SNP Genotypes (imputed)",
      "RNA-Seq",
      "CNV Genotypes",
      "SNP/CNV Genotypes (NGS)",
      "RNA Seq (NGS)",
      "MAF (NGS)",
      "WGS",
      "WXS",
    ]);
  });

  it("parses two data types", () => {
    const input = "SNP Genotypes (Array), RNA-Seq";
    expect(parseCommaSeparated(input)).toEqual([
      "SNP Genotypes (Array)",
      "RNA-Seq",
    ]);
  });

  it("parses three data types with NGS variants", () => {
    const input = "SNP/CNV Genotypes (NGS), CNV (NGS), WGS";
    expect(parseCommaSeparated(input)).toEqual([
      "SNP/CNV Genotypes (NGS)",
      "CNV (NGS)",
      "WGS",
    ]);
  });

  it("parses a single value", () => {
    const input = "WGS";
    expect(parseCommaSeparated(input)).toEqual(["WGS"]);
  });

  it("returns empty array for 'Not Provided'", () => {
    expect(parseCommaSeparated("Not Provided")).toEqual([]);
  });

  it("returns empty array for empty string", () => {
    expect(parseCommaSeparated("")).toEqual([]);
  });

  it("returns empty array for null/undefined input", () => {
    expect(parseCommaSeparated(null as unknown as string)).toEqual([]);
    expect(parseCommaSeparated(undefined as unknown as string)).toEqual([]);
  });

  it("trims whitespace from values", () => {
    const input = "  WGS  ,  RNA-Seq  ,  WXS  ";
    expect(parseCommaSeparated(input)).toEqual(["WGS", "RNA-Seq", "WXS"]);
  });
});

describe("parseDataTypes", () => {
  it("parses data types and removes duplicates", () => {
    const input =
      "Allele-Specific Expression, Allele-Specific Expression, SNP Genotypes (Array), mRNA Expression (Array), SNP Genotypes (imputed), RNA-Seq, CNV Genotypes, SNP/CNV Genotypes (NGS), RNA Seq (NGS), MAF (NGS), WGS, WXS";
    expect(parseDataTypes(input)).toEqual([
      "Allele-Specific Expression",
      "SNP Genotypes (Array)",
      "mRNA Expression (Array)",
      "SNP Genotypes (imputed)",
      "RNA-Seq",
      "CNV Genotypes",
      "SNP/CNV Genotypes (NGS)",
      "RNA Seq (NGS)",
      "MAF (NGS)",
      "WGS",
      "WXS",
    ]);
  });

  it("parses two data types", () => {
    const input = "SNP Genotypes (Array), RNA-Seq";
    expect(parseDataTypes(input)).toEqual(["SNP Genotypes (Array)", "RNA-Seq"]);
  });

  it("parses three data types with NGS variants", () => {
    const input = "SNP/CNV Genotypes (NGS), CNV (NGS), WGS";
    expect(parseDataTypes(input)).toEqual([
      "SNP/CNV Genotypes (NGS)",
      "CNV (NGS)",
      "WGS",
    ]);
  });

  it("returns empty array for 'Not Provided'", () => {
    expect(parseDataTypes("Not Provided")).toEqual([]);
  });

  it("returns empty array for empty string", () => {
    expect(parseDataTypes("")).toEqual([]);
  });

  it("removes multiple duplicates", () => {
    const input = "WGS, WGS, WGS, RNA-Seq, RNA-Seq";
    expect(parseDataTypes(input)).toEqual(["WGS", "RNA-Seq"]);
  });
});

describe("parseFocus", () => {
  it("preserves commas within focus value", () => {
    expect(parseFocusDisease("Carcinoma, Merkel Cell")).toBe(
      "Carcinoma, Merkel Cell"
    );
  });

  it("returns simple focus value as-is", () => {
    expect(parseFocusDisease("Cancer")).toBe("Cancer");
  });

  it("returns empty string for 'Not Provided'", () => {
    expect(parseFocusDisease("Not Provided")).toBe("");
  });

  it("returns empty string for empty input", () => {
    expect(parseFocusDisease("")).toBe("");
  });

  it("returns empty string for null/undefined input", () => {
    expect(parseFocusDisease(null as unknown as string)).toBe("");
    expect(parseFocusDisease(undefined as unknown as string)).toBe("");
  });
});

describe("parseStudyDesigns", () => {
  it("wraps Case-Control in array", () => {
    expect(parseStudyDesigns("Case-Control")).toEqual(["Case-Control"]);
  });

  it("wraps Prospective Longitudinal Cohort in array", () => {
    expect(parseStudyDesigns("Prospective Longitudinal Cohort")).toEqual([
      "Prospective Longitudinal Cohort",
    ]);
  });

  it("wraps Family/Twin/Trios in array", () => {
    expect(parseStudyDesigns("Family/Twin/Trios")).toEqual([
      "Family/Twin/Trios",
    ]);
  });

  it("wraps Tumor vs. Matched-Normal in array", () => {
    expect(parseStudyDesigns("Tumor vs. Matched-Normal")).toEqual([
      "Tumor vs. Matched-Normal",
    ]);
  });

  it("returns empty array for 'Not Provided'", () => {
    expect(parseStudyDesigns("Not Provided")).toEqual([]);
  });

  it("returns empty array for empty string", () => {
    expect(parseStudyDesigns("")).toEqual([]);
  });

  it("returns empty array for null/undefined input", () => {
    expect(parseStudyDesigns(null as unknown as string)).toEqual([]);
    expect(parseStudyDesigns(undefined as unknown as string)).toEqual([]);
  });
});

describe("processDescription", () => {
  it("returns empty string for empty input", () => {
    expect(processDescription("")).toBe("");
  });

  it("returns empty string for null/undefined input", () => {
    expect(processDescription(null as unknown as string)).toBe("");
    expect(processDescription(undefined as unknown as string)).toBe("");
  });

  it("replaces tabs with spaces", () => {
    const input = "This\tis\ta\ttest";
    expect(processDescription(input)).toContain("This is a test");
  });

  it("replaces newline-newline-tab sequences with spaces", () => {
    const input = "First paragraph\n\n\tSecond paragraph";
    expect(processDescription(input)).toContain("First paragraph Second");
  });

  it("converts internal dbGaP study links to external links", () => {
    const input = "See study.cgi?study_id=phs000123 for details";
    const result = processDescription(input);
    expect(result).toContain(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=phs000123"
    );
    // The original relative link pattern should be gone
    expect(result).not.toMatch(/(?<!\/)study\.cgi\?study_id=/);
  });

  it("converts relative dbGaP study links to external links", () => {
    const input = "See ./study.cgi?study_id=phs000456 for details";
    const result = processDescription(input);
    expect(result).toContain(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=phs000456"
    );
    // The ./ prefix should be gone
    expect(result).not.toContain("./study.cgi");
  });

  it("passes through plain text", () => {
    const input = "Simple description text";
    const result = processDescription(input);
    expect(result).toContain("Simple description text");
  });

  it("handles multiple replacements in one string", () => {
    const input =
      "See study.cgi?study_id=phs001\tand\t./study.cgi?study_id=phs002";
    const result = processDescription(input);
    expect(result).toContain(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=phs001"
    );
    expect(result).toContain(
      "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=phs002"
    );
    expect(result).not.toContain("\t");
  });
});

describe("parseVersionsFromHtml", () => {
  it("parses single version from HTML", () => {
    const html = `<a href="phs000220.v1.p1/">link</a>`;
    expect(parseVersionsFromHtml(html, "phs000220")).toEqual(["v1.p1"]);
  });

  it("parses multiple versions from HTML", () => {
    const html = `
      <a href="phs000220.v1.p1/">link1</a>
      <a href="phs000220.v2.p2/">link2</a>
      <a href="phs000220.v3.p1/">link3</a>
    `;
    expect(parseVersionsFromHtml(html, "phs000220")).toEqual([
      "v1.p1",
      "v2.p2",
      "v3.p1",
    ]);
  });

  it("returns empty array when no versions found", () => {
    const html = `<a href="other-file.txt">other-file.txt</a>`;
    expect(parseVersionsFromHtml(html, "phs000220")).toEqual([]);
  });

  it("only matches the specified phsId", () => {
    const html = `
      <a href="phs000220.v1.p1/">link1</a>
      <a href="phs000999.v2.p1/">link2</a>
    `;
    expect(parseVersionsFromHtml(html, "phs000220")).toEqual(["v1.p1"]);
  });

  it("handles double-digit version numbers", () => {
    const html = `
      <a href="phs000220.v10.p2/">link1</a>
      <a href="phs000220.v9.p1/">link2</a>
    `;
    expect(parseVersionsFromHtml(html, "phs000220")).toEqual([
      "v10.p2",
      "v9.p1",
    ]);
  });

  it("returns empty array for empty HTML", () => {
    expect(parseVersionsFromHtml("", "phs000220")).toEqual([]);
  });
});

describe("sortVersions", () => {
  it("sorts versions with latest first", () => {
    const versions = ["v1.p1", "v2.p2", "v3.p1"];
    expect(sortVersions(versions)).toEqual(["v3.p1", "v2.p2", "v1.p1"]);
  });

  it("handles single version", () => {
    expect(sortVersions(["v1.p1"])).toEqual(["v1.p1"]);
  });

  it("handles empty array", () => {
    expect(sortVersions([])).toEqual([]);
  });

  it("sorts by version number primarily", () => {
    const versions = ["v1.p2", "v2.p1"];
    expect(sortVersions(versions)).toEqual(["v2.p1", "v1.p2"]);
  });

  it("sorts by participant number secondarily", () => {
    const versions = ["v2.p1", "v2.p3", "v2.p2"];
    expect(sortVersions(versions)).toEqual(["v2.p3", "v2.p2", "v2.p1"]);
  });

  it("handles double-digit version numbers correctly", () => {
    const versions = ["v9.p1", "v10.p1", "v2.p1"];
    expect(sortVersions(versions)).toEqual(["v10.p1", "v9.p1", "v2.p1"]);
  });

  it("does not mutate original array", () => {
    const versions = ["v1.p1", "v2.p1"];
    sortVersions(versions);
    expect(versions).toEqual(["v1.p1", "v2.p1"]);
  });
});

describe("getLatestVersionXmlUrl", () => {
  it("returns URL for the latest version", () => {
    const versions = ["v1.p1", "v2.p2", "v3.p1"];
    const result = getLatestVersionXmlUrl("phs000220", versions);
    expect(result).toBe(
      "https://ftp.ncbi.nlm.nih.gov/dbgap/studies/phs000220/phs000220.v3.p1/GapExchange_phs000220.v3.p1.xml"
    );
  });

  it("handles single version", () => {
    const result = getLatestVersionXmlUrl("phs000123", ["v1.p1"]);
    expect(result).toBe(
      "https://ftp.ncbi.nlm.nih.gov/dbgap/studies/phs000123/phs000123.v1.p1/GapExchange_phs000123.v1.p1.xml"
    );
  });

  it("returns null for empty versions array", () => {
    expect(getLatestVersionXmlUrl("phs000220", [])).toBeNull();
  });

  it("handles double-digit version numbers", () => {
    const versions = ["v9.p1", "v10.p2"];
    const result = getLatestVersionXmlUrl("phs000456", versions);
    expect(result).toBe(
      "https://ftp.ncbi.nlm.nih.gov/dbgap/studies/phs000456/phs000456.v10.p2/GapExchange_phs000456.v10.p2.xml"
    );
  });

  it("sorts unsorted versions and picks latest", () => {
    const versions = ["v3.p1", "v1.p1", "v2.p2"];
    const result = getLatestVersionXmlUrl("phs000789", versions);
    expect(result).toBe(
      "https://ftp.ncbi.nlm.nih.gov/dbgap/studies/phs000789/phs000789.v3.p1/GapExchange_phs000789.v3.p1.xml"
    );
  });
});

describe("parseDescriptionFromXml", () => {
  it("extracts description from CDATA section", () => {
    const xml = `
      <Configuration>
        <Description><![CDATA[This is the study description.]]></Description>
      </Configuration>
    `;
    expect(parseDescriptionFromXml(xml)).toBe("This is the study description.");
  });

  it("extracts description without CDATA", () => {
    const xml = `
      <Configuration>
        <Description>This is a plain description.</Description>
      </Configuration>
    `;
    expect(parseDescriptionFromXml(xml)).toBe("This is a plain description.");
  });

  it("handles multiline description in CDATA", () => {
    const xml = `
      <Configuration>
        <Description><![CDATA[
          This is a multiline
          study description with
          several lines.
        ]]></Description>
      </Configuration>
    `;
    const result = parseDescriptionFromXml(xml);
    expect(result).toContain("multiline");
    expect(result).toContain("several lines");
  });

  it("trims whitespace from description", () => {
    const xml = `<Description><![CDATA[   trimmed   ]]></Description>`;
    expect(parseDescriptionFromXml(xml)).toBe("trimmed");
  });

  it("returns null when no Description element found", () => {
    const xml = `<Configuration><Title>Study Title</Title></Configuration>`;
    expect(parseDescriptionFromXml(xml)).toBeNull();
  });

  it("returns null for empty Description element", () => {
    const xml = `<Description></Description>`;
    // Empty content is treated as no description
    expect(parseDescriptionFromXml(xml)).toBeNull();
  });

  it("prefers CDATA over plain text pattern", () => {
    const xml = `<Description><![CDATA[CDATA content]]></Description>`;
    expect(parseDescriptionFromXml(xml)).toBe("CDATA content");
  });
});
