"""MCP client for the agents: MultiServerMCPClient over Streamable HTTP (deployed) or the same servers over
MCP's in-memory transport (local dev, evals, tests). Either way the agents only ever see MCP tools.

A6 client discipline:
  * per-agent allowlists (agent/config.yaml `tool_allowlists`) - a node cannot call a tool it was not given
  * timeouts and bounded retries with backoff on transport errors
  * MARKETPLACE_UNAVAILABLE surfaces as MarketplaceDown so the graph degrades (queue + retry later)
  * every call is appended to the execution trace (tool, masked args, result summary, latency, ok)
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any

from agent import config
from agent.guardrails import mask_obj

TRACE_EVENTS: contextvars.ContextVar[list | None] = contextvars.ContextVar("trace_events", default=None)
RUN_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("run_ctx", default={})

SERVER_OF: dict[str, str] = {
    # portfolio
    "search_evidence": "portfolio", "get_case_study": "portfolio", "get_item": "portfolio", "list_skills": "portfolio",
    # marketplace
    "search_jobs": "marketplace", "get_job": "marketplace", "get_client_history": "marketplace",
    "get_connects_balance": "marketplace", "get_market_stats": "marketplace", "get_policy": "marketplace",
    "list_threads": "marketplace", "list_messages": "marketplace", "list_proposals": "marketplace",
    "list_events": "marketplace", "create_proposal_draft": "marketplace", "submit_proposal": "marketplace",
    "send_message": "marketplace",
    # workspace
    "free_slots": "workspace", "create_interview_hold": "workspace", "create_email_draft": "workspace",
}


class ToolNotAllowed(PermissionError):
    pass


class MarketplaceDown(RuntimeError):
    """The marketplace is unreachable after retries: the UI shows a banner and the job is re-queued."""


class ToolCallError(RuntimeError):
    def __init__(self, tool: str, message: str):
        super().__init__(f"{tool}: {message}")
        self.tool = tool
        self.message = message


def mode() -> str:
    return os.getenv("MCP_MODE", "inproc")  # inproc | http


def allowed(role: str) -> list[str]:
    return list((config.get("tool_allowlists", {}) or {}).get(role, []))


def _headers(server: str) -> dict[str, str]:
    ctx = RUN_CTX.get()
    h = {"X-Trace-Id": ctx.get("trace_id", "-"), "X-GigBid-User": ctx.get("user_id", "local"),
         "X-GigBid-Persona": ctx.get("persona", "")}
    tok = os.getenv(f"{server.upper()}_MCP_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def connections() -> dict[str, dict]:
    servers = config.get("mcp_servers", {}) or {}
    out = {}
    for name in ("portfolio", "marketplace", "workspace"):
        url = (servers.get(name) or {}).get("url")
        out[name] = {"transport": "streamable_http", "url": url, "headers": _headers(name),
                     "timeout": float(config.get("marketplace.timeouts_s.write", 30))}
    return out


def _server_module(name: str):
    if name == "portfolio":
        from mcp_servers.portfolio.server import mcp
    elif name == "marketplace":
        from mcp_servers.marketplace.server import mcp
    else:
        from mcp_servers.workspace.server import mcp
    return mcp


@asynccontextmanager
async def session(server: str):
    """An initialised MCP ClientSession to one server, carrying trace/user/persona context."""
    if mode() == "http":
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({server: connections()[server]})
        async with client.session(server) as s:
            yield s
    else:
        from mcp.shared.memory import create_connected_server_and_client_session

        from mcp_servers import common
        ctx = RUN_CTX.get()
        common.TRACE_ID.set(ctx.get("trace_id", "-"))
        common.USER_ID.set(ctx.get("user_id", "local"))
        common.PERSONA.set(ctx.get("persona", ""))
        async with create_connected_server_and_client_session(_server_module(server)) as s:
            yield s


def _record(ev: dict) -> None:
    lst = TRACE_EVENTS.get()
    if lst is not None:
        lst.append(ev)


async def call(role: str, tool: str, args: dict | None = None, *, retries: int | None = None) -> dict:
    """Call one MCP tool on behalf of an agent role. Returns the tool's structured output."""
    args = {k: v for k, v in (args or {}).items() if v is not None}
    if tool not in allowed(role):
        _record({"type": "tool", "node": role, "tool": tool, "ok": False, "error": "not allowed"})
        raise ToolNotAllowed(f"agent '{role}' may not call '{tool}'")
    server = SERVER_OF[tool]
    r = config.get("marketplace.retries", {}) or {}
    attempts = retries if retries is not None else int(r.get("max_attempts", 4))
    timeout = float(config.get("marketplace.timeouts_s.write" if tool.startswith(("create", "submit", "send")) else
                               "marketplace.timeouts_s.read", 30)) * 2
    t0 = time.perf_counter()
    last = ""
    for i in range(1, attempts + 1):
        try:
            async with session(server) as s:
                res = await asyncio.wait_for(s.call_tool(tool, args), timeout=timeout)
        except (OSError, asyncio.TimeoutError, ConnectionError) as e:
            last = f"{type(e).__name__}: {e}"
        except Exception as e:  # noqa: BLE001 - e.g. httpx/anyio errors wrapped in ExceptionGroup
            last = f"{type(e).__name__}: {str(e)[:200]}"
        else:
            text = res.content[0].text if res.content and hasattr(res.content[0], "text") else ""
            if res.isError:
                ok_down = "MARKETPLACE_UNAVAILABLE" in text
                _record({"type": "tool", "node": role, "tool": tool, "args": mask_obj(args), "ok": False,
                         "error": text[:300], "latency_ms": round((time.perf_counter() - t0) * 1000)})
                if ok_down:
                    raise MarketplaceDown(text)
                raise ToolCallError(tool, text)
            out = res.structuredContent
            if out is None:
                try:
                    out = json.loads(text)
                except json.JSONDecodeError:
                    out = {"text": text}
            if isinstance(out, dict) and set(out) == {"result"}:
                out = out["result"]
            _record({"type": "tool", "node": role, "tool": tool, "args": mask_obj(args), "ok": True,
                     "result": _summary(out), "latency_ms": round((time.perf_counter() - t0) * 1000)})
            return out
        if i < attempts:
            await asyncio.sleep(min(8.0, 0.5 * 2 ** (i - 1)) * (0.5 + random.random()))
    _record({"type": "tool", "node": role, "tool": tool, "args": mask_obj(args), "ok": False, "error": last})
    if server == "marketplace":
        raise MarketplaceDown(f"{tool}: {last}")
    raise ToolCallError(tool, last)


