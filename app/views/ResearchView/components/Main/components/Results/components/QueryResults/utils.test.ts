import {
  type AssistantMessage,
  MESSAGE_TYPE,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import type { TableOptions } from "@tanstack/react-table";
import type { Response } from "../../../../../../types/response";
import type { Study } from "../../types/study";
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

describe("getOptions", () => {
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
