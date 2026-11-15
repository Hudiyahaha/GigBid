"""B4 outcome metrics + X2 proposal A/B test on a FIXED job set (simulated GigSim clients).

For each job the bid graph runs to the human-approval interrupt (strategy A = evidence_first). Strategy B
(question_first) is drafted from the SAME analyses/evidence, so only the writing differs. Every client-facing letter
is scored by GigSim's simulated client (POST /admin/evaluate, stateless) under several seeds.

    python -m evals.runners.gigsim_outcomes --per-persona 8            # heuristic profile
    RAG_VARIANT=v0_naive python -m evals.runners.gigsim_outcomes --name gigsim_outcomes_v0   # retrieval ablation
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import time
import uuid

import httpx

from evals.common import PERSONAS, load_dev, mean, pct, write_result
from evals.gigsim_local import running_gigsim

SEEDS = [str(i) for i in range(10)]
GENERIC = ("Dear Sir/Madam, I am writing to express my interest in your project. I am a passionate and hardworking "
           "freelancer with great skills and I can deliver high quality work on time. Please message me to discuss.")


def two_prop_z(x1: int, n1: int, x2: int, n2: int) -> dict:
    if not n1 or not n2:
        return {}
    p1, p2, p = x1 / n1, x2 / n2, (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-9
    z = (p1 - p2) / se
    pval = math.erfc(abs(z) / math.sqrt(2))
    return {"p_a": round(p1, 4), "p_b": round(p2, 4), "diff": round(p1 - p2, 4), "z": round(z, 3), "p_value": round(pval, 4),
            "n_a": n1, "n_b": n2, "significant_at_0.05": pval < 0.05}


def score(base: str, job_id: str, persona: str, text: str, bid: float, answers: list[str]) -> dict:
    replies, hires, probs = 0, 0, []
    for s in SEEDS:
        r = httpx.post(base + "/admin/evaluate", headers={"Authorization": "Bearer gigsim-admin"},
                       json={"job_id": job_id, "persona": persona, "cover_letter": text, "bid_amount": bid,
                             "screening_answers": answers, "run_seed": s}, timeout=30).json()
        replies += r["reply"]
        hires += r["hire"]
        probs.append(r["reply_prob"])
    return {"replies": replies, "hires": hires, "n": len(SEEDS), "reply_prob": round(sum(probs) / len(probs), 4)}


async def run(base: str, per_persona: int) -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent import config, llm, mcp_client, runner
    from agent.graphs.bid_graph import build_bid_graph
    from agent.nodes.writer import heuristic_draft, strip_citations
    g = build_bid_graph(InMemorySaver(), InMemoryStore())
    rows = []
    for persona in PERSONAS:
        cands = [r for r in load_dev(persona) if r["gold_bid"] and r["kind"] in ("normal", "vague", "injection")]
        done = 0
        for r in cands:
            if done >= per_persona:
                break
            tid = f"out:{uuid.uuid4().hex[:8]}"
            mcp_client.RUN_CTX.set({"trace_id": tid, "user_id": "eval", "persona": persona})
            u = llm.start_usage(30000)
            t0 = time.perf_counter()
            state = {"thread_id": tid, "user_id": "eval", "persona": persona, "trace_id": tid, "job_id": r["job_id"], "job": {},
                     "prefs": runner.default_prefs(persona), "strategy": "evidence_first", "revisions": 0}
            await g.ainvoke(state, runner.cfg(tid))
            snap = await g.aget_state(runner.cfg(tid))
            v = snap.values
            intr = [i.value for t in snap.tasks for i in (t.interrupts or [])]
            if not intr:
                continue
            done += 1
            lat = time.perf_counter() - t0
            req = intr[0]
            pay = req["send_payload"]
            a = score(base, r["job_id"], persona, pay["cover_letter"], pay["bid_amount"], pay["screening_answers"])
            bd = heuristic_draft(v, v.get("evidence") or [], "question_first")
            b_text = strip_citations(bd["cover_letter"])
            b = score(base, r["job_id"], persona, b_text, pay["bid_amount"], [strip_citations(x["answer"]) for x in bd["screening_answers"]])
            gen = score(base, r["job_id"], persona, GENERIC, pay["bid_amount"], [])
            ver = req.get("verification") or {}
            rows.append({"job_id": r["job_id"], "persona": persona, "kind": r["kind"], "A_evidence_first": a, "B_question_first": b,
                         "generic_baseline": gen, "claims": ver.get("claims"), "unsupported_before": ver.get("unsupported_before"),
                         "unsupported_after_rate": ver.get("unsupported_rate_after"), "revisions": len(req.get("critiques") or []) - 1,
                         "latency_s": round(lat, 2), "tokens": u.tokens, "usd": round(u.usd, 6), "words": len(pay["cover_letter"].split()),
                         "letter_a": pay["cover_letter"], "letter_b": b_text, "title": (v.get("job") or {}).get("title")})
            print(f"{r['job_id']}: A {a['replies']}/10  B {b['replies']}/10  generic {gen['replies']}/10  {lat:.0f}s", flush=True)

    def tot(key, f):
        return sum(x[key][f] for x in rows)
    n = len(rows) * len(SEEDS)
    return {
        "variant": config.get("rag.variant"), "jobs": len(rows), "seeds_per_job": len(SEEDS),
        "reply_rate": {"evidence_first": round(tot("A_evidence_first", "replies") / max(1, n), 4),
                       "question_first": round(tot("B_question_first", "replies") / max(1, n), 4),
                       "generic_template": round(tot("generic_baseline", "replies") / max(1, n), 4)},
        "hire_rate": {"evidence_first": round(tot("A_evidence_first", "hires") / max(1, n), 4),
                      "question_first": round(tot("B_question_first", "hires") / max(1, n), 4)},
        "x2_ab_test": two_prop_z(tot("A_evidence_first", "replies"), n, tot("B_question_first", "replies"), n),
        "unsupported_claims_per_proposal_before": mean([x["unsupported_before"] for x in rows]),
        "unsupported_rate_after_verification": mean([x["unsupported_after_rate"] for x in rows]),
        "critic_revisions_mean": mean([x["revisions"] for x in rows]),
        "latency_s_per_proposal": {"p50": pct([x["latency_s"] for x in rows], 0.5), "p95": pct([x["latency_s"] for x in rows], 0.95)},
        "tokens_per_proposal": mean([x["tokens"] for x in rows]), "usd_per_proposal": mean([x["usd"] for x in rows]),
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=8)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--name", default="gigsim_outcomes")
    a = ap.parse_args()
    if not a.llm:
        os.environ["GIGBID_FAKE_LLM"] = "1"
    os.environ.setdefault("GIGBID_LOCAL_SQLITE", "1")
    with running_gigsim(8093, error_rate="0") as base:
        res = asyncio.run(run(base, a.per_persona))
    res["profile"] = "open (Groq)" if a.llm else "heuristic (no LLM)"
    print({k: res[k] for k in ("reply_rate", "x2_ab_test", "unsupported_claims_per_proposal_before", "latency_s_per_proposal")})
    write_result(a.name, res)


if __name__ == "__main__":
    main()
