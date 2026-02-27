import { useCallback, useRef } from "react";

interface AbortableFetchResult<T> {
  aborted: boolean;
  data: T | null;
  error: string | null;
}

interface UseAbortableFetchReturn {
  abort: () => void;
  execute: <T>(
    url: string,
    options?: RequestInit
  ) => Promise<AbortableFetchResult<T>>;
}

/**
 * Hook for making fetch requests with automatic abort handling.
 * Cancels any in-flight request when a new one is made.
 * @param timeoutMs - Request timeout in milliseconds (default: 90000).
 * @returns Object with execute function and abort function.
 */
export function useAbortableFetch(timeoutMs = 90_000): UseAbortableFetchReturn {
  const abortRef = useRef<AbortController | null>(null);

  const execute = useCallback(
    async <T>(
      url: string,
      options?: RequestInit
    ): Promise<AbortableFetchResult<T>> => {
      abortRef.current?.abort();

      const controller = new AbortController();
      abortRef.current = controller;
      const timeout = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const res = await fetch(url, {
          ...options,
          signal: controller.signal,
        });

        if (!res.ok) {
          return {
            aborted: false,
            data: null,
            error: `Request failed (${res.status})`,
          };
        }

        const data: T = await res.json();
        return { aborted: false, data, error: null };
      } catch (err) {
        if (controller.signal.aborted) {
          return { aborted: true, data: null, error: null };
        }
        const message =
          err instanceof Error ? err.message : "An unknown error occurred.";
        return { aborted: false, data: null, error: message };
      } finally {
        clearTimeout(timeout);
      }
    },
    [timeoutMs]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { abort, execute };
}
