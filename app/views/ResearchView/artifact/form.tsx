import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { isAssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards";
import { useChatDispatch } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatDispatch/hook";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { QueryContext } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/context";
import { MessageResponse } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
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
 * Provider that drives the conversational agent search. Every submission goes to
 * the `/search/agent` endpoint with a server-owned `sessionId`; the backend owns
 * multi-turn conversation state, so the client sends no prior query.
 * @param props - Component props.
 * @param props.children - Children to render.
 * @returns Provider wrapping children with multi-turn context.
 */
export function MultiTurnQueryProvider({
  children,
}: MultiTurnQueryProviderProps): JSX.Element {
  const { config } = useConfig();
  const baseUrl = getSearchApiUrl(config.ai?.url);
  const submitUrl = baseUrl ? `${baseUrl}/agent` : "";
  const dispatch = useChatDispatch();
  // Conversation id created lazily on first submission so the backend can key
  // multi-turn state. The agent handles resets server-side, so one id per
  // provider lifetime (one research-view visit) is sufficient.
  const sessionIdRef = useRef<string>("");
  const abortRef = useRef<AbortController | null>(null);

  // Once results have come back, switch the input placeholder to refine mode.
  const { state } = useChatState();
  const messages = state.messages;
  const lastMessage = messages[messages.length - 1];
  useEffect(() => {
    if (!lastMessage || !isAssistantMessage(lastMessage)) return;
    const input = document.querySelector<HTMLTextAreaElement>(
      'textarea[name="ai-prompt"]'
    );
    if (input) {
      input.placeholder = "Refine, e.g. “also where BMI was measured”";
    }
  }, [lastMessage]);

  /**
   * Submits a query to the agent search API under the current session.
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
      try {
        if (!sessionIdRef.current) sessionIdRef.current = crypto.randomUUID();
      } catch {
        dispatch.onSetError("Search needs a secure (HTTPS) connection.");
        options.onError?.(new Error("Failed to start a search session."));
        return;
      }
      body.sessionId = sessionIdRef.current;

      dispatch.onSetQuery(query);
      dispatch.onSetStatus(true);
      form.reset();
      options.onMutate?.(form, query);

      const data = await postSearch(submitUrl, body, abortRef, dispatch);
      if (data) {
        options.onSuccess?.(data);
      } else {
        options.onError?.(new Error("Search request failed"));
      }
      options.onSettled?.(form);
    },
    [dispatch, submitUrl]
  );

  const queryContextValue = useMemo(() => ({ onSubmit }), [onSubmit]);

  const removeFilter = useCallback(
    (facet: string, value: string): void => {
      // Conversation state lives server-side, keyed by sessionId; ask the backend
      // to drop the value from the session's query (#382).
      if (!sessionIdRef.current || !submitUrl) return;
      dispatch.onSetStatus(true);
      postSearch(
        `${submitUrl}/filter`,
        { facet, sessionId: sessionIdRef.current, value },
        abortRef,
        dispatch
      );
    },
    [dispatch, submitUrl]
  );

  return (
    <QueryContext.Provider value={queryContextValue}>
      <MultiTurnContext.Provider value={{ removeFilter }}>
        {children}
      </MultiTurnContext.Provider>
    </QueryContext.Provider>
  );
}
