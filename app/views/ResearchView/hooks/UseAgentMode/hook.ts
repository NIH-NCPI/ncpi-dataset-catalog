import { useRouter } from "next/router";

/** URL search param that opts a session into agentic search mode. */
export const AGENT_MODE_PARAM = "agent";

/** Value of {@link AGENT_MODE_PARAM} that enables agent mode. */
const AGENT_MODE_ENABLED = "1";

/**
 * Reads the `?agent=1` URL flag that routes search to the `/search/agent`
 * endpoint. Single source of truth for the flag so every agent-aware component
 * (submission, filter chips, history) stays in sync. Honored in all envs.
 * @returns True when agent mode is enabled via the URL.
 */
export function useAgentMode(): boolean {
  const { query } = useRouter();
  return query[AGENT_MODE_PARAM] === AGENT_MODE_ENABLED;
}
