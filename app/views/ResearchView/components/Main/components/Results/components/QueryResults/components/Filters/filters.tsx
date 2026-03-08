import { Fragment, JSX } from "react";
import { Props } from "./types";
import { Chip, Stack, Typography } from "@mui/material";
import { STACK_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/stack";
import { TYPOGRAPHY_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/typography";
import { getFacet, getFilters } from "./utils";
import { CHIP_PROPS } from "@databiosphere/findable-ui/lib/styles/common/mui/chip";
import { RowData } from "@tanstack/react-table";
import { useMultiTurn } from "../../../../../../../../artifact/form";

/**
 * Filters component to display applied filters from the assistant message.
 * @param props - Component props.
 * @param props.message - Assistant message.
 * @param props.table - Table instance.
 * @returns JSX element displaying the filters or null if no filters are applied.
 */
export const Filters = <T extends RowData>({
  message,
  table,
}: Props<T>): JSX.Element | null => {
  const filters = getFilters(table, message);
  const { removeFilter } = useMultiTurn();

  if (filters.length === 0) return null;

  return (
    <Stack
      alignItems={STACK_PROPS.ALIGN_ITEMS.CENTER}
      direction={STACK_PROPS.DIRECTION.ROW}
      flexWrap={STACK_PROPS.FLEX_WRAP.WRAP}
      gap={2}
      useFlexGap
    >
      <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_500}>
        Filters
      </Typography>
      {filters.map((filter) =>
        filter.value.map((value) => (
          <Chip
            key={`${filter.categoryKey}-${value}`}
            label={
              <Fragment>
                <Typography
                  color={TYPOGRAPHY_PROPS.COLOR.INK_LIGHT}
                  variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_400}
                  sx={{ textTransform: "capitalize" }}
                >
                  {filter.categoryKey}:{" "}
                </Typography>
                <Typography variant={TYPOGRAPHY_PROPS.VARIANT.BODY_SMALL_500}>
                  {String(value)}
                </Typography>
              </Fragment>
            }
            onDelete={(): void =>
              removeFilter(getFacet(table, filter.categoryKey), String(value))
            }
            size={CHIP_PROPS.SIZE.MEDIUM}
          />
        ))
      )}
    </Stack>
  );
};
