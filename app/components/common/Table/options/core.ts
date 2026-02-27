import { CoreOptions, getCoreRowModel, RowData } from "@tanstack/react-table";
import { ROW_PREVIEW } from "@databiosphere/findable-ui/lib/components/Table/features/RowPreview/constants";

export const CORE_OPTIONS: Pick<
  CoreOptions<RowData>,
  "_features" | "getCoreRowModel"
> = {
  _features: [ROW_PREVIEW],
  getCoreRowModel: getCoreRowModel(),
};
