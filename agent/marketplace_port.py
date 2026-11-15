"""The single marketplace interface (R1). Nodes call these methods; the port calls the Marketplace MCP server,
which picks the GigSim or live-Upwork adapter from config. Switching marketplaces changes config, not this file
or any node:

    agent graph -> MarketplacePort(role) -> MCP tool call (allowlisted per role)
                -> mcp_servers/marketplace/server.py -> adapters/gigsim.py | adapters/upwork_live.py
"""

from __future__ import annotations

from typing import Any

from agent import mcp_client


class MarketplacePort:
    def __init__(self, role: str):
        self.role = role

    async def _c(self, tool: str, args: dict | None = None) -> Any:
        out = await mcp_client.call(self.role, tool, args or {})
        return out.get("data", out) if isinstance(out, dict) and set(out) == {"data"} else out

    # reads
    async def search_jobs(self, query: str, limit: int = 20, since_tick: int = 0) -> dict:
        return await self._c("search_jobs", {"query": query, "limit": limit, "since_tick": since_tick})

    async def get_job(self, job_id: str) -> dict:
        return await self._c("get_job", {"job_id": job_id})

    async def get_client_history(self, client_id: str) -> dict:
        return await self._c("get_client_history", {"client_id": client_id})

    async def get_connects_balance(self) -> dict:
        return await self._c("get_connects_balance")

    async def get_market_stats(self, category: str | None = None, domain: str | None = None,
                               pay_type: str | None = None) -> dict:
        return await self._c("get_market_stats", {"category": category, "domain": domain, "pay_type": pay_type})

    async def get_policy(self) -> dict:
        return await self._c("get_policy")

    async def list_threads(self) -> dict:
        return await self._c("list_threads")

    async def list_messages(self, thread_id: str) -> dict:
        return await self._c("list_messages", {"thread_id": thread_id})

    async def list_events(self, after: int = 0) -> dict:
        return await self._c("list_events", {"after": after})

    # writes (all take an idempotency key; real calls need a human approval token)
    async def create_proposal_draft(self, payload: dict, idempotency_key: str, dry_run: bool = False,
                                    approval_token: str | None = None) -> dict:
        return await self._c("create_proposal_draft", {**payload, "idempotency_key": idempotency_key, "dry_run": dry_run,
                                                       "approval_token": approval_token})

    async def submit_proposal(self, proposal_id: str, draft_key: str, idempotency_key: str,
                              approval_token: str | None = None) -> dict:
        return await self._c("submit_proposal", {"proposal_id": proposal_id, "draft_idempotency_key": draft_key,
                                                 "idempotency_key": idempotency_key, "approval_token": approval_token})

    async def send_message(self, thread_id: str, body: str, idempotency_key: str, dry_run: bool = False,
                           approval_token: str | None = None) -> dict:
        return await self._c("send_message", {"thread_id": thread_id, "body": body, "idempotency_key": idempotency_key,
                                              "dry_run": dry_run, "approval_token": approval_token})
