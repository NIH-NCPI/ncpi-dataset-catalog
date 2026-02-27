import { useCallback, useRef } from "react";

interface UseQueryHistoryReturn {
  add: (query: string) => void;
  navigate: (direction: "down" | "up", currentInput: string) => string | null;
  reset: () => void;
}

/**
 * Hook for managing query history with arrow key navigation.
 * Provides shell-like recall of previous queries.
 * @param maxLength - Maximum number of queries to store (default: 50).
 * @returns Object with add, navigate, and reset functions.
 */
export function useQueryHistory(maxLength = 50): UseQueryHistoryReturn {
  const historyRef = useRef<string[]>([]);
  const indexRef = useRef(-1);
  const draftRef = useRef("");

  const add = useCallback(
    (query: string) => {
      historyRef.current = [...historyRef.current, query].slice(-maxLength);
      indexRef.current = -1;
      draftRef.current = "";
    },
    [maxLength]
  );

  const navigate = useCallback(
    (direction: "down" | "up", currentInput: string): string | null => {
      const history = historyRef.current;
      if (history.length === 0) return null;

      if (direction === "up") {
        if (indexRef.current === -1) {
          draftRef.current = currentInput;
          indexRef.current = history.length - 1;
        } else if (indexRef.current > 0) {
          indexRef.current -= 1;
        }
        return history[indexRef.current];
      } else {
        if (indexRef.current === -1) return null;
        if (indexRef.current < history.length - 1) {
          indexRef.current += 1;
          return history[indexRef.current];
        } else {
          indexRef.current = -1;
          return draftRef.current;
        }
      }
    },
    []
  );

  const reset = useCallback(() => {
    indexRef.current = -1;
    draftRef.current = "";
  }, []);

  return { add, navigate, reset };
}
