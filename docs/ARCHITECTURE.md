# Architecture

```
Browser (React, SSE) -> FastAPI (apps/api) -> LangGraph graphs (agent/graphs) -> MCP client (agent/mcp_client.py)
        ^                     |  Arq worker (worker/)                     |-> Portfolio MCP  (RAG over the portfolio)
        |  approvals          |  Postgres: app DB + checkpoints + store   |-> Marketplace MCP -> GigSim | Upwork official MCP
        +---------------------+  Phoenix traces (one trace id per run)    |-> Workspace MCP (calendar holds, email drafts)
```

## Graphs (rendered from code: `docs/images/bid_graph.mmd`, `docs/images/conversation_graph.mmd`)
* **Bid graph** (one thread per job): `scout` -> (`Send`) `job_analyst` || `risk_assessor` || `fit_matcher` ->
  `decision` -> `pricing` -> `writer` -> `verifier` -> `critic` (back to writer at most twice) -> `compliance` ->
  `preview` (dry run) -> `human_approval` (`interrupt()`) -> `executor`. An edit loops back to compliance.
* **Conversation graph** (one thread per client thread): `fetch_thread` -> `intent` -> `slots` -> `client_liaison` ->
  `compliance` -> `preview` -> `human_approval` -> `executor`.

## Why each agent exists
| Agent | Why it is separate | Model tier |
|---|---|---|
| Scout | polite scheduled search + dedup (fingerprints survive reposts) | none |
| Job Analyst | structured JobSpec that later steps decide on | small |
| Risk Assessor | rules + client history + LLM; skips the LLM on obvious scams (cost) | small |
| Fit Matcher | requirement-to-evidence matrix via Portfolio MCP; calibrated relevance thresholds | none (LLM grader optional) |
| Pricing Strategist | market percentiles (real Kaggle + history), floor, Connects economics, live policy surcharges | none |
| Proposal Writer | cited claims only `[E:item_id]`; style memory applied deterministically | large |
| Claim verifier | splits claims, checks each against the cited evidence text; removes/rewrites unsupported ones | medium |
| Critic | grounding, personalisation, length, generic opening, screening answers; max 2 revisions | large |
| Compliance Guard | `rules.yaml` + live policy: redact contacts/guarantees, block off-platform pay/free work; re-checks edits | small |
| Client Liaison | intent, interview slots, negotiation within the floor, scam replies | large |

## State, trace and memory are kept apart
* **State** (`agent/state.py`): what one job/conversation needs now; reducers for parallel writes (evidence union,
  usage merge, status severity).
* **Execution trace**: `state.trace` (node latency, tokens, USD, every MCP call with masked args), the MCP audit log,
  and OpenTelemetry spans in Phoenix. One id (the run id) is the trace id everywhere.
* **Long-term memory** (`agent/memory`): LangGraph store with `("style", user)` and `("outcome", user)` namespaces,
  written only by `promotion_rules.py` (edit pattern in >= 3 jobs; >= 5 outcomes with a >= 10-point reply-rate gap).
  Raw edits and outcomes live in DB tables and are never memory by themselves.

## Safety: nothing leaves without a human
1. The graph pauses at `human_approval` (an interrupt). 2. The API mints an HMAC approval token bound to (user,
operation, exact payload) only when the human clicks Approve. 3. The marketplace MCP server refuses any write
without a valid token, or if the payload changed after approval. Untrusted text (job posts, client messages) is
stripped of injected instructions, delimited in prompts, and never followed.
