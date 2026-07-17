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

/**
 * Fields the slimmed studies list artifact omits — kept only in the full
 * catalog that feeds the detail pages (epic #425 stage 3b; see
 * scripts/slim-list-artifact.mjs, whose KEEP_FIELDS is the complement of this).
 */
export const SLIM_DROPPED_FIELDS = [
  "description",
  "numChildren",
  "parentStudyId",
  "parentStudyName",
  "publications",
  "variableSummary",
] as const;

/**
 * Input accepted by NCPIStudyInputMapper: either a full NCPIStudy (detail
 * pages, from the full catalog) or a slim studies-list record fetched at
 * runtime, which omits SLIM_DROPPED_FIELDS. Keeping NCPIStudy/DbGapStudy strict
 * means catalog-build still fails to typecheck if it drops any of these from the
 * full catalog; only this mapper boundary tolerates their absence.
 */
export type NCPIStudyMapperInput = Omit<
  NCPIStudy,
  (typeof SLIM_DROPPED_FIELDS)[number]
> &
  Partial<Pick<NCPIStudy, (typeof SLIM_DROPPED_FIELDS)[number]>>;

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
