"""Scout (Marketplace read).

* `scout_intake` is the bid graph's entry node: it (re)fetches the job through the marketplace port, strips
  injected instructions from the untrusted text, and loads the live platform policy.
* `run_saved_search` is used by the worker on a schedule: search, deduplicate, queue new jobs.
"""

from __future__ import annotations

import hashlib
import re

from agent import policy
from agent.guardrails import injection_signals, strip_injections
from agent.marketplace_port import MarketplacePort
from agent.nodes.base import node


def fingerprint(job: dict) -> str:
    """Dedup key that survives reposts: normalised title + client + budget + first 300 chars of the description."""
    title = re.sub(r"\(reposted\)|[^a-z0-9 ]", "", (job.get("title") or "").lower()).strip()
    desc = re.sub(r"\s+", " ", (job.get("description") or "").lower())[:300]
    b = job.get("budget") or {}
    key = f"{title}|{job.get('client_id')}|{b.get('type')}|{b.get('max')}|{desc}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


@node("scout")
async def scout_intake(state: dict) -> dict:
    port = MarketplacePort("intake")
    job = state.get("job") or {}
    if not job.get("description"):
        job = await port.get_job(state["job_id"])
    live_policy = await port.get_policy()
    clean, removed = strip_injections(job.get("description", ""))
    job = {**job, "clean_description": clean, "injection_removed": removed,
           "injection_signals": injection_signals(job.get("description", ""))}
    return {"job": job, "job_id": job["job_id"], "status": "analysing", "policy": policy.merged(live_policy)}


async def run_saved_search(query: str, since_tick: int = 0, limit: int = 50) -> tuple[list[dict], int | None]:
    port = MarketplacePort("scout")
    out = await port.search_jobs(query, limit=limit, since_tick=since_tick)
    return out.get("jobs", []), out.get("tick")
