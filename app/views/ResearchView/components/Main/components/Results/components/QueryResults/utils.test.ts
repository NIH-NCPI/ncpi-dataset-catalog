import {
  type AssistantMessage,
  MESSAGE_TYPE,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import type { RowData, TableOptions } from "@tanstack/react-table";
import { renderHook } from "@testing-library/react";
import type { Response } from "../../../../../../types/response";
import type { Study } from "../../types/study";
import type { Variable } from "../../types/variable";
import { useTable } from "./hooks/UseTable/hook";
import { getOptions } from "./utils";

// The app component barrel pulls in ESM-only markdown dependencies Jest can't
// parse; getOptions never renders a cell, so no component is needed.
jest.mock("../../../../../../../../components", () => ({}));

const STUDY: Study = {
  consentCodes: ["GRU"],
  dataTypes: ["WGS"],
  dbGapId: "phs000001",
  demographics: null,
  focus: "Breast Cancer",
  participantCount: 100,
  platforms: ["AnVIL"],
  studyDesigns: ["Cohort"],
  title: "Shared Title",
};

const VARIABLE: Variable = {
  concept: "topmed:bmi",
  datasetId: "ds1",
  dbGapUrl: "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi",
  description: "Body mass index",
  phvId: "phv00000001.v1.p1",
  studyId: "phs000001",
  studyTitle: "Study",
  studyUrl: "",
  tableName: "baseline",
  variableName: "BMI",
};

/**
 * Builds an assistant message holding the given studies.
 * @param studies - Studies in the response.
 * @param consentLongNames - Response-level consent long names.
 * @returns Assistant message.
 */
function buildMessage(
  studies: Study[],
  consentLongNames?: Record<string, string>
): AssistantMessage<Response> {
  return {
    createdAt: 0,
    response: {
      consentLongNames,
      intent: "study",
      message: null,
      query: { mentions: [], message: null },
      studies,
      timing: { lookupMs: 0, pipelineMs: 0, totalMs: 0 },
      totalStudies: studies.length,
      totalVariables: 0,
      variables: [],
    },
    type: MESSAGE_TYPE.ASSISTANT,
  } as AssistantMessage<Response>;
}

/**
 * Builds an assistant message holding the given variables (and no studies).
 * @param variables - Variables in the response.
 * @returns Assistant message.
 */
function buildVariableMessage(
  variables: Variable[]
): AssistantMessage<Response> {
  const message = buildMessage([]);
  return {
    ...message,
    response: {
      ...message.response,
      intent: "variable",
      totalVariables: variables.length,
      variables,
    },
  };
}

/**
 * Returns the first cell value of each row, in the order the table renders them.
 * @param message - Assistant message.
 * @param key - Row field to read.
 * @returns Row values in display order.
 */
function getDisplayOrder(
  message: AssistantMessage<Response>,
  key: "concept" | "title"
): string[] {
  const { result } = renderHook(() =>
    useTable(getOptions(message) as TableOptions<RowData>)
  );
  return result.current.table
    .getRowModel()
    .rows.map((row) => (row.original as Record<string, string>)[key]);
}

describe("getOptions", () => {
  describe("studies", () => {
    it("gives studies with the same title distinct row ids", () => {
      const studies = [STUDY, { ...STUDY, dbGapId: "phs000002" }];
      const options = getOptions(buildMessage(studies)) as TableOptions<Study>;
      const rowIds = studies.map((study, i) => options.getRowId?.(study, i));
      expect(rowIds).toEqual(["phs000001", "phs000002"]);
    });

    it("hides the dbGaP Id, Platform and Consent Code columns", () => {
      const options = getOptions(buildMessage([STUDY])) as TableOptions<Study>;
      expect(options.initialState?.columnVisibility).toEqual({
        consentCodes: false,
        dbGapId: false,
        platform: false,
      });
    });

    it("starts sorted by the Study column (title), ascending", () => {
      const options = getOptions(buildMessage([STUDY])) as TableOptions<Study>;
      expect(options.initialState?.sorting).toEqual([
        { desc: false, id: "title" },
      ]);
    });

    it("passes the response's consent long names to the table meta", () => {
      const consentLongNames = { GRU: "General Research Use" };
      const options = getOptions(
        buildMessage([STUDY], consentLongNames)
      ) as TableOptions<Study>;
      expect(options.meta).toEqual({ consentLongNames });
    });

    it("falls back to empty consent long names when the response has none", () => {
      const options = getOptions(buildMessage([STUDY])) as TableOptions<Study>;
      expect(options.meta).toEqual({ consentLongNames: {} });
    });
  });

  describe("variables", () => {
    it("hides the Concept and Variable Name columns", () => {
      const options = getOptions(
        buildVariableMessage([VARIABLE])
      ) as TableOptions<Variable>;
      expect(options.initialState?.columnVisibility).toEqual({
        concept: false,
        variableName: false,
      });
    });

    it("starts sorted by the Variable column (concept), ascending", () => {
      const options = getOptions(
        buildVariableMessage([VARIABLE])
      ) as TableOptions<Variable>;
      expect(options.initialState?.sorting).toEqual([
        { desc: false, id: "variable" },
      ]);
    });

    it("leads with the Variable column, with Concept and Variable Name hidden after it", () => {
      const options = getOptions(
        buildVariableMessage([VARIABLE])
      ) as TableOptions<Variable>;
      expect(options.columns.map(({ id }) => id)).toEqual([
        "variable",
        "concept",
        "variableName",
        "description",
        "studyTitle",
        "dbGapUrl",
      ]);
    });
  });
});

describe("research table display order", () => {
  // TanStack's "auto" sorting picks a case-sensitive sort for 10 or fewer rows,
  // which would put "eMERGE" after "Zebrafish".
  it("sorts a short study list by title, ignoring case", () => {
    const studies = ["Zebrafish", "eMERGE", "Asthma"].map((title, i) => ({
      ...STUDY,
      dbGapId: `phs00000${i}`,
      title,
    }));
    expect(getDisplayOrder(buildMessage(studies), "title")).toEqual([
      "Asthma",
      "eMERGE",
      "Zebrafish",
    ]);
  });

  it("sorts a short variable list by concept, ignoring case", () => {
    const variables = ["zinc", "Glucose", "bmi"].map((concept) => ({
      ...VARIABLE,
      concept,
    }));
    expect(getDisplayOrder(buildVariableMessage(variables), "concept")).toEqual(
      ["bmi", "Glucose", "zinc"]
    );
  });

  // Must match the backend's ORDER BY LOWER(concept) (case-insensitive,
  // lexical), so its 500-row LIMIT keeps the rows the table shows first.
  it("sorts variables lexically like the backend, not naturally", () => {
    const variables = ["topmed:il6", "Topmed:zinc", "topmed:il10"].map(
      (concept) => ({ ...VARIABLE, concept })
    );
    expect(getDisplayOrder(buildVariableMessage(variables), "concept")).toEqual(
      ["topmed:il10", "topmed:il6", "Topmed:zinc"]
    );
  });
});
