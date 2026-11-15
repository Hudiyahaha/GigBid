"""Risk Assessor (Marketplace read: get_client_history).

score = max(rule_score, 0.6 * llm_score + 0.4 * client_risk)
  rule_score  - max severity of config-driven scam signals (data/policy_pack/rules.yaml: scam_signals)
  client_risk - 1 - client_quality (payment verified, hires, hire rate, rating, spend)
  llm_score   - small model's judgement; SKIPPED when rules already show a clear scam (cost optimisation)
Prompt-injection text is flagged but does not by itself make a job a scam.
"""

from __future__ import annotations

import math
import re

from agent import config, llm, policy
from agent.guardrails import delimit
from agent.handoffs import RiskFlag, RiskReport
from agent.marketplace_port import MarketplacePort
from agent.nodes.base import node


def rule_flags(text: str) -> list[RiskFlag]:
    flags = []
    for sig in policy.rules().get("scam_signals", []):
        m = re.search(sig["regex"], text or "")
        if m:
            s = max(0, m.start() - 40)
            flags.append(RiskFlag(code=sig["code"], severity=float(sig["severity"]), evidence=text[s:m.end() + 40].strip()))
    return flags


def client_quality(c: dict) -> tuple[float, list[RiskFlag]]:
    flags = []
    q = 0.5
    if c.get("payment_verified"):
        q += 0.2
    else:
        flags.append(RiskFlag(code="unverified_payment", severity=0.4, evidence="payment method not verified"))
    hires = c.get("hires", 0) or 0
    if hires == 0:
        q -= 0.15
        flags.append(RiskFlag(code="no_hire_history", severity=0.3, evidence=f"{c.get('jobs_posted', 0)} jobs posted, 0 hires"))
    else:
        q += min(0.15, 0.03 * math.log1p(hires))
    rating = c.get("avg_rating_given")
    if rating is not None and rating < 3.5:
        q -= 0.2
        flags.append(RiskFlag(code="low_rating", severity=0.4, evidence=f"average rating given {rating}"))
    if (c.get("total_spent_usd") or 0) > 1000:
        q += 0.1
    return max(0.0, min(1.0, q)), flags


@node("risk_assessor")
async def risk_assessor(state: dict) -> dict:
    job = state["job"]
    raw = job.get("description", "")
    flags = rule_flags(raw)
    rule_score = max((f.severity for f in flags), default=0.0)
    inj = job.get("injection_signals") or []
    if inj:
        flags.append(RiskFlag(code="prompt_injection", severity=0.3, evidence="; ".join(inj)[:200]))
    client = {}
    if job.get("client_id"):
        client = await MarketplacePort("risk_assessor").get_client_history(job["client_id"])
    cq, cflags = client_quality(client) if client else (0.5, [])
    flags += cflags
    b = job.get("budget") or {}
    if b.get("type") == "fixed" and (b.get("max") or 0) <= 0:
        flags.append(RiskFlag(code="unrealistic_budget", severity=0.6, evidence="budget of $0"))
        rule_score = max(rule_score, 0.6)
    client_risk = 1 - cq
    trace = []
    scam_thr = float(config.get("decision.scam_risk", 0.75))
    if rule_score >= 0.9:  # clear-cut: skip the LLM call entirely
        llm_score, explanation = rule_score, "Rule-based scam signals: " + ", ".join(f.code for f in flags if f.severity >= 0.8)
    else:
        def heuristic() -> dict:
            return {"scam": rule_score >= scam_thr, "score": rule_score, "flags": [], "explanation": "heuristic (rules + client history)"}
        safe_client = {k: client.get(k) for k in ("payment_verified", "jobs_posted", "hires", "hire_rate", "total_spent_usd",
                                                  "avg_rating_given", "member_since", "country")}
        rep, meta = await llm.call_json("risk_assessor", "risk_assessor",
                                        {"client": safe_client, "rule_flags": [f.code for f in flags],
                                         "job": delimit("job_post", raw)}, RiskReport, heuristic=heuristic)
        trace.append({"type": "llm", "node": "risk_assessor", **meta})
        llm_score, explanation = rep.score, rep.explanation
        known = {f.code for f in flags}
        flags += [f for f in rep.flags if f.code not in known and f.code != "prompt_injection"]
    score = round(max(rule_score, 0.6 * llm_score + 0.4 * client_risk), 3)
    report = RiskReport(score=score, client_quality=round(cq, 3), scam=score >= scam_thr, flags=flags,
                        injection_detected=bool(inj), explanation=explanation)
    return {"risk": report.model_dump(), "trace": trace}
