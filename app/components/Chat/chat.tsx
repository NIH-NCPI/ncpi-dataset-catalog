import { useLayoutDimensions } from "@databiosphere/findable-ui/lib/providers/layoutDimensions/hook";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";
import {
  JSX,
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AssistantBubble,
  ChatContainer,
  ClarificationBanner,
  InputArea,
  LoadingDots,
  MessageList,
  ResultCount,
  SectionLabel,
  SectionRow,
  SendButton,
  StyledInput,
  StudyTable,
  UserBubble,
} from "./chat.styles";
import { SEARCH_API_URL } from "./constants";

interface Mention {
  exclude: boolean;
  facet: string;
  originalText: string;
  values: string[];
}

interface Study {
  consentCodes: string[];
  dataTypes: string[];
  dbGapId: string;
  focus: string;
  participantCount: number | null;
  platforms: string[];
  studyDesigns: string[];
  title: string;
}

interface SearchResponse {
  message: string | null;
  query: {
    mentions: Mention[];
    message: string | null;
  };
  studies: Study[];
  timing: {
    lookupMs: number;
    pipelineMs: number;
    totalMs: number;
  };
  totalStudies: number;
}

interface UserMessage {
  text: string;
  type: "user";
}

interface AssistantMessage {
  response: SearchResponse;
  type: "assistant";
}

interface ErrorMessage {
  error: string;
  type: "error";
}

type Message = AssistantMessage | ErrorMessage | UserMessage;

/**
 * Chat component for natural-language dataset search.
 * @returns Chat UI element.
 */
export const Chat = (): JSX.Element => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const historyIndexRef = useRef(-1);
  const draftRef = useRef("");
  const { dimensions } = useLayoutDimensions();
  const headerHeight = dimensions.header.height;

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Re-focus input when loading finishes (and on mount).
  useEffect(() => {
    if (!loading) {
      inputRef.current?.focus();
    }
  }, [loading]);

  const handleSend = useCallback(async () => {
    const query = input.trim();
    if (!query || loading) return;

    setInput("");
    setQueryHistory((prev) => [...prev, query]);
    historyIndexRef.current = -1;
    draftRef.current = "";
    setMessages((prev) => [...prev, { text: query, type: "user" }]);
    setLoading(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 90_000);

    try {
      if (!SEARCH_API_URL) {
        throw new Error("Search API URL is not configured.");
      }
      const res = await fetch(SEARCH_API_URL, {
        body: JSON.stringify({ query }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
        signal: controller.signal,
      });
      if (res.status === 429) {
        setMessages((prev) => [
          ...prev,
          {
            error: "You're sending too many requests. Please wait a moment.",
            type: "error",
          },
        ]);
        return;
      }
      if (!res.ok) {
        throw new Error(`Search failed (${res.status})`);
      }
      const data: SearchResponse = await res.json();
      setMessages((prev) => [...prev, { response: data, type: "assistant" }]);
    } catch (err) {
      if (!controller.signal.aborted) {
        const errorMessage =
          err instanceof Error ? err.message : "An unknown error occurred.";
        setMessages((prev) => [
          ...prev,
          { error: errorMessage, type: "error" },
        ]);
      }
    } finally {
      clearTimeout(timeout);
      setLoading(false);
    }
  }, [input, loading]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
        return;
      }

      // Up/Down arrow: navigate query history when input is empty or
      // cursor is at the very start (avoids interfering with multiline editing).
      const el = e.currentTarget;
      const cursorAtStart = el.selectionStart === 0 && el.selectionEnd === 0;

      if (e.key === "ArrowUp" && (input === "" || cursorAtStart)) {
        if (queryHistory.length === 0) return;
        e.preventDefault();
        if (historyIndexRef.current === -1) {
          draftRef.current = input;
          historyIndexRef.current = queryHistory.length - 1;
        } else if (historyIndexRef.current > 0) {
          historyIndexRef.current -= 1;
        }
        setInput(queryHistory[historyIndexRef.current]);
      } else if (e.key === "ArrowDown" && historyIndexRef.current >= 0) {
        e.preventDefault();
        if (historyIndexRef.current < queryHistory.length - 1) {
          historyIndexRef.current += 1;
          setInput(queryHistory[historyIndexRef.current]);
        } else {
          historyIndexRef.current = -1;
          setInput(draftRef.current);
        }
      }
    },
    [handleSend, input, queryHistory]
  );

  return (
    <ChatContainer style={{ paddingTop: headerHeight }}>
      <MessageList ref={listRef}>
        {messages.map((msg, i) => {
          if (msg.type === "user") {
            return <UserBubble key={i}>{msg.text}</UserBubble>;
          }
          if (msg.type === "error") {
            return (
              <AssistantBubble key={i} style={{ color: "#d32f2f" }}>
                {msg.error}
              </AssistantBubble>
            );
          }
          return <AssistantResponse key={i} response={msg.response} />;
        })}
        {loading && (
          <AssistantBubble>
            <LoadingDots>
              <span />
              <span />
              <span />
            </LoadingDots>
          </AssistantBubble>
        )}
      </MessageList>
      <InputArea>
        <StyledInput
          disabled={loading}
          inputRef={inputRef}
          multiline
          maxRows={4}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about datasets..."
          value={input}
        />
        <SendButton disabled={loading || !input.trim()} onClick={handleSend}>
          <SendRoundedIcon />
        </SendButton>
      </InputArea>
    </ChatContainer>
  );
};

