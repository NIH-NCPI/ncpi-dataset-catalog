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

type SearchMode = "agent" | "pipeline";

/**
 * Resolve the active search backend. A `?searchMode=` query param (runtime
 * override, set by the toggle) wins, then `NEXT_PUBLIC_SEARCH_MODE`, else the
 * default deterministic pipeline.
 * @returns The active search mode.
 */
function resolveSearchMode(): SearchMode {
  if (typeof window !== "undefined") {
    const param = new URLSearchParams(window.location.search).get("searchMode");
    if (param === "agent" || param === "pipeline") return param;
  }
  return process.env.NEXT_PUBLIC_SEARCH_MODE === "agent" ? "agent" : "pipeline";
}

/**
 * Derive the agentic endpoint URL from the configured `/search` URL.
 * @param url - The configured search URL (ending in `/search`).
 * @returns The corresponding `/search/agent` URL.
 */
function toAgentUrl(url: string): string {
  if (url.endsWith("/agent")) return url;
  return url.endsWith("/search")
    ? `${url}/agent`
    : url.replace(/\/?$/, "/search/agent");
}

/**
 * Generate a session id for an agentic conversation.
 * @returns A unique session id.
 */
function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Non-crypto fallback: a session id needs only to be unique, not secure.
  // eslint-disable-next-line sonarjs/pseudo-random -- not security-sensitive
  return `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
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
  const url = getSearchApiUrl(config.ai?.url);
  const dispatch = useChatDispatch();
  const lastQueryRef = useRef<MessageResponse["query"] | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  if (!sessionIdRef.current) sessionIdRef.current = newSessionId();

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
      if (!query || !url) return;

      const form = e.currentTarget;

      dispatch.onSetQuery(query);
      dispatch.onSetStatus(true);
      form.reset();
      options.onMutate?.(form, query);

      const mode = resolveSearchMode();
      const requestUrl = mode === "agent" ? toAgentUrl(url) : url;
      const body: Record<string, unknown> =
        mode === "agent"
          ? { query, sessionId: sessionIdRef.current }
          : { query };
      if (mode === "pipeline" && lastQueryRef.current) {
        body.previousQuery = lastQueryRef.current;
      }

      const data = await postSearch(requestUrl, body, abortRef, dispatch);
      if (data) {
        lastQueryRef.current = data.query;
        options.onSuccess?.(data);
      } else {
        options.onError?.(new Error("Search request failed"));
      }
      options.onSettled?.(form);
    },
    [dispatch, url]
  );

  const queryContextValue = useMemo(() => ({ onSubmit }), [onSubmit]);

  const removeFilter = useCallback(
    (facet: string, value: string): void => {
      if (!url) return;

      // Agent mode: ask the assistant to drop the filter conversationally.
      if (resolveSearchMode() === "agent") {
        dispatch.onSetStatus(true);
        postSearch(
          toAgentUrl(url),
          {
            query: `Remove ${value} from the ${facet} filter`,
            sessionId: sessionIdRef.current,
          },
          abortRef,
          dispatch
        ).then((data) => {
          if (data) lastQueryRef.current = data.query;
        });
        return;
      }

      if (!lastQueryRef.current) return;
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
