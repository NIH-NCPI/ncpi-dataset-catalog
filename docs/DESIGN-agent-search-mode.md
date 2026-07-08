# Design Note: Agent Search Mode (`?agent=1`)

> Status: DRAFT — Jun 2026
> Refs: epic #365 · backend endpoint #379 · this PR #383 · follow-ups #381 (markdown), #382 (filter chips), #380 (history)

> **⚠️ SUPERSEDED (Jul 2026, #410/#412).** This note describes the original
> *opt-in* rollout — the `?agent=1` flag, the deterministic `/search` pipeline as
> the default, and the agent behind `/search/agent`. Agent search has since been
> promoted to the **default and only** search path: the deterministic pipeline,
> the `?agent=1` flag, and the `previousQuery` round-trip were removed, and the
> orchestrator now serves **`POST /search`** (+ **`POST /search/filter`** for chip
> removal). Endpoint/flow references below are historical.

---

## 1. Context

The catalog's conversational search runs the deterministic **`/search`** pipeline
(Extract → Resolve → Structure → Router), with multi-turn context carried by the
client via a `previousQuery` round-trip. Epic #365 productionizes an alternative:
a single Sonnet **orchestrator** with composable tools, exposed at
**`POST /search/agent`** (#379), which owns conversation state server-side keyed
by a `sessionId`.

This note documents how the frontend opts into that endpoint **without any new
UI**, so we can dogfood the agent against the real catalog before deciding
whether to promote it to the default.

## 2. Enabling agent mode

Append **`?agent=1`** to the research-view URL. The flag is read from the URL
(`next/router` `router.query.agent`) in `MultiTurnQueryProvider`
(`app/views/ResearchView/artifact/form.tsx`).

- **No toggle UI.** The flag is the entire opt-in — the prompt window, results
  table, and filter chips are unchanged.
- **Honored in all environments.** The agent endpoint is rate-limited
  server-side; there is no environment gate on the flag. (It calls Sonnet per
  request, so it does cost real money — see §6.)

## 3. Request / response mapping

Both modes call the same `postSearch()` helper and parse the same
`SearchResponse` shape, so results, filters, and the assistant message render
identically. The only differences are the URL and the request body:

|                  | Deterministic (`/search`)         | Agent (`/search/agent`)                                              |
| ---------------- | --------------------------------- | -------------------------------------------------------------------- |
| URL              | `getSearchApiUrl(config.ai?.url)` | `getSearchApiUrl(config.ai?.url, { agent: true })` → base + `/agent` |
| Body             | `{ query, previousQuery? }`       | `{ query, sessionId }`                                               |
| Multi-turn state | client-owned (`previousQuery`)    | server-owned (`SessionStore`, keyed by `sessionId`)                  |
| Response         | `SearchResponse`                  | `SearchResponse` (identical shape; `message` is the agent's prose)   |

The base URL (env `NEXT_PUBLIC_SEARCH_API_URL` or `config.ai?.url`) ends in
`/search`, so the agent URL is that with `/agent` appended.

## 4. Session model

`sessionId` is a `crypto.randomUUID()` generated **lazily on the first agent
submission** and held in a ref for the lifetime of the provider (one
research-view visit). The agent handles "reset"/new-topic turns server-side, so
a single id per visit is sufficient; we deliberately do not try to detect a
"fresh search" on the client.

> **Secure-context requirement.** `crypto.randomUUID()` is only available in a
> secure context (HTTPS, or `localhost`). All real deployments are HTTPS, but a
> non-secure origin such as a bare `http://<LAN-IP>` dev server will throw on
> submission. Use HTTPS or `localhost` when testing agent mode.

## 5. Behavioral notes & known limitations

> **Flag read timing.** The flag is read via `next/router` `router.query`, which
> is empty until the router hydrates. In the (sub-second) window before
> hydration, a submission would fall back to the deterministic `/search` path;
> it self-corrects on the next turn. Acceptable for an opt-in experiment.

Tracked separately:

- **Markdown not formatted (#381).** The agent replies in markdown, but the
  assistant message is rendered as plain `<Typography>` text, so formatting is
  not applied. Out of scope here.
- **Filter-chip removal (#382).** The chip × button uses the deterministic
  `previousQuery` lookup and is left **as-is** in agent mode (it does not update
  the agent's server-side state). Tracked for a proper fix.
- **Persisted-history truncation (#380).** The backend currently applies stopgap
  bounds on stored history; a coherent policy is tracked there.

## 6. Why this is safe to ship

Additive and opt-in: with no flag, behavior is exactly today's `/search`. The
agent path is reachable only by explicitly adding `?agent=1`, and is rate-limited
server-side. Nothing about the default experience changes.

## 7. Next steps (epic #365)

- Resolve #381 / #382 so agent mode reaches UX parity.
- Streaming for perceived latency; DynamoDB `SessionStore` for prod persistence.
- Frontend `session_id` plumbing to replace the `previousQuery` round-trip.
- Promote agent to default once parity + confidence are reached.
