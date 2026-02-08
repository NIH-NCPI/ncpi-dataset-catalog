export interface DbGapStudy {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  description: string;
  focus: string;
  gdcProjectId?: string;
  participantCount: number;
  publications: Publication[];
  studyAccession: string;
  studyDesigns: string[];
  title: string;
}

export interface Publication {
  authors: string;
  citationCount: number;
  doi: string;
  journal: string;
  title: string;
  year: number;
}
