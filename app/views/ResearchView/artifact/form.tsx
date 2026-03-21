import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { useChatDispatch } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatDispatch/hook";
import { useChatState } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatState/hook";
import { isAssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/guards/guards";
import {
  MessageResponse,
  Mention,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import {
  createContext,
  JSX,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
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
    <MultiTurnContext.Provider value={{ removeFilter }}>
      {children}
    </MultiTurnContext.Provider>
  );
}
