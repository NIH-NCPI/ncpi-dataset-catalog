import {
  INTENT,
  MessageResponse,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Variable } from "../ui/Datasets/types/variable";
import { Study } from "../ui/Datasets/types/study";

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
