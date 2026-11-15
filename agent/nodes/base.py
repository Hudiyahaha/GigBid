"""Node wrapper: every node gets the same discipline.

  * step budget and token budget per thread -> 'needs_attention' when exceeded (C4)
  * execution trace: node start/end, latency, model usage, tool calls (C2 "execution trace")
  * MarketplaceDown -> status 'queued_retry' (degraded mode, A6); other failures -> 'dead_letter' (C7)
  * per-node usage (tokens, USD, latency) merged into state['usage'] (R8)
Transient errors are re-raised so LangGraph's RetryPolicy can retry the node.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable

from langgraph.errors import GraphBubbleUp

from agent import config, llm, mcp_client
from agent.mcp_client import MarketplaceDown

TERMINAL = {"skipped", "watch", "rejected", "submitted", "needs_attention", "dead_letter", "queued_retry", "blocked",
            "sent", "awaiting_approval"}


class Transient(RuntimeError):
    """Raise to ask LangGraph's RetryPolicy to re-run the node."""


def node(name: str) -> Callable:
    def deco(fn: Callable[[dict], Awaitable[dict]]):
        @functools.wraps(fn)
        async def wrapper(state: dict) -> dict:
            steps = int(state.get("steps", 0)) + 1
            max_steps = int(config.get("budgets.max_graph_steps", 40))
            used = int((state.get("usage") or {}).get("tokens", 0))
            max_tokens = int(config.get("budgets.max_tokens_per_job", 30000))
            if steps > max_steps:
                return {"status": "needs_attention", "attention_reason": f"step budget {max_steps} exceeded at {name}",
                        "steps": 1, "trace": [{"type": "budget", "node": name, "steps": steps}]}
            if used > max_tokens:
                return {"status": "needs_attention", "attention_reason": f"token budget {max_tokens} exceeded before {name}",
                        "steps": 1, "trace": [{"type": "budget", "node": name, "tokens": used}]}
            events: list = []
            tok_events = mcp_client.TRACE_EVENTS.set(events)
            before = llm.CURRENT_USAGE.get() or llm.start_usage()
            snap = (before.tokens_in, before.tokens_out, before.usd, before.calls)
            # absolute ceiling on this run's cumulative counter (state usage already counts earlier nodes once)
            llm.TOKEN_BUDGET.set(before.tokens + max(1, max_tokens - used))
            t0 = time.perf_counter()
            status_update: dict = {}
            try:
                out = await fn(state) or {}
            except MarketplaceDown as e:
                out = {}
                status_update = {"status": "queued_retry", "attention_reason": f"marketplace unavailable during {name}: {e}"[:300],
                                 "errors": [f"{name}: marketplace unavailable"]}
            except llm.BudgetExceeded as e:
                out = {}
                status_update = {"status": "needs_attention", "attention_reason": str(e)}
            except (Transient, GraphBubbleUp):  # retries and interrupt() must reach LangGraph untouched
                raise
            except Exception as e:  # noqa: BLE001
                out = {}
                status_update = {"status": "dead_letter", "attention_reason": f"{name} failed: {type(e).__name__}: {e}"[:300],
                                 "errors": [f"{name}: {type(e).__name__}: {str(e)[:200]}"]}
            finally:
                mcp_client.TRACE_EVENTS.reset(tok_events)
            u = llm.CURRENT_USAGE.get() or before
            d_in, d_out, d_usd, d_calls = u.tokens_in - snap[0], u.tokens_out - snap[1], u.usd - snap[2], u.calls - snap[3]
            lat = time.perf_counter() - t0
            usage = {"tokens": d_in + d_out, "tokens_in": d_in, "tokens_out": d_out, "usd": round(d_usd, 6),
                     "llm_calls": d_calls, "by_node": {name: {"tokens": d_in + d_out, "usd": round(d_usd, 6),
                                                              "latency_s": round(lat, 3), "calls": 1}}}
            trace = [{"type": "node", "node": name, "latency_s": round(lat, 3), "tokens": d_in + d_out,
                      "usd": round(d_usd, 6), "status": status_update.get("status", "ok"), "ts": time.time()}] + events
            merged = {**out, **status_update}
            merged["steps"] = 1
            merged["usage"] = usage
            merged["trace"] = list(out.get("trace", [])) + trace
            if "errors" in out and "errors" in status_update:
                merged["errors"] = out["errors"] + status_update["errors"]
            return merged
        wrapper.node_name = name
        return wrapper
    return deco


def halted(state: dict) -> bool:
    return state.get("status") in {"needs_attention", "dead_letter", "queued_retry", "blocked"}
