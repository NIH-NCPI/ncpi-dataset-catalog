import { NCPICatalogStudy } from "../../../../apis/catalog/ncpi-catalog/common/entities";

export interface Props {
  researchType: string;
  study: NCPICatalogStudy;
  studyId: string;
  subpath: string;
}
