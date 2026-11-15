"""Agent run viewer: list runs, stream node-by-node progress (SSE), checkpoint history and replay."""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from agent import runner
from apps.api import services
from apps.api.db import Run, User, session
from apps.api.schemas import RunOut
from apps.api.security import current_user, issue

router = APIRouter(tags=["runs"])


def trace_url(run_id: str) -> str | None:
    base = os.getenv("PHOENIX_UI_URL")
    return f"{base}/projects?traceId={run_id}" if base else None


def run_out(r: Run, events: bool = False) -> dict:
    d = {"id": r.id, "graph": r.graph, "thread_id": r.thread_id, "ref": r.ref, "status": r.status, "started": r.started,
         "finished": r.finished, "latency_s": r.latency_s, "tokens": r.tokens, "usd": r.usd, "trace_url": trace_url(r.id)}
    if events:
        d["events"], d["usage"] = r.events, r.usage
    return d


@router.get("/runs")
def runs(u: User = Depends(current_user)) -> list[dict]:
    with session() as s:
        rows = s.execute(select(Run).where(Run.user_id == u.id).order_by(Run.started.desc()).limit(100)).scalars().all()
    return [run_out(r) for r in rows]


@router.get("/runs/{run_id}")
def run(run_id: str, u: User = Depends(current_user)) -> dict:
    with session() as s:
        r = s.get(Run, run_id)
    if not r or r.user_id != u.id:
        raise HTTPException(404, "run not found")
    return run_out(r, events=True)


@router.get("/runs/{run_id}/stream")
async def stream(run_id: str, request: Request, token: str) -> EventSourceResponse:
    """SSE (EventSource cannot send headers, so the session token comes as a query parameter)."""
    import jwt

    from apps.api.security import (
        _bearer,  # noqa: F401
        _secret,
    )
    try:
        uid = jwt.decode(token, _secret(), algorithms=["HS256"])["sub"]
    except jwt.PyJWTError as e:
        raise HTTPException(401, "invalid session") from e

    async def gen():
        sent = 0
        while True:
            if await request.is_disconnected():
                return
            with session() as s:
                r = s.get(Run, run_id)
            if not r or r.user_id != uid:
                yield {"event": "error", "data": "run not found"}
                return
            evs = r.events or []
            for ev in evs[sent:]:
                yield {"event": "node", "data": json.dumps(ev, default=str)}
            sent = len(evs)
            if r.status != "running":
                yield {"event": "end", "data": json.dumps(run_out(r), default=str)}
                return
            await asyncio.sleep(0.4)
    return EventSourceResponse(gen())


@router.get("/threads/{thread_id}/history")
async def thread_history(thread_id: str, kind: str = "bid", u: User = Depends(current_user)) -> list[dict]:
    if not thread_id.startswith(u.id + ":"):
        raise HTTPException(404, "thread not found")
    return await runner.history(services.GRAPHS, kind, thread_id)


@router.post("/threads/{thread_id}/replay", response_model=RunOut)
async def thread_replay(thread_id: str, checkpoint_id: str, kind: str = "bid", u: User = Depends(current_user)) -> RunOut:
    if not thread_id.startswith(u.id + ":"):
        raise HTTPException(404, "thread not found")
    rid = services.new_run(u.id, kind, thread_id, "replay")

    async def go(emit):
        return await runner.replay(services.GRAPHS, kind, thread_id, checkpoint_id, u.id, u.persona, on_event=emit)
    services._spawn(services._run(rid, u, kind, thread_id.split(":")[-1], go))
    return RunOut(run_id=rid)


_ = issue
