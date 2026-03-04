import { VariableSummary } from "../../../../apis/catalog/ncpi-catalog/common/entities";

export interface Props {
  studyAccession: string;
  variableSummary: VariableSummary | null;
}