/**
 * Renders a structured assistant response.
 * @param props - Component props.
 * @param props.response - The search API response.
 * @returns Rendered assistant response.
 */
function AssistantResponse({
  response,
}: {
  response: SearchResponse;
}): JSX.Element {
  const { mentions } = response.query;

  // Group mentions by facet for resolved mappings display.
  const mappings = mentions.reduce<Record<string, string[]>>((acc, m) => {
    const key = m.exclude ? `${m.facet} (exclude)` : m.facet;
    acc[key] = [...(acc[key] || []), ...m.values];
    return acc;
  }, {});

  const totalSeconds = (response.timing.totalMs / 1000).toFixed(1);

  return (
    <AssistantBubble>
      {response.message && (
        <ClarificationBanner>{response.message}</ClarificationBanner>
      )}

      {mentions.length > 0 && (
        <SectionRow>
          <SectionLabel>Extracted mentions:</SectionLabel>
          {mentions.map((m) => m.originalText).join(", ")}
        </SectionRow>
      )}

      {Object.keys(mappings).length > 0 && (
        <SectionRow>
          <SectionLabel>Resolved mappings:</SectionLabel>
          {Object.entries(mappings)
            .map(([facet, values]) => `${facet}: ${values.join(", ")}`)
            .join(" / ")}
        </SectionRow>
      )}

      <ResultCount>
        Found {response.totalStudies}{" "}
        {response.totalStudies === 1 ? "study" : "studies"} in {totalSeconds}s
      </ResultCount>

      {response.studies.length > 0 && (
        <StudyTable>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Title</TableCell>
                <TableCell>dbGaP Id</TableCell>
                <TableCell>Platform</TableCell>
                <TableCell>Focus / Disease</TableCell>
                <TableCell>Data Type</TableCell>
                <TableCell>Participants</TableCell>
                <TableCell>Study Design</TableCell>
                <TableCell>Consent Code</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {response.studies.map((study, i) => (
                <TableRow key={i}>
                  <TableCell>{study.title}</TableCell>
                  <TableCell>{study.dbGapId}</TableCell>
                  <TableCell>{study.platforms.join(", ")}</TableCell>
                  <TableCell>{study.focus}</TableCell>
                  <TableCell>{study.dataTypes.join(", ")}</TableCell>
                  <TableCell>
                    {study.participantCount != null
                      ? study.participantCount.toLocaleString()
                      : "—"}
                  </TableCell>
                  <TableCell>{study.studyDesigns.join(", ")}</TableCell>
                  <TableCell>{study.consentCodes.join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </StudyTable>
      )}
    </AssistantBubble>
  );
}
