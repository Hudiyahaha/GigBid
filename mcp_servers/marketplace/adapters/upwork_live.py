"""Live Upwork adapter (A4): talks to Upwork's OFFICIAL MCP server (https://mcp.upwork.com/mcp) through
MultiServerMCPClient over Streamable HTTP with OAuth 2.1. Tokens are stored encrypted per user
(apps/api/auth/token_store.py). No scraping, no browser automation, no session cookies.

Upwork's own MCP write tools create DRAFTS that the user must confirm on Upwork. GigBid therefore maps:
  create_proposal_draft -> Upwork draft (only after approval in GigBid)
  submit_proposal       -> NOT automated: returns a "confirm on Upwork" link; the human finishes it there
  send_message          -> Upwork message draft (confirmed by the user on Upwork)

Tool names are mapped in agent/config.yaml (marketplace.upwork_live.tool_map) so a rename on Upwork's side
is a config edit. Status: implemented against the MCP spec; not exercised against a live account in this
repository (see docs/RUNBOOK.md, "Live mode").
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from agent import config
from mcp_servers.marketplace.adapters.base import MarketplaceRejected, MarketplaceUnavailable

UPWORK_SCOPES = ["jobs:read", "proposals:write", "messages:write"]


class EncryptedTokenStorage:
    """mcp.client.auth.TokenStorage backed by the encrypted per-user token store."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken

        from apps.api.auth import token_store
        d = (token_store.get(self.user_id, "upwork") or {}).get("tokens")
        return OAuthToken(**d) if d else None

    async def set_tokens(self, tokens) -> None:
        from apps.api.auth import token_store
        cur = token_store.get(self.user_id, "upwork") or {}
        cur["tokens"] = tokens.model_dump(mode="json")
        token_store.put(self.user_id, "upwork", cur)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull

        from apps.api.auth import token_store
        d = (token_store.get(self.user_id, "upwork") or {}).get("client_info")
        return OAuthClientInformationFull(**d) if d else None

    async def set_client_info(self, info) -> None:
        from apps.api.auth import token_store
        cur = token_store.get(self.user_id, "upwork") or {}
        cur["client_info"] = info.model_dump(mode="json")
        token_store.put(self.user_id, "upwork", cur)


# OAuth flow state shared with the API's /auth/upwork/* routes: state -> future(code)
PENDING_AUTH: dict[str, dict] = {}


