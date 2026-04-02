/* eslint-disable @typescript-eslint/no-explicit-any -- test mocks require flexible typing */
/* eslint-disable @typescript-eslint/explicit-function-return-type -- test helpers */
import { act, renderHook } from "@testing-library/react";
import { FormEvent, ReactNode, useContext } from "react";
import { QueryContext } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/context";
import { MultiTurnContext, MultiTurnQueryProvider } from "./form";

// --- Mocks ---

const mockDispatch = {
  onSetError: jest.fn(),
  onSetMessage: jest.fn(),
  onSetQuery: jest.fn(),
  onSetStatus: jest.fn(),
};

const mockChatState = {
  state: { messages: [], status: { loading: false } },
};

jest.mock("@databiosphere/findable-ui/lib/hooks/useConfig", () => ({
  useConfig: (): any => ({
    config: { ai: { url: "https://test-api/search" } },
  }),
}));

jest.mock(
  "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatDispatch/hook",
  () => ({
    useChatDispatch: (): any => mockDispatch,
  })
);

jest.mock(
  "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook",
  () => ({
    useChatState: (): any => mockChatState,
  })
);

jest.mock(
  "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards",
  () => ({
    isAssistantMessage: (m: any): boolean => m?.type === "ASSISTANT",
  })
);

jest.mock("../../../utils/searchApiUrl", () => ({
  getSearchApiUrl: (url: string): string => url,
}));

// --- Helpers ---

const mockFormEvent = (): FormEvent<HTMLFormElement> =>
  ({
    currentTarget: { reset: jest.fn() } as unknown as HTMLFormElement,
    preventDefault: jest.fn(),
    target: { reset: jest.fn() } as unknown as EventTarget,
  }) as unknown as FormEvent<HTMLFormElement>;

const defaultOptions = {
  status: { loading: false },
};

/**
 * Returns onSubmit from QueryContext as provided by MultiTurnQueryProvider.
 * @returns Hook result with onSubmit.
 */
function renderOnSubmit() {
  return renderHook(() => useContext(QueryContext), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <MultiTurnQueryProvider>{children}</MultiTurnQueryProvider>
    ),
  });
}

// --- Tests ---

