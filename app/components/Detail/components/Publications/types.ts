import { BaseComponentProps } from "@databiosphere/findable-ui/lib/components/types";
import { PaperProps } from "@mui/material";
import { ComponentType } from "react";
import { Publication } from "../../../../apis/catalog/common/entities";

export interface Props extends BaseComponentProps {
  Paper?: ComponentType<BaseComponentProps & PaperProps>;
  publications: Publication[];
}
