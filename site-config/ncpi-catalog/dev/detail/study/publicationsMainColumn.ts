import { ComponentConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { NCPICatalogStudy } from "../../../../../app/apis/catalog/ncpi-catalog/common/entities";
import * as C from "../../../../../app/components";
import * as V from "../../../../../app/viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";

export const publicationsMainColumn = [
  {
    component: C.Publications,
    viewBuilder: V.buildPublications,
  } as ComponentConfig<typeof C.Publications, NCPICatalogStudy>,
];
