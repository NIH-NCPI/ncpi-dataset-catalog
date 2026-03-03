import { useConfig } from "@databiosphere/findable-ui/lib/hooks/useConfig";
import { FONT } from "@databiosphere/findable-ui/lib/styles/common/constants/font";
import { PALETTE } from "@databiosphere/findable-ui/lib/styles/common/constants/palette";
import styled from "@emotion/styled";
import {
  Chip,
  CircularProgress,
  Link as MuiLink,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Typography,
} from "@mui/material";
import { JSX, useEffect, useState } from "react";

const GIT_HUB_COMMIT_URL =
  "https://github.com/NIH-NCPI/ncpi-dataset-catalog/commit";

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

const PageContainer = styled.div`
  margin: 0 auto;
  max-width: 720px;
  padding: 32px 16px;
  width: 100%;
`;

const Section = styled.div`
  margin-bottom: 24px;
`;

const SectionTitle = styled(Typography)`
  font: ${FONT.BODY_500};
  margin-bottom: 8px;
`;

const StyledTableContainer = styled(TableContainer)`
  .MuiTable-root {
    tr {
      td {
        border-bottom: 1px solid ${PALETTE.SMOKE_MAIN};
        font: ${FONT.BODY_SMALL_400};
        padding: 6px 8px;
      }

      td:first-of-type {
        font: ${FONT.BODY_SMALL_500};
        white-space: nowrap;
        width: 200px;
      }
    }
  }
`;

const CenterBox = styled.div`
  align-items: center;
  display: flex;
  justify-content: center;
  padding: 64px 0;
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
    <Section>
      <SectionTitle>{title}</SectionTitle>
      <StyledTableContainer>
        <Table size="small">
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
      </StyledTableContainer>
    </Section>
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
        }
      });
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
      <PageContainer>
        <Chip color="error" label={state.error} />
      </PageContainer>
    );
  }

  const { data } = state;

  return (
    <PageContainer>
      <Section>
        <SectionTitle>Service</SectionTitle>
        <StyledTableContainer>
          <Table size="small">
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
                    href={`${GIT_HUB_COMMIT_URL}/${data.gitSha}`}
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    {data.gitSha}
                  </MuiLink>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </StyledTableContainer>
      </Section>

      <Section>
        <SectionTitle>Index Stats</SectionTitle>
        <StyledTableContainer>
          <Table size="small">
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
        </StyledTableContainer>
      </Section>

      <CacheSection cache={data.pipelineCache} title="Pipeline Cache" />
      <CacheSection cache={data.resolveCache} title="Resolve Cache" />
    </PageContainer>
  );
};
