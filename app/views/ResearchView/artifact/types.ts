export const RESEARCH_TYPE = {
  DATASETS: "datasets",
  PLAN: "plan",
} as const;

export type ResearchType = (typeof RESEARCH_TYPE)[keyof typeof RESEARCH_TYPE];

export interface Props {
  researchType: ResearchType;
}
