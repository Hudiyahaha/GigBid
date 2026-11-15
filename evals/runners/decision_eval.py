"""B4 decision metrics: bid-or-skip F1, scam precision/recall, price inside the fair band, latency, tokens, USD.

Runs the bid graph up to (not including) the Writer, so analyses + decision + pricing are measured without drafting.
    python -m evals.runners.decision_eval --limit 40              # deterministic heuristic profile (GIGBID_FAKE_LLM=1)
    python -m evals.runners.decision_eval --limit 8 --llm         # open LLM profile (rate-limited free tier: small n)
Writes evals/results/decision_eval[_llm].json
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid

from evals.common import PERSONAS, f1, load_dev, mean, pct, write_result
from evals.gigsim_local import running_gigsim


def stratified(rows: list[dict], n: int) -> list[dict]:
    """Keep the dev set's mix: take every k-th row so scams, injections and vague posts stay represented."""
    if not n or n >= len(rows):
        return rows
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]


async def run(limit: int | None, personas: list[str], split: str) -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent import llm, mcp_client, runner
    from agent.graphs.bid_graph import build_bid_graph
    g = build_bid_graph(InMemorySaver(), InMemoryStore(), interrupt_before=["writer"])
    out = {"by_persona": {}, "rows": []}
    tp = fp = fn = tn = 0
    s_tp = s_fp = s_fn = 0
    band_hits, band_n, lat, toks, usd = 0, 0, [], [], []
    for persona in personas:
        rows = stratified(load_dev(persona, split), limit)
        p_tp = p_fp = p_fn = p_tn = 0
        for r in rows:
            tid = f"eval:{uuid.uuid4().hex[:8]}"
            mcp_client.RUN_CTX.set({"trace_id": tid, "user_id": "eval", "persona": persona})
            u = llm.start_usage(30000)
            t0 = time.perf_counter()
            state = {"thread_id": tid, "user_id": "eval", "persona": persona, "trace_id": tid, "job_id": r["job_id"],
                     "job": {}, "prefs": runner.default_prefs(persona), "revisions": 0}
            await g.ainvoke(state, runner.cfg(tid))
            v = (await g.aget_state(runner.cfg(tid))).values
            dt = time.perf_counter() - t0
            action = (v.get("decision") or {}).get("action", "skip")
            pred_bid = action == "bid" and v.get("status") not in ("skipped",)
            pred_scam = bool((v.get("risk") or {}).get("scam"))
            gold_bid, gold_scam = r["gold_bid"], r["gold_scam"]
            tp += pred_bid and gold_bid
            fp += pred_bid and not gold_bid
            fn += (not pred_bid) and gold_bid
            tn += (not pred_bid) and not gold_bid
            p_tp += pred_bid and gold_bid
            p_fp += pred_bid and not gold_bid
            p_fn += (not pred_bid) and gold_bid
            p_tn += (not pred_bid) and not gold_bid
            s_tp += pred_scam and gold_scam
            s_fp += pred_scam and not gold_scam
            s_fn += (not pred_scam) and gold_scam
            price = (v.get("price") or {}).get("amount")
            in_band = None
            if price and gold_bid:
                lo, hi = r["fair_band"]
                in_band = lo <= price <= hi
                band_n += 1
                band_hits += in_band
            lat.append(dt)
            toks.append(u.tokens)
            usd.append(u.usd)
            out["rows"].append({"job_id": r["job_id"], "persona": persona, "kind": r["kind"], "gold_bid": gold_bid,
                                "pred": action, "status": v.get("status"), "fit": (v.get("fit") or {}).get("score"),
                                "risk": (v.get("risk") or {}).get("score"), "gold_scam": gold_scam, "pred_scam": pred_scam,
                                "price": price, "fair_band": r["fair_band"], "in_band": in_band,
                                "reasons": (v.get("decision") or {}).get("reasons"), "gold_reasons": r["gold_skip_reasons"],
                                "latency_s": round(dt, 2), "tokens": u.tokens})
            print(f"{r['job_id']:18s} gold={'bid ' if gold_bid else 'skip'} pred={action:5s} fit={(v.get('fit') or {}).get('score', 0):.2f} "
                  f"{dt:.1f}s", flush=True)
        out["by_persona"][persona] = {**f1(p_tp, p_fp, p_fn), "n": len(rows), "accuracy": round((p_tp + p_tn) / max(1, len(rows)), 4)}
    n = tp + fp + fn + tn
    out["overall"] = {"bid_skip": {**f1(tp, fp, fn), "accuracy": round((tp + tn) / max(1, n), 4), "n": n,
                                   "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}},
                      "scam": f1(s_tp, s_fp, s_fn), "price_in_fair_band": round(band_hits / band_n, 4) if band_n else None,
                      "price_n": band_n,
                      "latency_s_per_job": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95)},
                      "tokens_per_job": mean(toks), "usd_per_job": round(sum(usd) / max(1, len(usd)), 6)}
    by_kind: dict = {}
    for row in out["rows"]:
        k = by_kind.setdefault(row["kind"], {"n": 0, "correct": 0})
        k["n"] += 1
        k["correct"] += (row["pred"] == "bid") == row["gold_bid"]
    out["accuracy_by_job_type"] = {k: {"accuracy": round(v["correct"] / v["n"], 3), "n": v["n"]} for k, v in by_kind.items()}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--llm", action="store_true", help="use the open LLM profile instead of deterministic heuristics")
    ap.add_argument("--personas", default=",".join(PERSONAS))
    ap.add_argument("--split", default="dev")
    a = ap.parse_args()
    if not a.llm:
        os.environ["GIGBID_FAKE_LLM"] = "1"
    os.environ.setdefault("GIGBID_LOCAL_SQLITE", "1")
    with running_gigsim(8091 if a.split == "dev" else 8092, error_rate="0"):
        res = asyncio.run(run(a.limit, a.personas.split(","), a.split))
    name = "decision_eval" + ("_llm" if a.llm else "") + ("" if a.split == "dev" else f"_{a.split}")
    res["profile"] = "open (Groq)" if a.llm else "heuristic (no LLM)"
    print(res["overall"])
    write_result(name, res)


if __name__ == "__main__":
    main()
