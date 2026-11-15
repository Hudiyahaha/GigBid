"""Pricing Strategist (Marketplace read: get_market_stats, get_connects_balance).

amount = market p50 for the category (real Kaggle + GigSim history), nudged by fit, kept inside the client's
budget when possible and never below the user's floor. Connects are worth it when
expected value >= decision.min_expected_value_ratio x Connects cost in USD, and the balance + weekly budget allow it.
The Connects cost includes any policy surcharge (e.g. unverified clients) from the live policy - no hard-coding.
"""

from __future__ import annotations

from agent import config
from agent.handoffs import PriceQuote
from agent.marketplace_port import MarketplacePort
from agent.nodes.base import node


def win_probability(amount: float, stats: dict, fit: float, risk: float) -> float:
    table = config.get("pricing.win_prob_by_price_quantile", {}) or {}
    base = table.get("p90", 0.08)
    for q in ("p25", "p50", "p75", "p90"):
        if stats.get(q) and amount <= stats[q]:
            base = table.get(q, base)
            break
    return round(min(0.9, base * (0.5 + fit) * (1 - 0.5 * risk)), 4)


@node("pricing")
async def pricing(state: dict) -> dict:
    job, prefs = state["job"], state.get("prefs") or {}
    fit = float((state.get("fit") or {}).get("score", 0))
    risk = state.get("risk") or {}
    port = MarketplacePort("pricing")
    b = job.get("budget") or {}
    pay = b.get("type", "fixed") if b.get("type") in ("fixed", "hourly") else "fixed"
    stats = await port.get_market_stats(category=job.get("category"), pay_type=pay)
    if (stats.get("n") or 0) < 10:
        stats = await port.get_market_stats(pay_type=pay)
    bal = (await port.get_connects_balance()).get("connects_balance")
    pol = state.get("policy") or {}
    floor = float(prefs.get("hourly_floor", 40)) if pay == "hourly" else float(prefs.get("min_project", 300))
    base = float(stats.get("p50") or b.get("max") or floor)
    amount = base * (1 + 0.3 * (fit - 0.6))
    rationale = [f"market median ${base:.0f} ({stats.get('n', 0)} comparable {pay} jobs)", f"fit {fit:.2f} adjusts by {30 * (fit - 0.6):+.0f}%"]
    if b.get("max"):
        if amount > b["max"]:
            rationale.append(f"capped at the client's budget ${b['max']:.0f}")
        amount = min(amount, float(b["max"]))
    if amount < floor:
        rationale.append(f"raised to your floor ${floor:.0f}")
        amount = floor
    amount = round(amount, 0 if pay == "hourly" else -1) or floor
    cost = int(job.get("connects_cost", 0))
    surcharge = int((pol.get("connects") or {}).get("surcharge_unverified_client", 0) or 0)
    if surcharge and any(f["code"] == "unverified_payment" for f in risk.get("flags", [])):
        cost += surcharge
        rationale.append(f"+{surcharge} Connects surcharge: client payment unverified (policy v{pol.get('marketplace_version')})")
    usd_per = float(config.get("decision.connects_value_per_unit_usd", 0.15))
    win = win_probability(amount, stats, fit, float(risk.get("score", 0)))
    hours = float(config.get("pricing.est_hours_hourly", 40))
    ev = win * amount * (hours if pay == "hourly" else 1)
    ratio = float(config.get("decision.min_expected_value_ratio", 3.0))
    weekly_left = int(prefs.get("weekly_connects_budget", 80)) - int(prefs.get("connects_spent_week", 0))
    worth = ev >= ratio * cost * usd_per and (bal is None or bal >= cost) and weekly_left >= cost
    if bal is not None and bal < cost:
        rationale.append(f"not enough Connects ({bal} < {cost})")
    if weekly_left < cost:
        rationale.append(f"weekly Connects budget left {weekly_left} < {cost}")
    rationale.append(f"win probability {win:.0%}, expected value ${ev:.0f} vs Connects cost ${cost * usd_per:.2f}")
    q = PriceQuote(amount=amount, pay_type=pay, market={k: stats.get(k) for k in ("n", "p25", "p50", "p75", "p90")},
                   floor=floor, connects_cost=cost, connects_usd=round(cost * usd_per, 2), win_probability=win,
                   expected_value_usd=round(ev, 2), worth_it=worth, rationale="; ".join(rationale))
    out = {"price": q.model_dump()}
    if not worth:
        out["status"] = "skipped"
        out["decision"] = {**(state.get("decision") or {}), "action": "skip",
                           "reasons": list((state.get("decision") or {}).get("reasons", [])) + ["Connects not worth spending: " + rationale[-1]]}
    return out
