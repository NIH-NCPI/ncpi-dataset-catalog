export interface DbGapStudy {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  // Optional: dropped from the slimmed studies list artifact (epic #425 stage
  // 3b); present on the full catalog that feeds the detail pages.
  description?: string;
  focus: string;
  gdcProjectId?: string;
  numChildren: number;
  parentStudyId: string | null;
  parentStudyName: string | null;
  participantCount: number;
  // Optional: dropped from the slimmed studies list artifact (epic #425 stage
  // 3b); present on the full catalog that feeds the detail pages.
  publications?: Publication[];
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
