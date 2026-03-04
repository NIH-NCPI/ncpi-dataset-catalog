import { ComponentConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { NCPICatalogStudy } from "../../../../../app/apis/catalog/ncpi-catalog/common/entities";
import * as C from "../../../../../app/components";
import * as V from "../../../../../app/viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";

export const variablesMainColumn = [
  {
    component: C.Variables,
    viewBuilder: V.buildVariables,
  } as ComponentConfig<typeof C.Variables, NCPICatalogStudy>,
];
