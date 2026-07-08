/* eslint-disable @typescript-eslint/explicit-function-return-type -- test helpers */
import { QueryContext } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/context";
import { act, renderHook } from "@testing-library/react";
import { FormEvent, ReactNode, useContext } from "react";
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
  getSearchApiUrl: (url: string): string => url || "",
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

const okResponse = () => ({
  json: () =>
    Promise.resolve({
      intent: "study",
      message: "Here are diabetes studies.",
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

// jsdom does not implement crypto.randomUUID; stub it with incrementing ids so
// tests can prove the session id is generated once and reused across turns.
let uuidCounter = 0;
const originalRandomUUID = Object.getOwnPropertyDescriptor(
  crypto,
  "randomUUID"
);

const stubRandomUUID = (): void => {
  Object.defineProperty(crypto, "randomUUID", {
    configurable: true,
    value: () => `uuid-${++uuidCounter}`,
  });
};

const restoreRandomUUID = (): void => {
  if (originalRandomUUID) {
    Object.defineProperty(crypto, "randomUUID", originalRandomUUID);
  } else {
    delete (crypto as { randomUUID?: unknown }).randomUUID;
  }
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

/**
 * Renders both the query and multi-turn contexts from one provider instance.
 * @returns Hook result with onSubmit and removeFilter.
 */
function renderBoth() {
  return renderHook(
    () => ({
      multiTurn: useContext(MultiTurnContext),
      query: useContext(QueryContext),
    }),
    {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MultiTurnQueryProvider>{children}</MultiTurnQueryProvider>
      ),
    }
  );
}

// --- Tests ---

describe("MultiTurnQueryProvider onSubmit", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockChatState.state.messages = [];
    uuidCounter = 0;
    stubRandomUUID();
    global.fetch = jest.fn().mockResolvedValue(okResponse());
  });

  afterEach(restoreRandomUUID);

  it("posts to the agent endpoint with sessionId and no previousQuery", async () => {
    const { result } = renderOnSubmit();

    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        defaultOptions
      );
    });

    const [calledUrl, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(calledUrl).toBe("https://test-api/search/agent");
    const body = JSON.parse(init.body);
    expect(body.query).toBe("diabetes studies");
    expect(body.sessionId).toBe("uuid-1");
    expect(body).not.toHaveProperty("previousQuery");
  });

  it("reuses the same sessionId across turns", async () => {
    const { result } = renderOnSubmit();

    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        defaultOptions
      );
    });
    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "only on BDC" },
        defaultOptions
      );
    });

    const calls = (global.fetch as jest.Mock).mock.calls;
    const firstBody = JSON.parse(calls[0][1].body);
    const secondBody = JSON.parse(calls[1][1].body);
    expect(secondBody.sessionId).toBe(firstBody.sessionId);
    expect(secondBody).not.toHaveProperty("previousQuery");
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

  it("surfaces an error and does not get stuck when session id generation fails", async () => {
    Object.defineProperty(crypto, "randomUUID", {
      configurable: true,
      value: () => {
        throw new Error("insecure context");
      },
    });
    const onError = jest.fn();
    const { result } = renderOnSubmit();

    await act(async () => {
      await result.current.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        { ...defaultOptions, onError }
      );
    });

    expect(global.fetch).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalled();
    expect(mockDispatch.onSetError).toHaveBeenCalled();
    // Loading was never entered, so the UI cannot be stuck.
    expect(mockDispatch.onSetStatus).not.toHaveBeenCalledWith(true);
  });
});

describe("MultiTurnQueryProvider removeFilter", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockChatState.state.messages = [];
    uuidCounter = 0;
    stubRandomUUID();
    global.fetch = jest.fn().mockResolvedValue(okResponse());
  });

  afterEach(restoreRandomUUID);

  it("posts to the agent filter endpoint with sessionId and no previousQuery", async () => {
    const { result } = renderBoth();

    // Establish the session with a first submission.
    await act(async () => {
      await result.current.query.onSubmit(
        mockFormEvent(),
        { query: "diabetes studies" },
        defaultOptions
      );
    });

    await act(async () => {
      result.current.multiTurn.removeFilter("focus", "DM");
      await new Promise((r) => setTimeout(r, 0));
    });

    const calls = (global.fetch as jest.Mock).mock.calls;
    expect(calls).toHaveLength(2);
    const [calledUrl, init] = calls[1];
    expect(calledUrl).toBe("https://test-api/search/agent/filter");
    const body = JSON.parse(init.body);
    expect(body).toEqual({ facet: "focus", sessionId: "uuid-1", value: "DM" });
  });

  it("is a no-op before a session exists", async () => {
    const { result } = renderBoth();

    await act(async () => {
      result.current.multiTurn.removeFilter("focus", "DM");
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(global.fetch).not.toHaveBeenCalled();
  });
});

/* eslint-enable @typescript-eslint/explicit-function-return-type -- re-enable after test helpers */
