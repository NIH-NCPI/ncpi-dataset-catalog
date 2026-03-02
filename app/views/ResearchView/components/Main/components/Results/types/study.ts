export interface Demographics {
  computedAncestry: DemographicDistribution | null;
  raceEthnicity: DemographicDistribution | null;
  sex: DemographicDistribution | null;
}

export interface DemographicCategory {
  count: number;
  label: string;
  percent: number;
}

export interface DemographicDistribution {
  categories: DemographicCategory[];
  n: number;
}

export interface Study {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  demographics: Demographics | null;
  focus: string;
  participantCount: number | null;
  platforms: string[];
  studyDesigns: string[];
  title: string;
}
