export interface StudyIdentity {
  consentCodes: string[];
  consentLongNames: Record<string, string>;
  dbGapId: string;
  platforms: string[];
}
