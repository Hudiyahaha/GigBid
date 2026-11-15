from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from agent import runner
from apps.api import services
from apps.api.db import InboxJob, User, session
from apps.api.schemas import RunOut, Simple, UploadIn
from apps.api.security import current_user

router = APIRouter(tags=["jobs"])
ROOT = Path(__file__).resolve().parents[3]


def job_row(r: InboxJob) -> dict:
    b = (r.job or {}).get("budget") or {}
    return {"job_id": r.job_id, "title": r.title, "status": r.status, "fit": round(r.fit, 3), "risk": round(r.risk, 3),
            "action": r.action, "price": r.price, "connects_cost": r.connects_cost or (r.job or {}).get("connects_cost", 0),
            "category": r.category, "budget": b, "summary": r.summary, "thread_id": r.thread_id,
            "duplicate_of": r.duplicate_of, "updated": r.updated, "source": (r.job or {}).get("source")}


@router.get("/jobs")
def inbox(status: str | None = None, q: str | None = None, min_fit: float = 0.0, u: User = Depends(current_user)) -> list[dict]:
    with session() as s:
        rows = s.execute(select(InboxJob).where(InboxJob.user_id == u.id)).scalars().all()
    out = [job_row(r) for r in rows if (not status or r.status == status) and r.fit >= min_fit
           and (not q or q.lower() in r.title.lower())]
    order = {"awaiting_approval": 0, "queued": 1, "watch": 2}
    return sorted(out, key=lambda j: (order.get(j["status"], 3), -j["fit"]))


@router.post("/jobs/scout")
async def scout_now(u: User = Depends(current_user)) -> dict:
    res = await services.scout_user(u)
    first = res["queued"][:3]  # polite + CPU-friendly; the worker analyses the rest on its schedule
    with session() as s:
        for r in s.execute(select(InboxJob).where(InboxJob.user_id == u.id, InboxJob.job_id.in_(first))).scalars():
            r.status = "analysing"
    started = [services.start_bid(u, jid) for jid in first]
    return {**res, "analysing": len(started)}


@router.post("/jobs/{job_id}/analyze", response_model=RunOut)
async def analyze(job_id: str, u: User = Depends(current_user)) -> RunOut:
    with session() as s:
        row = s.execute(select(InboxJob).where(InboxJob.user_id == u.id, InboxJob.job_id == job_id)).scalar_one_or_none()
        if row:
            row.status = "analysing"
    return RunOut(run_id=services.start_bid(u, job_id))


@router.post("/jobs/{job_id}/skip", response_model=Simple)
def skip(job_id: str, u: User = Depends(current_user)) -> Simple:
    with session() as s:
        row = s.execute(select(InboxJob).where(InboxJob.user_id == u.id, InboxJob.job_id == job_id)).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "job not in inbox")
        row.status, row.action, row.updated = "skipped", "skip", time.time()
        row.summary = {**(row.summary or {}), "reasons": ["skipped by you"]}
    return Simple()


@router.get("/jobs/{job_id}")
async def job_detail(job_id: str, u: User = Depends(current_user)) -> dict:
    with session() as s:
        row = s.execute(select(InboxJob).where(InboxJob.user_id == u.id, InboxJob.job_id == job_id)).scalar_one_or_none()
    thread = f"{u.id}:bid:{job_id}"
    snap = await services.GRAPHS.bid.aget_state(runner.cfg(thread))
    v = snap.values or {}
    return {"inbox": job_row(row) if row else None, "job": v.get("job") or (row.job if row else None),
            "job_spec": v.get("job_spec"), "risk": v.get("risk"), "fit": v.get("fit"), "price": v.get("price"),
            "decision": v.get("decision"), "status": v.get("status"), "thread_id": thread, "draft": v.get("draft"),
            "critiques": v.get("critiques"), "verification": (v.get("verification") or {}).get("last"),
            "attention_reason": v.get("attention_reason"), "submission": v.get("submission")}


@router.post("/portfolio/upload", response_model=Simple)
def upload(item: UploadIn, u: User = Depends(current_user)) -> Simple:
    """Add work in the UI -> incremental re-index of this persona's portfolio."""
    from rag.retriever import reindex
    slug = re.sub(r"[^a-z0-9]+", "-", item.title.lower()).strip("-")[:40]
    iid = f"up-{u.id[-6:]}-{slug}"
    d = ROOT / "data" / "processed" / "uploads" / u.persona
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{iid}.md").write_text(f"---\nid: {iid}\ntype: {item.kind}\ntitle: {item.title}\nproject: {iid}\n"
                                 f"date: {time.strftime('%Y-%m-%d')}\n---\n# {item.title}\n\n{item.text}\n", encoding="utf-8")
    reindex(u.persona)
    return Simple(detail={"item_id": iid})