def oauth_provider(user_id: str, redirect_uri: str):
    """Build the MCP SDK's OAuth 2.1 client (dynamic registration + PKCE). The web UI opens the authorization
    URL; /auth/upwork/callback resolves the waiting future with the code."""
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    async def redirect_handler(url: str) -> None:
        PENDING_AUTH[user_id] = {"url": url, "future": asyncio.get_running_loop().create_future(), "ts": time.time()}

    async def callback_handler() -> tuple[str, str | None]:
        return await asyncio.wait_for(PENDING_AUTH[user_id]["future"], timeout=600)

    return OAuthClientProvider(
        server_url=config.get("marketplace.upwork_live.mcp_url", "https://mcp.upwork.com/mcp"),
        client_metadata=OAuthClientMetadata(client_name="GigBid", redirect_uris=[redirect_uri],
                                            grant_types=["authorization_code", "refresh_token"],
                                            response_types=["code"], scope=" ".join(UPWORK_SCOPES)),
        storage=EncryptedTokenStorage(user_id), redirect_handler=redirect_handler, callback_handler=callback_handler)


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, user_id: str, redirect_uri: str = "http://localhost:8000/auth/upwork/callback"):
        self.user_id = user_id
        self.redirect_uri = redirect_uri
        self.tool_map: dict[str, str] = config.get("marketplace.upwork_live.tool_map", {}) or {}
        self._tools: dict[str, Any] | None = None

    async def _load_tools(self) -> dict[str, Any]:
        if self._tools is None:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            client = MultiServerMCPClient({"upwork": {
                "transport": "streamable_http",
                "url": config.get("marketplace.upwork_live.mcp_url", "https://mcp.upwork.com/mcp"),
                "auth": oauth_provider(self.user_id, self.redirect_uri)}})
            try:
                tools = await client.get_tools()
            except (httpx.HTTPError, OSError) as e:
                raise MarketplaceUnavailable(f"Upwork MCP unreachable: {type(e).__name__}") from e
            self._tools = {t.name: t for t in tools}
        return self._tools

    async def _call(self, op: str, args: dict) -> dict:
        name = self.tool_map.get(op)
        if not name:
            raise MarketplaceRejected(501, f"operation {op} is not available in live mode")
        tools = await self._load_tools()
        if name not in tools:
            raise MarketplaceRejected(501, f"Upwork MCP has no tool '{name}' (update marketplace.upwork_live.tool_map)")
        try:
            out = await tools[name].ainvoke(args)
        except Exception as e:  # noqa: BLE001
            raise MarketplaceUnavailable(f"Upwork tool {name} failed: {type(e).__name__}") from e
        if isinstance(out, str):
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"text": out}
        return out if isinstance(out, dict) else {"result": out}

    @staticmethod
    def _norm_job(j: dict) -> dict:
        """Map Upwork job fields onto GigSim's job shape so the graph cannot tell the difference."""
        budget = j.get("budget") or {}
        return {"job_id": str(j.get("id") or j.get("job_id") or j.get("ciphertext", "")), "title": j.get("title", ""),
                "description": j.get("description") or j.get("snippet", ""), "category": j.get("category", ""),
                "skills_tags": [s.get("name", s) if isinstance(s, dict) else s for s in j.get("skills", [])],
                "budget": {"type": "hourly" if j.get("hourly") or budget.get("type") == "hourly" else "fixed",
                           "min": budget.get("min") or j.get("hourlyBudgetMin") or 0,
                           "max": budget.get("max") or j.get("amount") or j.get("hourlyBudgetMax") or 0, "currency": "USD"},
                "client_id": str((j.get("client") or {}).get("id", "")), "posted_at": j.get("createdDateTime", ""),
                "connects_cost": int(j.get("connectPrice") or j.get("connects_cost") or 0),
                "screening_questions": [q.get("question", q) if isinstance(q, dict) else q for q in j.get("questions", [])],
                "proposals_count": j.get("totalApplicants", 0), "source": "upwork_live"}

    async def search_jobs(self, query: str, limit: int = 20, since_tick: int = 0, category: str | None = None) -> dict:
        out = await self._call("search_jobs", {"query": query, "limit": limit})
        jobs = out.get("jobs") or out.get("results") or []
        return {"total": len(jobs), "jobs": [self._norm_job(j) for j in jobs]}

    async def get_job(self, job_id: str) -> dict:
        return self._norm_job(await self._call("get_job", {"job_id": job_id}))

    async def get_client_history(self, client_id: str) -> dict:
        return await self._call("get_client_history", {"client_id": client_id})

    async def get_connects_balance(self) -> dict:
        out = await self._call("get_connects_balance", {})
        return {"connects_balance": out.get("connects_balance") or out.get("balance"), "source": "upwork_live"}

    async def get_market_stats(self, category, domain, pay_type) -> dict:
        return {"n": 0, "note": "Upwork exposes no market statistics; pricing falls back to Kaggle-derived priors"}

    async def get_policy(self) -> dict:
        return {"version": "upwork", "rules": ["See Upwork Terms of Service"], "connects": {"surcharge_unverified_client": 0},
                "limits": {"max_submissions_per_day": None, "max_cover_letter_chars": 5000}}

    async def list_threads(self) -> dict:
        return {"threads": [], "note": "message sync in live mode is read on demand"}

    async def list_messages(self, thread_id: str) -> dict:
        return {"thread": {"id": thread_id}, "messages": []}

    async def list_proposals(self) -> dict:
        return {"proposals": []}

    async def list_events(self, after: int = 0) -> dict:
        return {"events": []}

    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict:
        out = await self._call("create_proposal_draft", {"job_id": payload["job_id"], "cover_letter": payload["cover_letter"],
                                                         "bid_amount": payload["bid_amount"],
                                                         "answers": payload.get("screening_answers", [])})
        return {"proposal_id": str(out.get("id") or out.get("draft_id") or idempotency_key), "status": "drafted",
                "connects_cost": out.get("connects_cost", 0), "confirm_url": out.get("url")}

    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict:
        # Upwork requires the human to confirm drafts on Upwork itself; GigBid never auto-submits in live mode.
        return {"proposal_id": proposal_id, "status": "awaiting_confirmation_on_upwork",
                "detail": "Open the draft on Upwork and confirm it there.", "connects_spent": 0}

    async def send_message(self, thread_id: str, body: str, idempotency_key: str) -> dict:
        out = await self._call("send_message", {"thread_id": thread_id, "body": body})
        return {"message_id": str(out.get("id", idempotency_key)), "status": "draft_on_upwork"}
