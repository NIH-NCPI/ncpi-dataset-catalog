export const tsvPath = "./catalog-build/source/dashboard-source-ncpi.tsv";
export const duosCsvPath =
  "./catalog-build/source/duos-studies-by-dbgap-id.csv";
export const dbgapCsvPath =
  "catalog-build/source/2026-01-27-dbgap-advanced-search.csv";

export enum Platform {
  ANVIL = "AnVIL",
  BDC = "BDC",
  CRDC = "CRDC",
  DBGAP = "dbGaP",
  KFDRC = "KFDRC",
}

const SOURCE_HEADER_KEY = {
  DB_GAP_ID: "identifier",
  PLATFORM: "platform",
  STUDY_PHS: "studyPhs",
  STUDY_URL: "studyUrl",
};

export const DUOS_INFO_SOURCE_FIELD_KEY = {
  [SOURCE_HEADER_KEY.STUDY_PHS]: "Study PHS",
  [SOURCE_HEADER_KEY.STUDY_URL]: "Study URL",
};

export const DUOS_INFO_SOURCE_FIELD_TYPE = {
  [SOURCE_HEADER_KEY.STUDY_PHS]: "string",
  [SOURCE_HEADER_KEY.STUDY_URL]: "string",
};

export const SOURCE_FIELD_KEY = {
  [SOURCE_HEADER_KEY.DB_GAP_ID]: "dbGapId",
  [SOURCE_HEADER_KEY.PLATFORM]: "platform",
};

export const SOURCE_FIELD_TYPE = {
  [SOURCE_HEADER_KEY.DB_GAP_ID]: "string",
  [SOURCE_HEADER_KEY.PLATFORM]: "string",
};

// Field mappings for parsing the dbGaP advanced search CSV
const DBGAP_CSV_HEADER_KEY = {
  ACCESSION: "accession",
  DESCRIPTION: "description",
  NAME: "name",
  STUDY_CONSENT: "studyConsent",
  STUDY_CONTENT: "studyContent",
  STUDY_DESIGN: "studyDesign",
  STUDY_DISEASE_FOCUS: "studyDiseaseFocus",
  STUDY_MOLECULAR_DATA_TYPE: "studyMolecularDataType",
};

export const DBGAP_CSV_FIELD_KEY: Record<string, string> = {
  [DBGAP_CSV_HEADER_KEY.ACCESSION]: "accession",
  [DBGAP_CSV_HEADER_KEY.DESCRIPTION]: "description",
  [DBGAP_CSV_HEADER_KEY.NAME]: "name",
  [DBGAP_CSV_HEADER_KEY.STUDY_CONSENT]: "Study Consent",
  [DBGAP_CSV_HEADER_KEY.STUDY_CONTENT]: "Study Content",
  [DBGAP_CSV_HEADER_KEY.STUDY_DESIGN]: "Study Design",
  [DBGAP_CSV_HEADER_KEY.STUDY_DISEASE_FOCUS]: "Study Disease/Focus",
  [DBGAP_CSV_HEADER_KEY.STUDY_MOLECULAR_DATA_TYPE]: "Study Molecular Data Type",
};

export const DBGAP_CSV_FIELD_TYPE: Record<string, string> = {
  [DBGAP_CSV_HEADER_KEY.ACCESSION]: "string",
  [DBGAP_CSV_HEADER_KEY.DESCRIPTION]: "string",
  [DBGAP_CSV_HEADER_KEY.NAME]: "string",
  [DBGAP_CSV_HEADER_KEY.STUDY_CONSENT]: "string",
  [DBGAP_CSV_HEADER_KEY.STUDY_CONTENT]: "string",
  [DBGAP_CSV_HEADER_KEY.STUDY_DESIGN]: "string",
  [DBGAP_CSV_HEADER_KEY.STUDY_DISEASE_FOCUS]: "string",
  [DBGAP_CSV_HEADER_KEY.STUDY_MOLECULAR_DATA_TYPE]: "string",
};
