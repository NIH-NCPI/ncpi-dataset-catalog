/**
 * Represents a row from the dbGaP advanced search CSV export.
 * Keys are sorted alphabetically (case-insensitive) per lint rules.
 */
export interface DbGapCSVRow {
  accession: string;
  "Ancestry (computed)": string;
  Collections: string;
  description: string;
  "Embargo Release Date": string;
  name: string;
  "NIH Institute": string;
  "Parent study": string;
  "Related Terms": string;
  "Release Date": string;
  "Study Consent": string;
  "Study Content": string;
  "Study Design": string;
  "Study Disease/Focus": string;
  "Study Markerset": string;
  "Study Molecular Data Type": string;
}

export interface DuosStudyInfo {
  "Study ID": string;
  "Study PHS": string;
  "Study URL": string;
}
