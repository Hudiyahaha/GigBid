"""Shared plumbing for GigBid's MCP servers: bearer auth, trace/user context, append-only audit log,
per-user rate limiting and a runner for stdio / streamable-http transports."""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from agent.guardrails import mask_obj

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = Path(os.getenv("AUDIT_DIR", ROOT / "data" / "processed" / "audit"))

TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")
USER_ID: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="local")
PERSONA: contextvars.ContextVar[str] = contextvars.ContextVar("persona", default="")


def request_context(ctx: Any) -> dict[str, str]:
    """Pull trace id / user / persona from the HTTP request headers (streamable-http) or env (stdio, tests)."""
    headers: dict[str, str] = {}
    try:
        req = ctx.request_context.request
        if req is not None:
            headers = {k.lower(): v for k, v in req.headers.items()}
    except Exception:  # noqa: BLE001 - no request in stdio / in-memory transport
        pass
    out = {"trace_id": headers.get("x-trace-id") or TRACE_ID.get(),
           "user_id": headers.get("x-gigbid-user") or os.getenv("GIGBID_USER", USER_ID.get()),
           "persona": headers.get("x-gigbid-persona") or os.getenv("PORTFOLIO_PERSONA", PERSONA.get())}
    TRACE_ID.set(out["trace_id"])
    USER_ID.set(out["user_id"])
    return out


class AuditLog:
    """Append-only JSONL with a hash chain: each record stores the hash of the previous one, so any edit or
    deletion breaks verification (`python -m mcp_servers.common verify`)."""

    def __init__(self, name: str):
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        self.path = AUDIT_DIR / f"{name}.jsonl"
        self._lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        with open(self.path, "rb") as f:
            try:
                f.seek(-4096, os.SEEK_END)
            except OSError:
                f.seek(0)
            lines = f.read().splitlines()
        return json.loads(lines[-1])["hash"] if lines else "0" * 64

    def write(self, tool: str, args: dict, result: Any, status: str = "ok") -> None:
        with self._lock:
            rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "trace_id": TRACE_ID.get(), "user": USER_ID.get(),
                   "tool": tool, "args": mask_obj(args), "result": mask_obj(result), "status": status,
                   "prev": self._last_hash()}
            rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")

    def verify(self) -> tuple[bool, int]:
        prev = "0" * 64
        n = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            h = rec.pop("hash")
            if rec["prev"] != prev or hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest() != h:
                return False, n
            prev = h
            n += 1
        return True, n


class RateLimiter:
    """Per-user sliding-window limiter that waits (politely) instead of failing."""

    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self.hits: dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def acquire(self, user: str) -> float:
        waited = 0.0
        while True:
            async with self._lock:
                q = self.hits[user]
                now = time.monotonic()
                while q and now - q[0] > 60:
                    q.popleft()
                if len(q) < self.per_minute:
                    q.append(now)
                    return waited
                delay = 60 - (now - q[0]) + 0.05
            await asyncio.sleep(delay)
            waited += delay


def bearer_app(app, token_env: str):
    """Wrap a Starlette ASGI app so every request needs `Authorization: Bearer $token_env` (if set)."""
    expected = os.getenv(token_env, "")

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and expected:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if headers.get("authorization", "") != f"Bearer {expected}":
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await app(scope, receive, send)

    return wrapped


def run(mcp, default_port: int, token_env: str | None = None) -> None:
    """`python -m mcp_servers.X.server [stdio|http]` - stdio for Claude Desktop/Cursor, http for docker."""
    import sys

    transport = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("MCP_TRANSPORT", "stdio")).lower()
    if transport == "stdio":
        mcp.run("stdio")
        return
    import uvicorn

    app = mcp.streamable_http_app()
    if token_env:
        app = bearer_app(app, token_env)
    uvicorn.run(app, host=os.getenv("MCP_HOST", "0.0.0.0"), port=int(os.getenv("MCP_PORT", default_port)), log_level="warning")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "verify":
        ok, n = AuditLog(sys.argv[2]).verify()
        print(f"audit log {sys.argv[2]}: {'OK' if ok else 'TAMPERED'} ({n} records verified)")
