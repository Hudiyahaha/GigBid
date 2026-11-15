"""GigSim REST adapter: timeouts, bounded retries with exponential backoff + jitter, honours Retry-After on 429,
retries 5xx / connection errors, and raises MarketplaceUnavailable when GigSim stays down."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from agent import config
from mcp_servers.marketplace.adapters.base import MarketplaceRejected, MarketplaceUnavailable


class GigSimAdapter:
    name = "gigsim"

    def __init__(self, token: str, base_url: str | None = None, trace_id: str = "-"):
        self.base_url = (base_url or config.get("marketplace.gigsim.base_url", "http://localhost:8081")).rstrip("/")
        self.token = token
        self.trace_id = trace_id
        r = config.get("marketplace.retries", {}) or {}
        self.max_attempts = int(r.get("max_attempts", 4))
        self.backoff_base = float(r.get("backoff_base_s", 0.8))
        self.backoff_max = float(r.get("backoff_max_s", 10))
        t = config.get("marketplace.timeouts_s", {}) or {}
        self.t_read, self.t_write = float(t.get("read", 15)), float(t.get("write", 30))

    async def _req(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None,
                   idem: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "X-Trace-Id": self.trace_id}
        if idem:
            headers["Idempotency-Key"] = idem
        timeout = self.t_write if method != "GET" else self.t_read
        last = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as c:
                    resp = await c.request(method, self.base_url + path, params=params, json=json, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last = f"{type(e).__name__}"
                resp = None
            if resp is not None:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code == 429:
                    last = "rate limited"
                    wait = float(resp.headers.get("Retry-After", "2"))
                    if attempt < self.max_attempts:
                        await asyncio.sleep(min(wait, 30))
                        continue
                elif resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:  # noqa: BLE001
                        detail = resp.text
                    raise MarketplaceRejected(resp.status_code, str(detail))
            if attempt < self.max_attempts:
                delay = min(self.backoff_max, self.backoff_base * 2 ** (attempt - 1)) * (0.5 + random.random())
                await asyncio.sleep(delay)
        raise MarketplaceUnavailable(f"GigSim unavailable after {self.max_attempts} attempts ({last})")

    async def search_jobs(self, query: str, limit: int = 20, since_tick: int = 0, category: str | None = None) -> dict:
        p = {"q": query, "limit": limit, "since_tick": since_tick}
        if category:
            p["category"] = category
        return await self._req("GET", "/jobs", params=p)

    async def get_job(self, job_id: str) -> dict:
        return await self._req("GET", f"/jobs/{job_id}")

    async def get_client_history(self, client_id: str) -> dict:
        return await self._req("GET", f"/clients/{client_id}")

    async def get_connects_balance(self) -> dict:
        return await self._req("GET", "/me")

    async def get_market_stats(self, category: str | None, domain: str | None, pay_type: str | None) -> dict:
        p = {k: v for k, v in {"category": category, "domain": domain, "pay_type": pay_type}.items() if v}
        return await self._req("GET", "/market/stats", params=p)

    async def get_policy(self) -> dict:
        return await self._req("GET", "/policy")

    async def list_threads(self) -> dict:
        return await self._req("GET", "/threads")

    async def list_messages(self, thread_id: str) -> dict:
        return await self._req("GET", f"/threads/{thread_id}/messages")

    async def list_proposals(self) -> dict:
        return await self._req("GET", "/proposals")

    async def list_events(self, after: int = 0) -> dict:
        return await self._req("GET", "/events", params={"after": after})

    async def create_proposal_draft(self, payload: dict, idempotency_key: str) -> dict:
        return await self._req("POST", "/proposals", json=payload, idem=idempotency_key)

    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> dict:
        return await self._req("POST", f"/proposals/{proposal_id}/submit", idem=idempotency_key)

    async def send_message(self, thread_id: str, body: str, idempotency_key: str) -> dict:
        return await self._req("POST", f"/threads/{thread_id}/messages", json={"body": body}, idem=idempotency_key)
