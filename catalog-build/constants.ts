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
