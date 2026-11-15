"""Bid / watch / skip decision (deterministic, every reason shown in the UI). Thresholds come from config."""

from __future__ import annotations

from agent import config
from agent.handoffs import BidDecision
from agent.nodes.base import halted, node


def budget_ok(job: dict, prefs: dict) -> tuple[bool, str]:
    b = job.get("budget") or {}
    tol = float(config.get("decision.budget_tolerance", 0.8))
    mx = float(b.get("max") or 0)
    if b.get("type") == "hourly":
        floor = float(prefs.get("hourly_floor", config.get("pricing.hourly_floor_usd", 40)))
        return (mx >= floor * tol or mx == 0), f"hourly budget up to ${mx:.0f} vs your floor ${floor:.0f}/h"
    floor = float(prefs.get("min_project", 300))
    return (mx >= floor * tol), f"fixed budget ${mx:.0f} vs your minimum project ${floor:.0f}"


@node("decision")
async def decide(state: dict) -> dict:
    if halted(state):
        return {}
    fit = state.get("fit") or {}
    risk = state.get("risk") or {}
    prefs = state.get("prefs") or {}
    f, r = float(fit.get("score", 0)), float(risk.get("score", 0))
    t = {k: float(config.get(f"decision.{k}")) for k in ("min_fit_to_bid", "min_fit_to_watch", "max_risk_to_bid", "scam_risk")}
    reasons: list[str] = []
    ok_budget, budget_msg = budget_ok(state["job"], prefs)
    if risk.get("scam") or r >= t["scam_risk"]:
        action = "skip"
        reasons.append("likely scam: " + ", ".join(fl["code"] for fl in risk.get("flags", []) if fl["severity"] >= 0.5))
    elif not ok_budget:
        action = "skip"
        reasons.append("budget below your floor: " + budget_msg)
    elif f >= t["min_fit_to_bid"] and r <= t["max_risk_to_bid"]:
        action = "bid"
        reasons.append(f"fit {f:.2f} >= {t['min_fit_to_bid']}, risk {r:.2f} <= {t['max_risk_to_bid']}")
    elif f >= t["min_fit_to_watch"]:
        action = "watch"
        reasons.append(f"borderline: fit {f:.2f}" + (f", risk {r:.2f} above {t['max_risk_to_bid']}" if r > t["max_risk_to_bid"] else ""))
    else:
        action = "skip"
        reasons.append(f"low fit {f:.2f}: " + "; ".join(fit.get("missing_skills", [])[:3]))
    auto = action == "skip" and prefs.get("autonomy") == "auto_skip_low_fit" and f < t["min_fit_to_watch"]
    d = BidDecision(action=action, reasons=reasons, fit_score=f, risk_score=r, auto=auto)
    out = {"decision": d.model_dump()}
    if action != "bid":
        out["status"] = "skipped" if action == "skip" else "watch"
    return out
