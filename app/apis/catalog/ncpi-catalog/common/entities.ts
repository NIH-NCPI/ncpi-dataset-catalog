import { DbGapStudy, Publication } from "../../common/entities";

export enum PLATFORM {
  ANVIL = "AnVIL",
  BDC = "BDC",
  CRDC = "CRDC",
  DBGAP = "dbGaP",
  KFDRC = "KFDRC",
}

export interface PlatformStudy {
  dbGapId: string;
  platform: PLATFORM;
}

export interface NCPIStudy extends DbGapStudy {
  consentLongNames: Record<string, string>;
  duosUrl: string | null;
  platforms: PLATFORM[];
  variableSummary: VariableSummary | null;
}

export type DbGapId = string;

export type NCPICatalogEntity = NCPICatalogPlatform | NCPICatalogStudy;

export interface NCPICatalogPlatform {
  consentCode: string[];
  consentLongName: Record<string, string>;
  dataType: string[];
  dbGapId: string[];
  focus: string[];
  participantCount: number;
  platform: PLATFORM;
  studyAccession: string[];
  studyDesign: string[];
  title: string[];
}

export interface Variable {
  description: string;
  id: string;
  name: string;
}

export interface VariableCategory {
  categoryId: string;
  categoryName: string;
  totalCount: number;
  variables?: Variable[];
}

export interface VariableSummary {
  categories: VariableCategory[];
  classifiedVariables: number;
  totalVariables: number;
}

export interface NCPICatalogStudy {
  consentCode: string[];
  consentLongName: Record<string, string>;
  dataType: string[];
  duosUrl: string | null;
  dbGapId: string;
  focus: string;
  gdcProjectId: string | null;
  participantCount: number;
  platform: PLATFORM[];
  publications: Publication[];
  studyAccession: string;
  studyDescription: string;
  studyDesign: string[];
  title: string;
  variableSummary: VariableSummary | null;
}
