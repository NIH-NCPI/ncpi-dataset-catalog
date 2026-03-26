import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { useChatDispatch } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatDispatch/hook";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { isAssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards";
import { QueryContext } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/context";
import {
  MessageResponse,
  Mention,
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
   * @param _e - Form event (unused; dispatch handles state).
   * @param payload - Payload containing the query string.
   * @param options - Callbacks for the submit lifecycle.
   */
  const onSubmit = useCallback(
    async (
      _e: FormEvent<HTMLFormElement>,
      payload: { query: string },
      options: {
        onError?: (error: Error) => void;
        onMutate?: (form: HTMLFormElement, query: string) => void;
        onSettled?: (form: HTMLFormElement) => void;
        onSuccess?: (data: unknown) => void;
        status: { loading: boolean };
      }
    ): Promise<void> => {
      _e.preventDefault();

      if (options.status.loading) return;

      const { query } = payload;
      if (!query || !url) return;

      const form = (_e.target ?? _e.currentTarget) as HTMLFormElement;

      dispatch.onSetQuery(query);
      dispatch.onSetStatus(true);
      form.reset();
      options.onMutate?.(form, query);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const timeout = setTimeout(() => controller.abort(), 90_000);

      const body: Record<string, unknown> = { query };
      if (lastQueryRef.current) {
        body.previousQuery = lastQueryRef.current;
      }

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
          return;
        }
        if (!res.ok) throw new Error(`Search failed (${res.status})`);

        const data: MessageResponse = await res.json();
        lastQueryRef.current = data.query;
        dispatch.onSetMessage(data);
        options.onSuccess?.(data);
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error ? error.message : "An unknown error occurred.";
        dispatch.onSetError(message);
        options.onError?.(error instanceof Error ? error : new Error(message));
      } finally {
        clearTimeout(timeout);
        dispatch.onSetStatus(false);
        options.onSettled?.(form);
      }
    },
    [dispatch, url]
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
      // Abort any in-flight request.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const timeout = setTimeout(() => controller.abort(), 90_000);
      fetch(url, {
        body: JSON.stringify({ previousQuery: updatedQuery, query: "" }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
        signal: controller.signal,
      })
        .then(async (res) => {
          if (res.status === 429) {
            dispatch.onSetError(
              "You're sending too many requests. Please wait a moment."
            );
            return;
          }
          if (!res.ok) throw new Error(`Search failed (${res.status})`);
          const data: MessageResponse = await res.json();
          lastQueryRef.current = data.query;
          dispatch.onSetMessage(data);
        })
        .catch((error) => {
          if (controller.signal.aborted) return;
          const message =
            error instanceof Error
              ? error.message
              : "An unknown error occurred.";
          dispatch.onSetError(message);
        })
        .finally(() => {
          clearTimeout(timeout);
          dispatch.onSetStatus(false);
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
