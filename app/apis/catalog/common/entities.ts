export interface DbGapStudy {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  description: string;
  focus: string;
  numChildren: number;
  parentStudyId: string | null;
  parentStudyName: string | null;
  participantCount: number;
  studyAccession: string;
  studyDesigns: string[];
  title: string;
}
