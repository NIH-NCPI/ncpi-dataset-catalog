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
  // Optional: dropped from the slimmed studies list artifact (epic #425 stage
  // 3b); present on the full catalog that feeds the detail pages.
  variableSummary?: VariableSummary | null;
}

// eslint-disable-next-line sonarjs/redundant-type-aliases -- DbGapId is a semantic alias documenting that these strings are dbGaP study identifiers
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
  dbGapId: string;
  duosUrl: string | null;
  focus: string;
  gdcProjectId: string | null;
  participantCount: number;
  platform: PLATFORM[];
  publications: Publication[];
  studyAccession: string;
  // Optional: sourced from the slimmed list artifact for the /studies list
  // (where it is absent — epic #425 stage 3b) and from the full catalog on the
  // detail pages (where it is present).
  studyDescription?: string;
  studyDesign: string[];
  title: string;
  variableSummary: VariableSummary | null;
}
