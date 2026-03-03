import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { ContentView } from "@databiosphere/findable-ui/lib/views/ContentView/contentView";
import styled from "@emotion/styled";
import {
  Chip,
  CircularProgress,
  Link as MuiLink,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import { JSX, useEffect, useState } from "react";
import { GIT_HUB_REPO_URL } from "../../../site-config/common/constants";
import { Content } from "../Layout/components/Content/content";

const FETCH_TIMEOUT_MS = 15_000;

interface CacheStats {
  hit_rate: number;
  hits: number;
  misses: number;
  size: number;
}

interface HealthResponse {
  gitSha: string;
  indexStats: Record<string, number>;
  pipelineCache: CacheStats;
  resolveCache: CacheStats;
  status: string;
}

type FetchState =
  | { data: HealthResponse; status: "success" }
  | { error: string; status: "error" }
  | { status: "loading" };

const CenterBox = styled.div`
  align-items: center;
  display: flex;
  justify-content: center;
  padding: 64px 0;
`;

const StatusContent = styled.div`
  .MuiTableCell-root:first-of-type {
    width: 200px;
  }
`;

/**
 * Derives the health endpoint URL from the configured AI search URL.
 * @param aiUrl - The AI search URL from site config.
 * @returns The health endpoint URL.
 */
function getHealthUrl(aiUrl: string): string {
  return aiUrl.replace(/\/search$/, "/health");
}

/**
 * Formats a hit-rate number as a percentage string.
 * @param rate - The hit rate (0-1).
 * @returns Formatted percentage string.
 */
function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

/**
 * Renders a key-value table for cache statistics.
 * @param props - Component props.
 * @param props.cache - Cache statistics object.
 * @param props.title - Section title.
 * @returns Rendered cache stats section.
 */
function CacheSection({
  cache,
  title,
}: {
  cache: CacheStats;
  title: string;
}): JSX.Element {
  return (
    <>
      <h2>{title}</h2>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Metric</TableCell>
              <TableCell>Value</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableRow>
              <TableCell>Hit Rate</TableCell>
              <TableCell>{formatRate(cache.hit_rate)}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Hits</TableCell>
              <TableCell>{cache.hits}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Misses</TableCell>
              <TableCell>{cache.misses}</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Size</TableCell>
              <TableCell>{cache.size}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}

/**
 * Client-side health status page that fetches and displays backend health data.
 * @returns Status page element.
 */
export const Status = (): JSX.Element => {
  const { config } = useConfig();
  const [state, setState] = useState<FetchState>({ status: "loading" });

  useEffect(() => {
    const aiUrl = config.ai?.url;
    if (!aiUrl) {
      setState({ error: "AI service URL is not configured.", status: "error" });
      return;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    fetch(getHealthUrl(aiUrl), { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`Health check failed (${res.status})`);
        return res.json();
      })
      .then((data: HealthResponse) => setState({ data, status: "success" }))
      .catch((err) => {
        if (!controller.signal.aborted) {
          setState({
            error: err instanceof Error ? err.message : "Unknown error",
            status: "error",
          });
        } else {
          setState({
            error: "Health check timed out.",
            status: "error",
          });
        }
      })
      .finally(() => clearTimeout(timeout));
    return (): void => controller.abort();
  }, [config.ai?.url]);

  if (state.status === "loading") {
    return (
      <CenterBox>
        <CircularProgress size={32} />
      </CenterBox>
    );
  }

  if (state.status === "error") {
    return (
      <ContentView
        content={
          <Content>
            <StatusContent>
              <h1>Status</h1>
              <Chip color="error" label={state.error} />
            </StatusContent>
          </Content>
        }
      />
    );
  }

  const { data } = state;

  return (
    <ContentView
      content={
        <Content>
          <StatusContent>
            <h1>Status</h1>

            <h2>Service</h2>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Property</TableCell>
                    <TableCell>Value</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  <TableRow>
                    <TableCell>Status</TableCell>
                    <TableCell>
                      <Chip
                        color={data.status === "ok" ? "success" : "error"}
                        label={data.status}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Git SHA</TableCell>
                    <TableCell>
                      <MuiLink
                        href={`${GIT_HUB_REPO_URL}/commit/${data.gitSha}`}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        {data.gitSha}
                      </MuiLink>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>

            <h2>Index Stats</h2>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Facet</TableCell>
                    <TableCell>Count</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(data.indexStats)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([key, value]) => (
                      <TableRow key={key}>
                        <TableCell>{key}</TableCell>
                        <TableCell>{value.toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </TableContainer>

            <CacheSection cache={data.pipelineCache} title="Pipeline Cache" />
            <CacheSection cache={data.resolveCache} title="Resolve Cache" />
          </StatusContent>
        </Content>
      }
    />
  );
};
