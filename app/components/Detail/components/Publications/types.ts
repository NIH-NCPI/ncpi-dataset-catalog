import { BaseComponentProps } from "@databiosphere/findable-ui/lib/components/types";
import { Publication } from "../../../../apis/catalog/common/entities";
import { ComponentType } from "react";
import { PaperProps } from "@mui/material";

export interface Props extends BaseComponentProps {
  Paper?: ComponentType<BaseComponentProps & PaperProps>;
  publications: Publication[];
}
