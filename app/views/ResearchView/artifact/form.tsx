import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { isAssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards";
import { useChatDispatch } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatDispatch/hook";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { QueryContext } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/context";
import {
  Mention,
  MessageResponse,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import {
  createContext,
  FormEvent,
  JSX,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from "react";
import { getSearchApiUrl } from "../../../utils/searchApiUrl";
import { useAgentMode } from "../hooks/UseAgentMode/hook";

/**
 * Context for multi-turn filter removal.
 */
interface MultiTurnContextValue {
  removeFilter: (facet: string, value: string) => void;
}

export const MultiTurnContext = createContext<MultiTurnContextValue>({
  removeFilter: () => {},
});

/**
 * Hook to access multi-turn context.
 * @returns Multi-turn context value.
 */
export const useMultiTurn = (): MultiTurnContextValue =>
  useContext(MultiTurnContext);

interface MultiTurnQueryProviderProps {
  children: ReactNode;
}

/**
 * Dispatch actions used by the search helpers.
 */
interface SearchDispatch {
  onSetError: (message: string) => void;
  onSetMessage: (data: MessageResponse) => void;
  onSetStatus: (loading: boolean) => void;
}

/**
 * Posts a search request, handling abort, timeout, rate-limit, and errors.
 * @param url - Search API URL.
 * @param body - Request body to send as JSON.
 * @param abortRef - Shared abort controller ref (previous request is aborted).
 * @param dispatch - Chat dispatch actions.
 * @returns The parsed response, or undefined on error/abort.
 */
async function postSearch(
  url: string,
  body: Record<string, unknown>,
  abortRef: React.RefObject<AbortController | null>,
  dispatch: SearchDispatch
): Promise<MessageResponse | undefined> {
  abortRef.current?.abort();
  const controller = new AbortController();
  abortRef.current = controller;
  const timeout = setTimeout(() => controller.abort(), 90_000);

  try {
    const res = await fetch(url, {
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
      method: "POST",
      signal: controller.signal,
    });

    if (res.status === 429) {
      dispatch.onSetError(
        "You're sending too many requests. Please wait a moment."
      );
      return undefined;
    }
    if (!res.ok) throw new Error(`Search failed (${res.status})`);

    const data: MessageResponse = await res.json();
    dispatch.onSetMessage(data);
    return data;
  } catch (error) {
    if (controller.signal.aborted) return undefined;
    const message =
      error instanceof Error ? error.message : "An unknown error occurred.";
    dispatch.onSetError(message);
    return undefined;
  } finally {
    clearTimeout(timeout);
    if (abortRef.current === controller) {
      dispatch.onSetStatus(false);
    }
  }
}

/**
 * Provider that tracks query state for multi-turn support.
 * Observes assistant messages from the chat state to capture the latest
 * QueryModel, enabling filter removal via requery.
 * @param props - Component props.
 * @param props.children - Children to render.
 * @returns Provider wrapping children with multi-turn context.
 */
export function MultiTurnQueryProvider({
  children,
}: MultiTurnQueryProviderProps): JSX.Element {
  const { config } = useConfig();
  // Opt-in agentic search via the `?agent=1` URL flag. When on, submissions go
  // to the `/search/agent` endpoint with a server-owned session instead of the
  // deterministic `/search` previousQuery round-trip.
  const agentMode = useAgentMode();
  const url = getSearchApiUrl(config.ai?.url);
  const submitUrl = getSearchApiUrl(config.ai?.url, { agent: agentMode });
  const dispatch = useChatDispatch();
  const lastQueryRef = useRef<MessageResponse["query"] | null>(null);
  // Conversation id for agent mode; created lazily on first agent submission so
  // the backend can key multi-turn state. The agent handles resets server-side,
  // so one id per provider lifetime (one research-view visit) is sufficient.
  const sessionIdRef = useRef<string>("");
  const abortRef = useRef<AbortController | null>(null);

  // Sync lastQueryRef from chat state whenever a new assistant message arrives.
  const { state } = useChatState();
  const messages = state.messages;
  const lastMessage = messages[messages.length - 1];
  useEffect(() => {
    if (lastMessage && isAssistantMessage(lastMessage)) {
      const response = (lastMessage as { response: MessageResponse }).response;
      if (response?.query) {
        lastQueryRef.current = response.query;
      }
    }
  }, [lastMessage]);

  // Update the input placeholder to indicate refine mode after first results.
  useEffect(() => {
    if (!lastQueryRef.current) return;
    const input = document.querySelector<HTMLTextAreaElement>(
      'textarea[name="ai-prompt"]'
    );
    if (input) {
      input.placeholder =
        "Refine, e.g. \u201Calso where BMI was measured\u201D";
    }
  }, [lastMessage]);

  /**
   * Submits a query to the search API, injecting previousQuery when available.
   * @param e - Form event used to prevent default submission and access the form element.
   * @param payload - Payload containing the query string.
   * @param options - Callbacks for the submit lifecycle.
   */
  const onSubmit = useCallback(
    async (
      e: FormEvent<HTMLFormElement>,
      payload: { query: string },
      options: {
        onError?: (error: Error) => void;
        onMutate?: (form: HTMLFormElement, query: string) => void;
        onSettled?: (form: HTMLFormElement) => void;
        onSuccess?: (data: unknown) => void;
        status: { loading: boolean };
      }
    ): Promise<void> => {
      e.preventDefault();

      if (options.status.loading) return;

      const query = payload.query.trim();
      if (!query || !submitUrl) return;

      const form = e.currentTarget;

      // Build the request body before mutating UI state. crypto.randomUUID()
      // throws on a non-secure origin (HTTP outside localhost); doing it here
      // surfaces a visible error instead of leaving the form stuck loading.
      const body: Record<string, unknown> = { query };
      if (agentMode) {
        // Backend owns conversation state keyed by sessionId — no previousQuery.
        try {
          if (!sessionIdRef.current) sessionIdRef.current = crypto.randomUUID();
        } catch {
          dispatch.onSetError(
            "Agent search needs a secure (HTTPS) connection."
          );
          options.onError?.(new Error("Failed to start an agent session."));
          return;
        }
        body.sessionId = sessionIdRef.current;
      } else if (lastQueryRef.current) {
        body.previousQuery = lastQueryRef.current;
      }

      dispatch.onSetQuery(query);
      dispatch.onSetStatus(true);
      form.reset();
      options.onMutate?.(form, query);

      const data = await postSearch(submitUrl, body, abortRef, dispatch);
      if (data) {
        lastQueryRef.current = data.query;
        options.onSuccess?.(data);
      } else {
        options.onError?.(new Error("Search request failed"));
      }
      options.onSettled?.(form);
    },
    [agentMode, dispatch, submitUrl]
  );

  const queryContextValue = useMemo(() => ({ onSubmit }), [onSubmit]);

  const removeFilter = useCallback(
    (facet: string, value: string): void => {
      if (!lastQueryRef.current || !url) return;
      const filtered = lastQueryRef.current.mentions
        .map((m: Mention) => {
          if (m.facet !== facet) return m;
          const values = m.values.filter((v) => v !== value);
          if (values.length === 0) return null;
          return { ...m, values };
        })
        .filter((m): m is Mention => m !== null);
      const updatedQuery = { ...lastQueryRef.current, mentions: filtered };
      lastQueryRef.current = updatedQuery;
      dispatch.onSetStatus(true);

      postSearch(
        url,
        { previousQuery: updatedQuery, query: "" },
        abortRef,
        dispatch
      ).then((data) => {
        if (data) {
          lastQueryRef.current = data.query;
        }
      });
    },
    [dispatch, url]
  );

  return (
    <QueryContext.Provider value={queryContextValue}>
      <MultiTurnContext.Provider value={{ removeFilter }}>
        {children}
      </MultiTurnContext.Provider>
    </QueryContext.Provider>
  );
}