describe("MultiTurnQueryProvider onSubmit", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockChatState.state.messages = [];
    global.fetch = jest.fn().mockResolvedValue({
      json: () =>
        Promise.resolve({
          intent: "study",
          message: null,
          query: {
            intent: "study",
            mentions: [
              { facet: "focus", originalText: "diabetes", values: ["DM"] },
            ],
            message: null,
          },
          timing: { lookupMs: 0, pipelineMs: 0, totalMs: 0 },
        }),
      ok: true,
      status: 200,
    });
  });

  it("sends only query on first submission (no previousQuery)", async () => {
    const { result } = renderOnSubmit();

    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        defaultOptions
      );
    });

    const body = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body);
    expect(body).toEqual({ query: "diabetes studies" });
    expect(body).not.toHaveProperty("previousQuery");
  });

  it("sends previousQuery on follow-up after first response", async () => {
    const { result } = renderOnSubmit();

    // First query — sets lastQueryRef via response.
    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        defaultOptions
      );
    });

    // Simulate assistant message arriving (syncs lastQueryRef).
    act(() => {
      mockChatState.state.messages = [
        {
          response: {
            intent: "study",
            message: null,
            query: {
              intent: "study",
              mentions: [
                { facet: "focus", originalText: "diabetes", values: ["DM"] },
              ],
              message: null,
            },
            timing: { lookupMs: 0, pipelineMs: 0, totalMs: 0 },
          },
          type: "ASSISTANT",
        },
      ] as any;
    });

    // Re-render to pick up the message change.
    const { result: result2 } = renderOnSubmit();

    // Second query — should include previousQuery.
    await act(async () => {
      await result2.current.onSubmit(
        mockFormEvent(),
        { query: "also where BMI was measured" },
        defaultOptions
      );
    });

    const calls = (global.fetch as jest.Mock).mock.calls;
    const secondBody = JSON.parse(calls[calls.length - 1][1].body);
    expect(secondBody.query).toBe("also where BMI was measured");
    expect(secondBody).toHaveProperty("previousQuery");
    expect(secondBody.previousQuery.mentions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ facet: "focus", originalText: "diabetes" }),
      ])
    );
  });

  it("preserves disambiguation in previousQuery for follow-up responses", async () => {
    // First response includes disambiguation in mentions (as the real backend returns).
    const disambiguationResponse = {
      intent: "study",
      message: "Which did you mean?",
      query: {
        intent: "study",
        mentions: [
          {
            disambiguation: [
              {
                conceptId: "topmed:nutrient_intake",
                facet: "measurement",
                label: "Glucose Intake from Diet",
              },
              {
                conceptId: "Diabetes Mellitus",
                facet: "focus",
                label: "Diabetes Mellitus",
              },
            ],
            exclude: false,
            facet: "focus",
            matchedVariables: [],
            message: null,
            originalText: "glucose",
            values: [],
          },
          {
            disambiguation: [],
            exclude: false,
            facet: "platform",
            matchedVariables: [],
            message: null,
            originalText: "BDC",
            values: ["BDC"],
          },
        ],
        message: null,
      },
      timing: { lookupMs: 0, pipelineMs: 0, totalMs: 0 },
    };
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      json: () => Promise.resolve(disambiguationResponse),
      ok: true,
      status: 200,
    });

    const { result } = renderOnSubmit();

    // First query — response has disambiguation.
    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "glucose on BDC" },
        defaultOptions
      );
    });

    // Second query — previousQuery should include disambiguation.
    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "glucose intake" },
        defaultOptions
      );
    });

    const calls = (global.fetch as jest.Mock).mock.calls;
    const secondBody = JSON.parse(calls[1][1].body);
    expect(secondBody).toHaveProperty("previousQuery");
    const glucoseMention = secondBody.previousQuery.mentions.find(
      (m: any) => m.originalText === "glucose"
    );
    expect(glucoseMention).toBeDefined();
    expect(glucoseMention.disambiguation).toHaveLength(2);
    expect(glucoseMention.disambiguation[0].conceptId).toBe(
      "topmed:nutrient_intake"
    );
  });

  it("updates lastQueryRef from response for subsequent calls", async () => {
    const { result } = renderOnSubmit();

    // First query.
    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        defaultOptions
      );
    });

    // The onSubmit itself updates lastQueryRef from the response (line 145).
    // Second query should carry that forward.
    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "also on AnVIL" },
        defaultOptions
      );
    });

    const calls = (global.fetch as jest.Mock).mock.calls;
    const secondBody = JSON.parse(calls[1][1].body);
    expect(secondBody).toHaveProperty("previousQuery");
  });

  it("does not submit when loading", async () => {
    const { result } = renderOnSubmit();

    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "test" },
        {
          status: { loading: true },
        }
      );
    });

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("does not submit whitespace-only queries", async () => {
    const { result } = renderOnSubmit();

    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "   " },
        defaultOptions
      );
    });

    expect(global.fetch).not.toHaveBeenCalled();
  });
});

describe("MultiTurnQueryProvider removeFilter", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockChatState.state.messages = [
      {
        response: {
          intent: "study",
          message: null,
          query: {
            intent: "study",
            mentions: [
              { facet: "focus", originalText: "diabetes", values: ["DM"] },
              {
                facet: "platform",
                originalText: "AnVIL",
                values: ["AnVIL"],
              },
            ],
            message: null,
          },
          timing: { lookupMs: 0, pipelineMs: 0, totalMs: 0 },
        },
        type: "ASSISTANT",
      },
    ] as any;
    global.fetch = jest.fn().mockResolvedValue({
      json: () =>
        Promise.resolve({
          intent: "study",
          message: null,
          query: {
            intent: "study",
            mentions: [
              { facet: "focus", originalText: "diabetes", values: ["DM"] },
            ],
            message: null,
          },
          timing: { lookupMs: 0, pipelineMs: 0, totalMs: 0 },
        }),
      ok: true,
      status: 200,
    });
  });

  it("sends requery with previousQuery and empty query", async () => {
    const { result } = renderHook(() => useContext(MultiTurnContext), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MultiTurnQueryProvider>{children}</MultiTurnQueryProvider>
      ),
    });

    await act(async () => {
      result.current.removeFilter("platform", "AnVIL");
      // Allow the postSearch promise to resolve.
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body);
    expect(body.query).toBe("");
    expect(body).toHaveProperty("previousQuery");
    expect(body.previousQuery.mentions).toEqual([
      expect.objectContaining({ facet: "focus", originalText: "diabetes" }),
    ]);
  });
});
/* eslint-enable @typescript-eslint/no-explicit-any -- re-enable after test mocks */
/* eslint-enable @typescript-eslint/explicit-function-return-type -- re-enable after test helpers */
