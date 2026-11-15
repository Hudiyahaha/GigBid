# Runbook

## Local (no Docker)
```
.\.venv\Scripts\python.exe -m scripts.dev_stack        # GigSim :8081 + API/web :8000 (SQLite, in-process MCP)
.\.venv\Scripts\python.exe -m worker.main --local      # scheduled scouting / event sync without Redis
```
Set `GIGBID_FAKE_LLM=1` for offline deterministic runs. Set `GIGBID_LOCAL_SQLITE=1` while `.env` points at Postgres.

## Docker
`docker compose -f infra/docker-compose.yml --env-file .env up --build` starts web+API, worker, the 3 MCP servers,
GigSim, Postgres, Redis, Qdrant, Ollama and Phoenix. Reviewer login: set `REVIEWER_EMAIL`, `REVIEWER_PASSWORD`,
`REVIEWER_PERSONA` in the host's environment (never in the repo).

## Scheduling and politeness
* GigSim: saved searches every 5 min (`worker.scout_interval_minutes_gigsim`); the marketplace MCP server rate-limits
  each user to 40 req/min (GigSim allows 60).
* **Live Upwork: every 240 min**, 6 req/min. Jobs worth bidding on stay open for days and proposals are capped by
  Connects, so a 4-hour cadence loses almost nothing while keeping traffic far below anything that looks like
  scraping. Reads only use the official MCP server; there is no browser automation and no cookies.

## Degraded mode (marketplace down)
`agent/mcp_client.py` retries with backoff and raises `MarketplaceDown`. `agent/nodes/base.py` turns that into
status `queued_retry`. `/api/status` reports `unavailable`, and the UI shows a banner (`DegradedBanner.tsx`).
`worker.retry_queued` replays the thread from its last good checkpoint once the marketplace answers again.
Demo: `POST /api/dev/marketplace/down` (dev stack only), or stop the `gigsim` container.

## Crash and resume (exactly-once)
Threads checkpoint after every node (SQLite/Postgres). Kill the API while a proposal waits for approval, restart, then
approve. The executor's idempotency keys are derived from (thread, payload hash), and the marketplace server's ledger
replays any repeat. Proven by `tests/integration/test_bid_graph.py::test_approval_crash_resume_exactly_once`.

## Change request (policy v2)
Set `GIGSIM_POLICY_VERSION=2` on GigSim. GigBid reads the new surcharge and limits from `get_policy` (pricing,
compliance); `data/policy_pack/rules.yaml` gets `version: 2` and the 3,000-character limit.

## Audit
`python -m mcp_servers.common verify marketplace` checks the hash chain of the marketplace audit log.
