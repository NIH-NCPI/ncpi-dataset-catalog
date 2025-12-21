import { DbGapStudy } from "../../common/entities";

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
  dbGapUrl: string;
  duosUrl: string | null;
  platforms: PLATFORM[];
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

export interface NCPICatalogStudy {
  consentCode: string[];
  consentLongName: Record<string, string>;
  dataType: string[];
  dbGapId: string;
  dbGapUrl: string;
  duosUrl: string | null;
  focus: string;
  participantCount: number;
  platform: PLATFORM[];
  studyAccession: string;
  studyDescription: string;
  studyDesign: string[];
  title: string;
}
