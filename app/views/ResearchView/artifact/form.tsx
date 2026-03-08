import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { QueryContext } from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/context";
import { useChatDispatch } from "@databiosphere/findable-ui/lib/views/ResearchView/state/hooks/UseChatDispatch/hook";
import {
  MessageResponse,
  Mention,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import {
  OnSubmitOptions,
  OnSubmitPayload,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/query/types";
import {
  createContext,
  FormEvent,
  JSX,
  ReactNode,
  useCallback,
  useContext,
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
 * Provider that shadows the library's QueryContext with multi-turn support.
 * Tracks the last query response and includes previousQuery in submissions.
 * @param props - Component props.
 * @param props.children - Children to render.
 * @returns Provider wrapping children with multi-turn query context.
 */
export function MultiTurnQueryProvider({
  children,
}: MultiTurnQueryProviderProps): JSX.Element {
  const { config } = useConfig();
  const url = getSearchApiUrl(config.ai?.url);
  const dispatch = useChatDispatch();
  const lastQueryRef = useRef<MessageResponse["query"] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const doFetch = useCallback(
    async (
      query: string,
      previousQuery: MessageResponse["query"] | null,
      options: OnSubmitOptions
    ): Promise<void> => {
      // Abort any in-flight request.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const timeout = setTimeout(() => controller.abort(), 90_000);
      try {
        const body: Record<string, unknown> = { query };
        if (previousQuery) {
          body.previousQuery = previousQuery;
        }
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
        if (!res.ok) {
          throw new Error(`Search failed (${res.status})`);
        }
        const data: MessageResponse = await res.json();
        lastQueryRef.current = data.query;
        dispatch.onSetMessage(data);
        options.onSuccess?.(data);
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error ? error.message : "An unknown error occurred.";
        dispatch.onSetError(message);
        if (error instanceof Error) options.onError?.(error);
      } finally {
        clearTimeout(timeout);
        dispatch.onSetStatus(false);
        if (options.onSettled) {
          const form = document.querySelector("form");
          if (form) options.onSettled(form);
        }
      }
    },
    [dispatch, url]
  );

  const onSubmit = useCallback(
    async (
      e: FormEvent<HTMLFormElement>,
      payload: OnSubmitPayload,
      options: OnSubmitOptions
    ): Promise<void> => {
      e.preventDefault();
      if (options.status.loading) return;
      const { query } = payload;
      if (!query) return;
      dispatch.onSetQuery(query);
      dispatch.onSetStatus(true);
      e.currentTarget.reset();
      options.onMutate?.(e.currentTarget, query);
      await doFetch(query, lastQueryRef.current, options);
    },
    [dispatch, doFetch]
  );

  const removeFilter = useCallback(
    (facet: string, value: string): void => {
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
      doFetch("", updatedQuery, { status: { loading: false } });
    },
    [dispatch, doFetch]
  );

  return (
    <MultiTurnContext.Provider value={{ removeFilter }}>
      <QueryContext.Provider value={{ onSubmit }}>
        {children}
      </QueryContext.Provider>
    </MultiTurnContext.Provider>
  );
}
