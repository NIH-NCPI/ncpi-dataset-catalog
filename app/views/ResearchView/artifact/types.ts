export const RESEARCH_TYPE = {
  PLAN: "plan",
  RESULTS: "datasets",
} as const;

export type ResearchType = (typeof RESEARCH_TYPE)[keyof typeof RESEARCH_TYPE];

export interface Props {
  researchType: ResearchType;
}
