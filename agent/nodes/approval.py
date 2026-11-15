"""Human approval (C5) and the executor. Nothing reaches a client without passing human_approval.

preview         - builds the exact client-facing payload and asks the marketplace for a dry_run (cost, balance after)
human_approval  - interrupt(): the UI shows draft + evidence per claim + risk + price + dry_run; the human approves,
                  edits (diffed -> style memory candidates, re-checked by Compliance) or rejects with a reason
execute_*       - the only nodes that perform writes, with idempotency keys derived from (thread, payload), so a
                  crash/retry/replay submits exactly once. The approval token is minted by the API on approval.
"""

from __future__ import annotations

import time

from langgraph.types import interrupt

from agent import approval_token
from agent.marketplace_port import MarketplacePort
from agent.memory import promotion_rules
from agent.nodes.base import node
from agent.nodes.writer import strip_citations


def send_payload(state: dict) -> dict:
    d, p = state["draft"], state.get("price") or {}
    return {"job_id": state["job"]["job_id"], "cover_letter": strip_citations(d["cover_letter"]),
            "screening_answers": [strip_citations(a.get("answer", "")) for a in d.get("screening_answers", [])],
            "bid_amount": float(p.get("amount") or 0), "pay_type": p.get("pay_type", "fixed")}


@node("preview")
async def preview(state: dict) -> dict:
    payload = send_payload(state)
    res = await MarketplacePort("approval_executor").create_proposal_draft(
        payload, f"{state['thread_id']}:dry", dry_run=True)
    return {"dry_run": {"payload": payload, "preview": res.get("preview")}}


def approval_request(state: dict) -> dict:
    job = state["job"]
    return {
        "kind": "proposal", "thread_id": state["thread_id"], "job_id": job["job_id"], "title": job.get("title"),
        "send_payload": state["dry_run"]["payload"], "preview": state["dry_run"].get("preview"),
        "draft": state["draft"], "claims": state["draft"].get("claims", []), "evidence": (state.get("evidence") or [])[:10],
        "fit": state.get("fit"), "risk": state.get("risk"), "price": state.get("price"), "decision": state.get("decision"),
        "compliance": state.get("compliance"), "critiques": state.get("critiques"),
        "verification": (state.get("verification") or {}).get("last"),
        "can_approve": bool((state.get("compliance") or {}).get("allowed", False)),
    }


@node("human_approval")
async def human_approval(state: dict) -> dict:
    decision = interrupt(approval_request(state))
    action = (decision or {}).get("action")
    rec = {**(decision or {}), "decided_at": time.time()}
    if action == "approve":
        if not (state.get("compliance") or {}).get("allowed"):
            return {"approval": {**rec, "error": "blocked by compliance"}, "status": "blocked"}
        return {"approval": rec, "status": "approved"}
    if action == "edit":
        before = state["dry_run"]["payload"]["cover_letter"]
        after = (decision.get("edited_text") or before).strip()
        promotion_rules.record_edit(state.get("user_id", "local"), state["job"]["job_id"], before, after)
        await promotion_rules.promote_style(state.get("user_id", "local"))
        draft = dict(state["draft"])
        draft["cover_letter"] = after
        draft["edited_by_user"] = True
        if decision.get("edited_answers"):
            draft["screening_answers"] = [{**a, "answer": t} for a, t in zip(draft.get("screening_answers", []),
                                                                            decision["edited_answers"], strict=False)]
        return {"draft": draft, "approval": rec, "status": "analysing"}
    return {"approval": {**rec, "action": "reject"}, "status": "rejected"}


def route_after_approval(state: dict) -> str:
    a = (state.get("approval") or {}).get("action")
    if state.get("status") == "approved":
        return "execute"
    if a == "edit":
        return "compliance"
    if state.get("status") == "blocked" and a == "approve":
        return "human_approval"
    return "end"


@node("executor")
async def execute_proposal(state: dict) -> dict:
    token = (state.get("approval") or {}).get("approval_token")
    payload = state["dry_run"]["payload"]
    h = approval_token.payload_hash(payload)[:12]
    draft_key, submit_key = f"{state['thread_id']}:draft:{h}", f"{state['thread_id']}:submit:{h}"
    port = MarketplacePort("approval_executor")
    d = await port.create_proposal_draft(payload, draft_key, approval_token=token)
    pid = d["result"]["proposal_id"]
    s = await port.submit_proposal(pid, draft_key, submit_key, approval_token=token)
    return {"submission": {"proposal_id": pid, "draft_key": draft_key, "submit_key": submit_key, **(s.get("result") or {}),
                           "idempotent_replay": bool(s.get("idempotent_replay"))},
            "status": "submitted"}
