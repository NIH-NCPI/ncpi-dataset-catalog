import type { ColumnDef } from "@tanstack/react-table";
import { buildHiddenColumnVisibility } from "./utils";

interface Row {
  a: string;
  b: string;
}

describe("buildHiddenColumnVisibility", () => {
  it("maps each column id to false", () => {
    const columns: ColumnDef<Row>[] = [
      { accessorKey: "a", id: "a" },
      { accessorKey: "b", id: "renamedB" },
    ];
    expect(buildHiddenColumnVisibility(columns)).toEqual({
      a: false,
      renamedB: false,
    });
  });

  it("returns an empty state for no columns", () => {
    expect(buildHiddenColumnVisibility([])).toEqual({});
  });
});
