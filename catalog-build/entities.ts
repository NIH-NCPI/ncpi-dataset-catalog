/**
 * Represents a row from the dbGaP advanced search CSV export.
 */
export interface DbGapCSVRow {
  accession: string;
  description: string;
  name: string;
  "Study Consent": string;
  "Study Content": string;
  "Study Design": string;
  "Study Disease/Focus": string;
  "Study Molecular Data Type": string;
}

export interface DuosStudyInfo {
  "Study ID": string;
  "Study PHS": string;
  "Study URL": string;
}
