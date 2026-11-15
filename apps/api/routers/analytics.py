from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from agent import config
from agent.memory import store as memory
from apps.api.db import Approval, Outcome, Run, SavedSearch, User, UserSettings, session
from apps.api.schemas import SettingsIn, Simple
from apps.api.security import current_user

router = APIRouter(tags=["analytics"])


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 3) if xs else 0.0


@router.get("/analytics")
def analytics(u: User = Depends(current_user)) -> dict:
    with session() as s:
        outs = s.execute(select(Outcome).where(Outcome.user_id == u.id)).scalars().all()
        runs = s.execute(select(Run).where(Run.user_id == u.id)).scalars().all()
        appr = s.execute(select(Approval).where(Approval.user_id == u.id)).scalars().all()
    by_cat: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    connects = 0
    for o in outs:
        by_cat[o.category or "other"][o.stage].add(o.proposal_id)
        connects += o.connects
    cats = []
    for c, st in by_cat.items():
        n = len(st["submitted"]) or 1
        cats.append({"category": c, "submitted": len(st["submitted"]),
                     "reply_rate": round(len(st["replied"] | st["interview"] | st["hired"]) / n, 3),
                     "hire_rate": round(len(st["hired"]) / n, 3)})
    hires = sum(len(st["hired"]) for st in by_cat.values())
    replies = sum(len(st["replied"] | st["interview"] | st["hired"]) for st in by_cat.values())
    bid_runs = [r for r in runs if r.graph == "bid" and r.status not in ("running", "error")]
    prop_runs = [r for r in bid_runs if r.status in ("awaiting_approval", "submitted")]
    reasons = Counter((a.decision or {}).get("reason", "").strip().lower() for a in appr if a.status == "rejected")
    return {"by_category": cats, "connects_spent": connects, "replies": replies, "hires": hires,
            "connects_per_reply": round(connects / replies, 1) if replies else None,
            "latency": {"job_p50_s": _pct([r.latency_s for r in bid_runs], 0.5), "job_p95_s": _pct([r.latency_s for r in bid_runs], 0.95),
                        "proposal_p95_s": _pct([r.latency_s for r in prop_runs], 0.95)},
            "cost": {"usd_per_job": round(sum(r.usd for r in bid_runs) / len(bid_runs), 6) if bid_runs else 0,
                     "usd_per_proposal": round(sum(r.usd for r in prop_runs) / len(prop_runs), 6) if prop_runs else 0},
            "budgets": config.get("budgets.declared"),
            "top_rejection_reasons": [{"reason": r, "count": n} for r, n in reasons.most_common(5) if r]}


@router.get("/settings")
def get_settings(u: User = Depends(current_user)) -> dict:
    from apps.api.auth import token_store
    with session() as s:
        st = s.get(UserSettings, u.id) or UserSettings(user_id=u.id)
        searches = [{"id": x.id, "query": x.query, "interval_minutes": x.interval_minutes, "enabled": x.enabled}
                    for x in s.execute(select(SavedSearch).where(SavedSearch.user_id == u.id)).scalars()]
    return {"hourly_floor": st.hourly_floor, "min_project": st.min_project, "weekly_connects_budget": st.weekly_connects_budget,
            "autonomy": st.autonomy, "strategy": st.strategy, "marketplace_mode": st.marketplace_mode,
            "saved_searches": searches, "connected_accounts": token_store.connected(u.id), "persona": u.persona}


@router.put("/settings", response_model=Simple)
def put_settings(p: SettingsIn, u: User = Depends(current_user)) -> Simple:
    with session() as s:
        st = s.get(UserSettings, u.id) or UserSettings(user_id=u.id)
        for k in ("hourly_floor", "min_project", "weekly_connects_budget", "autonomy", "strategy"):
            if getattr(p, k) is not None:
                setattr(st, k, getattr(p, k))
        s.merge(st)
        if p.saved_searches is not None:
            for x in s.execute(select(SavedSearch).where(SavedSearch.user_id == u.id)).scalars():
                s.delete(x)
            for q in p.saved_searches[:10]:
                s.add(SavedSearch(user_id=u.id, query=q[:200]))
    return Simple()


@router.get("/memory")
async def get_memory(u: User = Depends(current_user)) -> dict:
    return await memory.list_all(u.id)


@router.delete("/memory/{namespace}/{key:path}", response_model=Simple)
async def delete_memory(namespace: str, key: str, u: User = Depends(current_user)) -> Simple:
    if namespace not in ("style", "outcome"):
        return Simple(ok=False, detail="unknown namespace")
    await memory.delete(u.id, namespace, key)
    return Simple()
