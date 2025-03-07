import { ComponentConfig } from "@databiosphere/findable-ui/lib/config/entities";
import { NCPICatalogStudy } from "../../../../../app/apis/catalog/ncpi-catalog/common/entities";
import * as C from "../../../../../app/components";
import * as V from "../../../../../app/viewModelBuilders/catalog/ncpi-catalog/common/viewModelBuilders";

export const sideColumn = [
  {
    children: [
      {
        component: C.KeyValuePairs,
        viewBuilder: V.buildStudyDetails,
      } as ComponentConfig<typeof C.KeyValuePairs, NCPICatalogStudy>,
    ],
    component: C.GridPaperSection,
  } as ComponentConfig<typeof C.GridPaperSection>,
  {
    children: [
      {
        children: [
          {
            component: C.Link,
            viewBuilder: V.buildViewInAnVIL,
          } as ComponentConfig<typeof C.Link, NCPICatalogStudy>,
        ],
        component: C.GridPaperSection,
      } as ComponentConfig<typeof C.GridPaperSection>,
    ],
    component: C.ConditionalComponent,
    viewBuilder: V.renderWhenPlatformIsAnVIL,
  } as ComponentConfig<typeof C.ConditionalComponent, NCPICatalogStudy>,
  {
    component: C.Details,
    viewBuilder: V.buildStudySummary,
  } as ComponentConfig<typeof C.Details, NCPICatalogStudy>,
];
