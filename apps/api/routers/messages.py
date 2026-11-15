from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from agent import mcp_client
from apps.api import services
from apps.api.db import InboxJob, User, session
from apps.api.schemas import RunOut
from apps.api.security import current_user

router = APIRouter(tags=["messages"])


async def _read(u: User, tool: str, args: dict) -> dict:
    mcp_client.RUN_CTX.set({"trace_id": "ui", "user_id": u.id, "persona": u.persona})
    return await mcp_client.call("api_reader", tool, args)


@router.get("/messages/threads")
async def threads(u: User = Depends(current_user)) -> list[dict]:
    data = await _read(u, "list_threads", {})
    out = data.get("data", data).get("threads", [])
    with session() as s:
        titles = {r.job_id: r.title for r in s.execute(select(InboxJob).where(InboxJob.user_id == u.id)).scalars()}
    return [{**t, "title": titles.get(t.get("job_id"), t.get("job_id"))} for t in out]


@router.get("/messages/threads/{thread_id}")
async def thread(thread_id: str, u: User = Depends(current_user)) -> dict:
    data = await _read(u, "list_messages", {"thread_id": thread_id})
    return data.get("data", data)


@router.post("/messages/threads/{thread_id}/suggest", response_model=RunOut)
async def suggest(thread_id: str, u: User = Depends(current_user)) -> RunOut:
    t = (await thread(thread_id, u)).get("thread", {})
    job, proposal = {}, {}
    with session() as s:
        row = s.execute(select(InboxJob).where(InboxJob.user_id == u.id, InboxJob.job_id == t.get("job_id"))).scalar_one_or_none()
        if row:
            job = {"job_id": row.job_id, "title": row.title, "category": row.category}
            proposal = {"bid": row.price, "pay_type": ((row.job or {}).get("budget") or {}).get("type", "fixed")}
    return RunOut(run_id=services.start_conversation(u, thread_id, job, proposal))


@router.get("/pipeline")
async def pipeline(u: User = Depends(current_user)) -> dict:
    """Kanban columns from marketplace proposal statuses + events (viewed)."""
    props = (await _read(u, "list_proposals", {})).get("data", {}).get("proposals", [])
    events = (await _read(u, "list_events", {"after": 0})).get("data", {}).get("events", [])
    viewed = {e["ref"] for e in events if e["type"] == "proposal.viewed"}
    with session() as s:
        titles = {r.job_id: r.title for r in s.execute(select(InboxJob).where(InboxJob.user_id == u.id)).scalars()}
    cols = {c: [] for c in ("drafted", "submitted", "viewed", "replied", "interview", "hired", "lost")}
    for p in props:
        st = p["status"]
        if st == "submitted" and p["id"] in viewed:
            st = "viewed"
        cols.setdefault(st, []).append({"proposal_id": p["id"], "job_id": p["job_id"], "title": titles.get(p["job_id"], p["job_id"]),
                                        "bid": p["bid"], "connects": p["connects_spent"]})
    return {"columns": cols}
