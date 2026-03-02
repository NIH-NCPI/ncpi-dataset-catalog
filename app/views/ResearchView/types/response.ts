import {
  INTENT,
  MessageResponse,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Variable } from "../components/Main/components/Results/types/variable";
import { Study } from "../components/Main/components/Results/types/study";

export const INTENTS = {
  AUTO: INTENT.AUTO,
  STUDY: "study",
  VARIABLE: "variable",
} as const;

export interface Response extends MessageResponse {
  intent: (typeof INTENTS)[keyof typeof INTENTS];
  studies: Study[];
  totalStudies: number;
  totalVariables: number;
  variables: Variable[];
}
