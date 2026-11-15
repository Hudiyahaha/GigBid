"""Approvals: pending interrupts survive refreshes (stored in the DB and the graph checkpoint)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from agent import llm
from agent.nodes.writer import strip_citations
from apps.api import services
from apps.api.db import Approval, User, session
from apps.api.schemas import DecisionIn, RegenerateIn, RunOut
from apps.api.security import current_user

router = APIRouter(tags=["approvals"])


def _get(u: User, approval_id: int) -> Approval:
    with session() as s:
        a = s.get(Approval, approval_id)
    if not a or a.user_id != u.id:
        raise HTTPException(404, "approval not found")
    return a


@router.get("/approvals")
def pending(kind: str | None = None, u: User = Depends(current_user)) -> list[dict]:
    with session() as s:
        rows = s.execute(select(Approval).where(Approval.user_id == u.id, Approval.status == "pending")).scalars().all()
    return [{"id": a.id, "kind": a.kind, "ref": a.ref, "thread_id": a.thread_id, "created": a.created,
             "title": a.payload.get("title"), "can_approve": a.payload.get("can_approve")}
            for a in rows if not kind or a.kind == kind]


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: int, u: User = Depends(current_user)) -> dict:
    a = _get(u, approval_id)
    return {"id": a.id, "kind": a.kind, "ref": a.ref, "status": a.status, "thread_id": a.thread_id, "payload": a.payload,
            "decision": a.decision}


@router.get("/approvals/by-job/{job_id}")
def by_job(job_id: str, u: User = Depends(current_user)) -> dict:
    with session() as s:
        a = s.execute(select(Approval).where(Approval.user_id == u.id, Approval.ref == job_id, Approval.status == "pending")
                      .order_by(Approval.id.desc())).scalars().first()
    if not a:
        raise HTTPException(404, "no pending approval for this job")
    return get_approval(a.id, u)


@router.post("/approvals/{approval_id}/decide", response_model=RunOut)
async def decide(approval_id: int, d: DecisionIn, u: User = Depends(current_user)) -> RunOut:
    a = _get(u, approval_id)
    if a.status != "pending":
        raise HTTPException(409, f"already {a.status}")
    if d.action == "reject" and not d.reason:
        raise HTTPException(422, "a reason is required to reject")
    if d.action == "edit" and not d.edited_text:
        raise HTTPException(422, "edited_text is required")
    try:
        return RunOut(run_id=services.decide(u, a, d.model_dump()))
    except PermissionError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/proposals/regenerate-paragraph")
async def regenerate(r: RegenerateIn, u: User = Depends(current_user)) -> dict:
    text, meta = await llm.call_text("writer", "rewrite_paragraph", {"paragraph": strip_citations(r.paragraph),
                                                                      "instruction": r.instruction},
                                     heuristic=lambda: r.paragraph, max_tokens=400)
    return {"text": text.strip(), "model": meta.get("model")}
