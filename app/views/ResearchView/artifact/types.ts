export const RESEARCH_TYPE = {
  PLAN: "plan",
  RESULTS: "results",
} as const;

export type ResearchType = (typeof RESEARCH_TYPE)[keyof typeof RESEARCH_TYPE];

export interface Props {
  researchType: ResearchType;
}
