"""Orchestration shared by the API and the worker: start/resume graph runs, record streamed events, keep the
inbox, approvals and outcomes in sync. Every run id IS the trace id (one id from UI -> API -> graph -> MCP -> audit)."""

from __future__ import annotations

import asyncio
import time
import uuid

from sqlalchemy import select

from agent import approval_token, mcp_client, runner
from agent.memory import promotion_rules
from agent.nodes.scout import fingerprint, run_saved_search
from apps.api.db import Approval, InboxJob, Outcome, Run, SavedSearch, User, UserSettings, session

GRAPHS: runner.Graphs | None = None
TASKS: set[asyncio.Task] = set()


def prefs_for(user: User) -> dict:
    with session() as s:
        st = s.get(UserSettings, user.id) or UserSettings(user_id=user.id)
    base = runner.default_prefs(user.persona or "ai_ml")
    base.update({"hourly_floor": st.hourly_floor, "min_project": st.min_project, "weekly_connects_budget": st.weekly_connects_budget,
                 "autonomy": st.autonomy, "strategy": st.strategy, "connects_spent_week": connects_spent_week(user.id)})
    return base


def connects_spent_week(user_id: str) -> int:
    with session() as s:
        rows = s.execute(select(Outcome).where(Outcome.user_id == user_id, Outcome.stage == "submitted",
                                               Outcome.created > time.time() - 7 * 86400)).scalars().all()
    return sum(r.connects for r in rows)


def new_run(user_id: str, graph: str, thread_id: str, ref: str) -> str:
    rid = uuid.uuid4().hex
    with session() as s:
        s.add(Run(id=rid, user_id=user_id, graph=graph, thread_id=thread_id, ref=ref, status="running", events=[]))
    return rid


def emit_factory(run_id: str):
    async def emit(ev: dict) -> None:
        with session() as s:
            r = s.get(Run, run_id)
            if r:
                r.events = list(r.events or []) + [{**ev, "ts": time.time()}]
    return emit


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)


def _finish(run_id: str, out: dict | None, error: str | None = None) -> None:
    with session() as s:
        r = s.get(Run, run_id)
        if not r:
            return
        r.finished = time.time()
        r.latency_s = round(r.finished - r.started, 3)
        if out:
            vals = out["values"]
            r.status = "awaiting_approval" if out.get("interrupt") else (vals.get("status") or "done")
            u = vals.get("usage") or {}
            r.tokens, r.usd = int(u.get("tokens", 0)), float(u.get("usd", 0.0))
            r.usage = {"by_node": u.get("by_node", {}), "llm": out.get("usage")}
        else:
            r.status, r.usage = "error", {"error": error}


def _sync_inbox(user_id: str, job_id: str, out: dict) -> None:
    v = out["values"]
    with session() as s:
        row = s.execute(select(InboxJob).where(InboxJob.user_id == user_id, InboxJob.job_id == job_id)).scalar_one_or_none()
        job = v.get("job") or {}
        if not row:
            row = InboxJob(user_id=user_id, job_id=job_id, fingerprint=fingerprint(job) if job else job_id,
                           title=job.get("title", job_id), job=job)
            s.add(row)
        row.thread_id = v.get("thread_id", "")
        row.status = "awaiting_approval" if out.get("interrupt") else (v.get("status") or row.status)
        row.fit = float((v.get("fit") or {}).get("score", row.fit or 0))
        row.risk = float((v.get("risk") or {}).get("score", row.risk or 0))
        row.action = (v.get("decision") or {}).get("action", row.action or "")
        row.price = float((v.get("price") or {}).get("amount", row.price or 0) or 0)
        row.connects_cost = int((v.get("price") or {}).get("connects_cost", job.get("connects_cost", 0)) or 0)
        row.category = job.get("category", row.category or "")
        row.summary = {"reasons": (v.get("decision") or {}).get("reasons", []), "risk_flags": [f["code"] for f in (v.get("risk") or {}).get("flags", [])],
                       "scam": (v.get("risk") or {}).get("scam", False), "attention": v.get("attention_reason")}
        row.updated = time.time()
        if v.get("submission") and v.get("status") == "submitted":
            sub = v["submission"]
            exists = s.execute(select(Outcome).where(Outcome.user_id == user_id, Outcome.proposal_id == sub["proposal_id"],
                                                     Outcome.stage == "submitted")).scalar_one_or_none()
            if not exists:
                s.add(Outcome(user_id=user_id, proposal_id=sub["proposal_id"], job_id=job_id, category=row.category,
                              stage="submitted", strategy=(v.get("draft") or {}).get("strategy", ""),
                              connects=int(sub.get("connects_spent", 0) or 0)))


def _sync_approval(user_id: str, kind: str, out: dict, ref: str) -> None:
    with session() as s:
        row = s.execute(select(Approval).where(Approval.user_id == user_id, Approval.thread_id == out["thread_id"],
                                               Approval.status == "pending")).scalar_one_or_none()
        if out.get("interrupt"):
            if row:
                row.payload = out["interrupt"]
            else:
                s.add(Approval(user_id=user_id, thread_id=out["thread_id"], kind=kind, ref=ref, payload=out["interrupt"]))


