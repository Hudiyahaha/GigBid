"""Run / resume / replay graph threads. Used by the API, the worker and the evaluation scripts.

Every run gets one trace id that flows into the MCP headers, the audit log and the OpenTelemetry spans (E3).
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langgraph.types import Command

from agent import config, llm, mcp_client
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph

ROOT = Path(__file__).resolve().parents[1]
EventFn = Callable[[dict], Awaitable[None]] | None


class Graphs:
    def __init__(self, checkpointer, store):
        self.bid = build_bid_graph(checkpointer, store)
        self.conversation = build_conversation_graph(checkpointer, store)

    def get(self, kind: str):
        return self.bid if kind == "bid" else self.conversation


def default_prefs(persona: str) -> dict:
    p = ROOT / "data" / "personas" / persona / "profile.json"
    prof = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {"hourly_floor": prof.get("hourly_floor_usd", 30), "min_project": prof.get("min_project_usd", 100),
            "weekly_connects_budget": prof.get("weekly_connects_budget", 80), "connects_spent_week": 0,
            "autonomy": config.get("autonomy.default_level", "suggest"), "strategy": config.get("writer.default_strategy")}


def cfg(thread_id: str, checkpoint_id: str | None = None) -> dict:
    c: dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": int(config.get("budgets.max_graph_steps", 40)) + 10}
    if checkpoint_id:
        c["configurable"]["checkpoint_id"] = checkpoint_id
    return c


def _summarise(update: Any) -> dict:
    if not isinstance(update, dict):
        return {}
    keep = {}
    for k in ("status", "decision", "attention_reason", "submission", "sent"):
        if k in update:
            keep[k] = update[k]
    for k, f in (("risk", "score"), ("fit", "score"), ("price", "amount")):
        if isinstance(update.get(k), dict):
            keep[k] = update[k].get(f)
    if isinstance(update.get("draft"), dict):
        keep["draft_version"] = update["draft"].get("version")
    if isinstance(update.get("critiques"), list) and update["critiques"]:
        keep["critique_passed"] = update["critiques"][-1].get("passed")
    if "usage" in update:
        keep["tokens"] = update["usage"].get("tokens")
    return keep


async def _drive(graph, payload: Any, thread_id: str, ctx: dict, on_event: EventFn) -> dict:
    mcp_client.RUN_CTX.set(ctx)
    usage = llm.start_usage(int(config.get("budgets.max_tokens_per_job", 30000)))
    t0 = time.perf_counter()
    async for chunk in graph.astream(payload, cfg(thread_id), stream_mode="updates"):
        for node_name, update in chunk.items():
            if on_event:
                await on_event({"type": "node", "node": node_name, "t": round(time.perf_counter() - t0, 3), **_summarise(update)})
    snap = await graph.aget_state(cfg(thread_id))
    interrupts = [i.value for t in snap.tasks for i in (t.interrupts or [])]
    out = {"thread_id": thread_id, "trace_id": ctx.get("trace_id"), "values": snap.values, "next": list(snap.next),
           "interrupt": interrupts[0] if interrupts else None, "latency_s": round(time.perf_counter() - t0, 3),
           "usage": usage.as_dict()}
    if on_event:
        await on_event({"type": "done", "status": snap.values.get("status"), "interrupt": bool(interrupts)})
    return out


async def start_bid(graphs: Graphs, job_id: str, user_id: str, persona: str, prefs: dict | None = None,
                    strategy: str | None = None, job: dict | None = None, thread_id: str | None = None,
                    trace_id: str | None = None, on_event: EventFn = None) -> dict:
    thread_id = thread_id or f"{user_id}:bid:{job_id}"
    trace_id = trace_id or uuid.uuid4().hex
    state = {"thread_id": thread_id, "user_id": user_id, "persona": persona, "trace_id": trace_id, "job_id": job_id,
             "job": job or {}, "prefs": prefs or default_prefs(persona), "strategy": strategy, "revisions": 0}
    return await _drive(graphs.bid, state, thread_id, {"trace_id": trace_id, "user_id": user_id, "persona": persona}, on_event)


async def start_conversation(graphs: Graphs, marketplace_thread_id: str, user_id: str, persona: str, job: dict | None = None,
                             proposal: dict | None = None, prefs: dict | None = None, thread_id: str | None = None,
                             trace_id: str | None = None, on_event: EventFn = None) -> dict:
    thread_id = thread_id or f"{user_id}:conv:{marketplace_thread_id}:{uuid.uuid4().hex[:6]}"
    trace_id = trace_id or uuid.uuid4().hex
    state = {"thread_id": thread_id, "user_id": user_id, "persona": persona, "trace_id": trace_id,
             "marketplace_thread_id": marketplace_thread_id, "job": job or {}, "proposal": proposal or {},
             "prefs": prefs or default_prefs(persona)}
    return await _drive(graphs.conversation, state, thread_id, {"trace_id": trace_id, "user_id": user_id, "persona": persona}, on_event)


async def resume(graphs: Graphs, kind: str, thread_id: str, decision: dict, user_id: str, persona: str,
                 trace_id: str | None = None, on_event: EventFn = None) -> dict:
    """Resume an interrupted thread with the human's decision (approve / edit / reject)."""
    g = graphs.get(kind)
    snap = await g.aget_state(cfg(thread_id))
    trace_id = trace_id or snap.values.get("trace_id") or uuid.uuid4().hex
    return await _drive(g, Command(resume=decision), thread_id, {"trace_id": trace_id, "user_id": user_id, "persona": persona}, on_event)


async def continue_thread(graphs: Graphs, kind: str, thread_id: str, user_id: str, persona: str, on_event: EventFn = None) -> dict:
    """Continue a thread from its last checkpoint (after a crash, or after the marketplace came back)."""
    g = graphs.get(kind)
    snap = await g.aget_state(cfg(thread_id))
    return await _drive(g, None, thread_id, {"trace_id": snap.values.get("trace_id", uuid.uuid4().hex), "user_id": user_id,
                                             "persona": persona}, on_event)


async def history(graphs: Graphs, kind: str, thread_id: str) -> list[dict]:
    out = []
    async for s in graphs.get(kind).aget_state_history(cfg(thread_id)):
        out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"], "next": list(s.next),
                    "status": s.values.get("status"), "step": s.metadata.get("step") if s.metadata else None,
                    "created_at": s.created_at})
    return out


async def replay(graphs: Graphs, kind: str, thread_id: str, checkpoint_id: str, user_id: str, persona: str,
                 on_event: EventFn = None) -> dict:
    """Re-run a thread from any earlier checkpoint (C6 time travel). Idempotency keys keep writes exactly-once."""
    g = graphs.get(kind)
    mcp_client.RUN_CTX.set({"trace_id": uuid.uuid4().hex, "user_id": user_id, "persona": persona})
    llm.start_usage()
    async for chunk in g.astream(None, cfg(thread_id, checkpoint_id), stream_mode="updates"):
        if on_event:
            for n, u in chunk.items():
                await on_event({"type": "node", "node": n, **_summarise(u)})
    snap = await g.aget_state(cfg(thread_id))
    interrupts = [i.value for t in snap.tasks for i in (t.interrupts or [])]
    return {"thread_id": thread_id, "values": snap.values, "interrupt": interrupts[0] if interrupts else None}
