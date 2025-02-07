export interface AnVILCatalogStudy {
  bucketSize: number;
  consentCode: string[];
  consentLongName: Record<string, string>;
  consortium: string;
  dataType: string[];
  dbGapId: string;
  disease: string[];
  participantCount: number;
  studyAccession: string;
  studyDescription: string;
  studyDesign: string[];
  studyName: string;
  workspaceCount: number;
  workspaceName: string[];
  workspaces: AnVILCatalogWorkspace[];
}

export interface AnVILCatalogWorkspace {
  bucketSize: number;
  consentCode: string;
  consentLongName: Record<string, string>;
  consortium: string;
  dataType: string[];
  dbGapId: string;
  disease: string[];
  participantCount: number;
  studyAccession: string;
  studyDesign: string[];
  studyName: string;
  workspaceName: string;
}