async def _run(run_id: str, user: User, kind: str, ref: str, coro_factory) -> None:
    try:
        out = await coro_factory(emit_factory(run_id))
    except Exception as e:  # noqa: BLE001 - recorded on the run, shown in the UI
        _finish(run_id, None, f"{type(e).__name__}: {e}")
        return
    _finish(run_id, out)
    if kind == "bid":
        _sync_inbox(user.id, ref, out)
    _sync_approval(user.id, "proposal" if kind == "bid" else "message", out, ref)


def start_bid(user: User, job_id: str, job: dict | None = None) -> str:
    thread = f"{user.id}:bid:{job_id}"
    rid = new_run(user.id, "bid", thread, job_id)

    async def go(emit):
        return await runner.start_bid(GRAPHS, job_id, user.id, user.persona, prefs_for(user), job=job, thread_id=thread,
                                      trace_id=rid, on_event=emit)
    _spawn(_run(rid, user, "bid", job_id, go))
    return rid


def start_conversation(user: User, mthread: str, job: dict | None = None, proposal: dict | None = None) -> str:
    thread = f"{user.id}:conv:{mthread}:{uuid.uuid4().hex[:6]}"
    rid = new_run(user.id, "conversation", thread, mthread)

    async def go(emit):
        return await runner.start_conversation(GRAPHS, mthread, user.id, user.persona, job=job, proposal=proposal,
                                               prefs=prefs_for(user), thread_id=thread, trace_id=rid, on_event=emit)
    _spawn(_run(rid, user, "conversation", mthread, go))
    return rid


def decide(user: User, approval: Approval, decision: dict) -> str:
    """Human decision from the UI. On approve, the API (not the agent) mints the approval token."""
    kind = "bid" if approval.kind == "proposal" else "conversation"
    payload = approval.payload.get("send_payload") or {}
    if decision["action"] == "approve":
        if not approval.payload.get("can_approve", True):
            raise PermissionError("blocked by compliance: edit the draft first")
        decision["approval_token"] = approval_token.mint(user.id, "proposal" if kind == "bid" else "message", payload)
    decision["user_id"] = user.id
    with session() as s:
        a = s.get(Approval, approval.id)
        a.status = {"approve": "approved", "edit": "edited", "reject": "rejected"}[decision["action"]]
        a.decision = {k: v for k, v in decision.items() if k != "approval_token"}
        a.decided = time.time()
    rid = new_run(user.id, kind, approval.thread_id, approval.ref)

    async def go(emit):
        return await runner.resume(GRAPHS, kind, approval.thread_id, decision, user.id, user.persona, trace_id=rid, on_event=emit)
    _spawn(_run(rid, user, kind, approval.ref, go))
    return rid


async def scout_user(user: User) -> dict:
    """Run the user's saved searches, dedupe, queue new jobs (Scout). Polite: one search per saved query."""
    mcp_client.RUN_CTX.set({"trace_id": uuid.uuid4().hex, "user_id": user.id, "persona": user.persona})
    with session() as s:
        searches = s.execute(select(SavedSearch).where(SavedSearch.user_id == user.id, SavedSearch.enabled.is_(True))).scalars().all()
        known_fp = {r.fingerprint for r in s.execute(select(InboxJob).where(InboxJob.user_id == user.id)).scalars()}
    new, dups = [], 0
    for ss in searches:
        jobs, tick = await run_saved_search(ss.query, since_tick=0, limit=30)
        with session() as s:
            row = s.get(SavedSearch, ss.id)
            row.last_run, row.last_tick = time.time(), tick or row.last_tick
            for j in jobs:
                fp = fingerprint(j)
                exists = s.execute(select(InboxJob).where(InboxJob.user_id == user.id, InboxJob.job_id == j["job_id"])).scalar_one_or_none()
                if exists:
                    continue
                if fp in known_fp:
                    dups += 1
                    s.add(InboxJob(user_id=user.id, job_id=j["job_id"], fingerprint=fp, title=j["title"], job=j,
                                   status="duplicate", category=j.get("category", "")))
                    continue
                known_fp.add(fp)
                s.add(InboxJob(user_id=user.id, job_id=j["job_id"], fingerprint=fp, title=j["title"], job=j, status="queued",
                               category=j.get("category", ""), connects_cost=j.get("connects_cost", 0)))
                new.append(j["job_id"])
    return {"queued": new, "duplicates": dups}


async def sync_events(user: User) -> int:
    """Pull marketplace events -> pipeline statuses + outcomes, then run the outcome promotion rule."""
    mcp_client.RUN_CTX.set({"trace_id": uuid.uuid4().hex, "user_id": user.id, "persona": user.persona})
    out = await mcp_client.call("api_reader", "list_events", {"after": 0})
    n = 0
    with session() as s:
        for ev in out.get("events", []):
            stage = ev["type"].split(".", 1)[1]
            if stage not in ("viewed", "replied", "interview", "hired", "lost"):
                continue
            sub = s.execute(select(Outcome).where(Outcome.user_id == user.id, Outcome.proposal_id == ev["ref"],
                                                  Outcome.stage == "submitted")).scalar_one_or_none()
            if not sub:
                continue
            exists = s.execute(select(Outcome).where(Outcome.user_id == user.id, Outcome.proposal_id == ev["ref"],
                                                     Outcome.stage == stage)).scalar_one_or_none()
            if not exists:
                s.add(Outcome(user_id=user.id, proposal_id=ev["ref"], job_id=sub.job_id, category=sub.category, stage=stage,
                              strategy=sub.strategy))
                n += 1
    if n:
        await promotion_rules.promote_outcomes(user.id)
    return n
