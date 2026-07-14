import type { NCPICatalogStudy } from "../../apis/catalog/ncpi-catalog/common/entities";

export interface Props {
  publicationsCount: number;
  researchType: string;
  study: NCPICatalogStudy;
  subpath: string;
  variablesCount: number;
}
