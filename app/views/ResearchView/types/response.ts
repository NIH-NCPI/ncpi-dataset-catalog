import {
  INTENT,
  MessageResponse,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Study } from "../components/Main/components/Results/types/study";
import { Variable } from "../components/Main/components/Results/types/variable";

export const INTENTS = {
  AUTO: INTENT.AUTO,
  STUDY: "study",
  VARIABLE: "variable",
} as const;

export interface Response extends MessageResponse {
  // Optional so the page still renders against a backend that predates it.
  consentLongNames?: Record<string, string>;
  intent: (typeof INTENTS)[keyof typeof INTENTS];
  studies: Study[];
  totalStudies: number;
  totalVariables: number;
  variables: Variable[];
}
