"""Fit Matcher (Portfolio read): map every requirement to portfolio evidence and score the fit.

Runs in parallel with the Job Analyst, so it derives requirements itself from the sanitised post
(sentence decomposition + skill lexicon). Strength per requirement:
  strong  - an evidence item explicitly shows the named skill, or relevance >= fit.strong_relevance
  partial - relevance >= fit.partial_relevance
  none    - otherwise
An optional LLM grader re-checks the matrix (fit.use_llm_grader). Fit = weighted share (must=1, nice=0.5).
"""

from __future__ import annotations

import asyncio

from agent import config, llm, mcp_client
from agent.handoffs import EvidenceItem, FitReport, RequirementMatch
from agent.nodes.base import node
from rag.ingest.skills import detect_skills
from rag.query import decompose

WEIGHT = {"strong": 1.0, "partial": 0.5, "none": 0.0}


def requirements_from_post(job: dict) -> list[dict]:
    text = job.get("clean_description") or job.get("description", "")
    out = []
    for sent in decompose(text):
        out.append({"text": sent, "skills": detect_skills(sent), "must": "bonus" not in sent.lower()})
    return out[:8]


def grade(req: dict, items: list[dict]) -> RequirementMatch:
    strong_t = float(config.get("fit.strong_relevance", 0.5))
    partial_t = float(config.get("fit.partial_relevance", 0.1))
    best = items[:3]
    named = [s for s in req["skills"] if s != "Python"] or req["skills"]
    if named:
        proving = [it["item_id"] for it in best if set(named) & set(it.get("skills", []))]
        if proving:
            return RequirementMatch(requirement=req["text"], strength="strong", evidence_ids=proving,
                                    reason=f"evidence names {', '.join(named)}")
    rel = max((it.get("relevance") or 0 for it in best), default=0)
    ids = [it["item_id"] for it in best if (it.get("relevance") or 0) >= partial_t]
    if rel >= strong_t and not named:
        return RequirementMatch(requirement=req["text"], strength="strong", evidence_ids=ids, reason=f"relevance {rel:.2f}")
    if rel >= partial_t:
        return RequirementMatch(requirement=req["text"], strength="partial", evidence_ids=ids,
                                reason=f"related evidence (relevance {rel:.2f})" + (f"; {', '.join(named)} not shown" if named else ""))
    return RequirementMatch(requirement=req["text"], strength="none", reason="no supporting evidence")


@node("fit_matcher")
async def fit_matcher(state: dict) -> dict:
    job = state["job"]
    reqs = requirements_from_post(job)
    filters = {"job_title": job.get("title"), "industry": job.get("industry"), "types": ["case_study", "repo", "review", "cv"]}

    async def one(r):
        return await mcp_client.call("fit_matcher", "search_evidence", {"requirement": r["text"], "k": 3, "filters": filters})

    results = await asyncio.gather(*(one(r) for r in reqs)) if reqs else []
    pool: dict[str, dict] = {}
    matrix = []
    for r, res in zip(reqs, results, strict=True):
        items = res.get("items", [])
        for it in items:
            if it["item_id"] not in pool or (it.get("relevance") or 0) > (pool[it["item_id"]].get("relevance") or 0):
                pool[it["item_id"]] = it
        matrix.append(grade(r, items))
    trace = []
    if matrix and config.get("fit.use_llm_grader", True):
        view = [{"requirement": m.requirement, "candidates": [{"item_id": i, "title": pool[i]["title"], "snippet": pool[i]["snippet"][:240]}
                                                              for i in (m.evidence_ids or [it["item_id"] for it in res.get("items", [])[:2]]) if i in pool]}
                for m, res in zip(matrix, results, strict=True)]

        def heuristic():
            return {"matches": [m.model_dump() for m in matrix]}
        out, meta = await llm.call_json("fit_matcher", "fit_grader", {"matrix": view}, None, heuristic=heuristic)
        trace.append({"type": "llm", "node": "fit_matcher", **meta})
        if meta.get("model") != "heuristic":
            by_req = {m.get("requirement"): m for m in (out.get("matches") or []) if isinstance(m, dict)}
            for m in matrix:
                g = by_req.get(m.requirement)
                if g and g.get("strength") in WEIGHT:
                    # the LLM may downgrade or confirm, and upgrade only partial -> strong when it cites pool items
                    cited = [i for i in g.get("evidence_ids", []) if i in pool]
                    if g["strength"] != m.strength and (g["strength"] != "strong" or (m.strength == "partial" and cited)):
                        m.strength, m.reason = g["strength"], f"LLM: {g.get('reason', '')}"[:200]
                        m.evidence_ids = cited or m.evidence_ids
    weights = [1.0 if r["must"] else 0.5 for r in reqs]
    score = sum(w * WEIGHT[m.strength] for w, m in zip(weights, matrix, strict=True)) / max(1e-9, sum(weights)) if matrix else 0.0
    matched = sorted({s for r, m in zip(reqs, matrix, strict=True) if m.strength != "none" for s in r["skills"]})
    missing = [m.requirement for m in matrix if m.strength == "none"]
    evidence = sorted(pool.values(), key=lambda it: -(it.get("relevance") or 0))[:10]
    report = FitReport(score=round(score, 3), matched_skills=matched, missing_skills=missing, matrix=matrix,
                       evidence=[EvidenceItem(**{k: it.get(k) for k in EvidenceItem.model_fields if k in it} | {"score": it.get("relevance") or 0})
                                 for it in evidence],
                       reasons=[f"{sum(m.strength == 'strong' for m in matrix)} strong, {sum(m.strength == 'partial' for m in matrix)} partial, "
                                f"{len(missing)} unproven of {len(matrix)} requirements"])
    return {"fit": report.model_dump(), "evidence": [e.model_dump() for e in report.evidence], "trace": trace}
