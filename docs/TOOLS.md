# MCP tools

Every capability the agents use is an MCP tool with a schema, annotations and a test. Agents get tools by name through
per-role allowlists (`agent/config.yaml: tool_allowlists`). Schemas are snapshot-tested (`tests/contract/snapshots/`).

| Tool | Server | R/W | Annotations | Auth |
|---|---|---|---|---|
| search_evidence(requirement, k, filters) | portfolio | read | readOnly, idempotent | bearer `PORTFOLIO_MCP_TOKEN` (http) / none (stdio) |
| get_case_study(id) | portfolio | read | readOnly, idempotent | same |
| get_item(id) | portfolio | read | readOnly, idempotent | same |
| list_skills() | portfolio | read | readOnly, idempotent | same |
| similar_proposals(query, k) | portfolio | read | readOnly, idempotent | same |
| resources `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{id}`, `portfolio://cv` | portfolio | read | - | same |
| prompts: answer_screening_question, fit_for_job, case_blurb | portfolio | - | - | same |
| search_jobs(query, limit, since_tick, category) | marketplace | read | readOnly, idempotent, openWorld | bearer `MARKETPLACE_MCP_TOKEN`; per-user rate limit |
| get_job(job_id) | marketplace | read | readOnly, idempotent, openWorld | same |
| get_client_history(client_id) | marketplace | read | readOnly, idempotent, openWorld | same |
| get_connects_balance() | marketplace | read | readOnly, idempotent, openWorld | same |
| get_market_stats(category, domain, pay_type) | marketplace | read | readOnly, idempotent, openWorld | same |
| get_policy() | marketplace | read | readOnly, idempotent, openWorld | same |
| list_threads / list_messages(thread_id) / list_proposals / list_events(after) | marketplace | read | readOnly, idempotent, openWorld | same |
| create_proposal_draft(..., idempotency_key, dry_run, approval_token) | marketplace | write | not readOnly, not destructive, idempotent | bearer + **human approval token** (HMAC, bound to user + payload) |
| submit_proposal(proposal_id, draft_idempotency_key, idempotency_key, dry_run, approval_token) | marketplace | write | **destructive** (spends Connects), idempotent | bearer + approval token |
| send_message(thread_id, body, idempotency_key, dry_run, approval_token) | marketplace | write | destructive, idempotent | bearer + approval token |
| free_slots(days, duration_min, max_slots) | workspace | read | readOnly, idempotent | bearer `WORKSPACE_MCP_TOKEN` |
| create_interview_hold(start, title, idempotency_key, dry_run) | workspace | write | not destructive, idempotent | same |
| create_email_draft(to_name, subject, body, idempotency_key, dry_run) | workspace | write | not destructive, idempotent (never sends) | same |

Every write: idempotency key -> exactly-once ledger (`apps/api/db.py: Submission`); `dry_run` returns the exact payload
and Connects cost; every call is written to a hash-chained, PII-masked audit log with the run's trace id
(`python -m mcp_servers.common verify marketplace`).

## Third-party servers (A5)
| Server | Used for | Trust rationale |
|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`, OAuth 2.1) | live-mode marketplace adapter (`mcp_servers/marketplace/adapters/upwork_live.py`) | First-party server run by the platform itself; every write is a draft the user confirms on Upwork, so GigBid can never submit on its own. |
| GitHub MCP server (`github/github-mcp-server`, read-only token) | repo ingestion for the portfolio (`GITHUB_MCP_COMMAND`) | Official GitHub server; used with a fine-grained read-only token limited to the user's public repos, so it cannot change anything. |

## R&D question A (tool granularity)
Runner: `evals/runners/tool_study.py` (see HANDOFF.md if results are missing). Variants: fine-grained (as above),
coarse (`marketplace(action, ...)`), and the fine-grained set with rewritten descriptions.