def _summary(out: Any) -> Any:
    if isinstance(out, dict):
        if "items" in out:
            return {"items": [i.get("item_id") for i in out["items"]][:10]}
        if "jobs" in out:
            return {"jobs": len(out["jobs"])}
        return {k: (v if isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) < 80) else "...")
                for k, v in list(out.items())[:8]}
    return str(out)[:120]


async def langchain_tools(role: str | None = None) -> list:
    """LangChain tool objects for LLM tool-calling (ReAct baseline, tool-design study), filtered by role."""
    names = set(allowed(role)) if role else set(SERVER_OF)
    tools = []
    for server in ("portfolio", "marketplace", "workspace"):
        if mode() == "http":
            from langchain_mcp_adapters.client import MultiServerMCPClient
            client = MultiServerMCPClient({server: connections()[server]})
            ts = await client.get_tools(server_name=server)
        else:
            ts = await _inproc_tools(server)
        tools += [t for t in ts if t.name in names]
    return tools


async def _inproc_tools(server: str) -> list:
    """Wrap in-memory MCP tools as LangChain StructuredTools (one session per call)."""
    from langchain_core.tools import StructuredTool

    async with session(server) as s:
        listed = (await s.list_tools()).tools
    out = []
    for t in listed:
        async def _run(_name=t.name, **kwargs):
            return json.dumps(await call("__all__", _name, kwargs), default=str)
        out.append(StructuredTool.from_function(coroutine=_run, name=t.name, description=t.description or "",
                                                args_schema=t.inputSchema))
    return out
