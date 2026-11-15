"""B4 retrieval evaluation: every variant on the dev set, per persona and per job type.

    python -m evals.runners.rag_eval                       # all variants, full dev set
    python -m evals.runners.rag_eval --variants v0_naive,v2_hybrid --limit 50

Writes evals/results/rag_variants.json and evals/results/rag_variants.csv.
Metrics are computed on jobs that have >=1 gold evidence item. On zero-gold jobs we report the
"false evidence rate": how often the retriever returns anything a writer could wrongly cite
(only meaningful for the corrective variant, which can abstain).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from agent.guardrails import strip_injections
from evals.common import (
    PERSONAS,
    RESULTS,
    load_dev,
    load_jobs,
    mean,
    mrr,
    ndcg_at,
    pct,
    recall_at,
    strict_gold,
    write_result,
)
from rag import variants as V
from rag.pipeline import Flags, Pipeline, Query
from rag.query import decompose

ROOT = Path(__file__).resolve().parents[2]
HYDE_PATH = ROOT / "data" / "processed" / "hyde.json"
EXACT_TOOLS = {"Celery", "dbt", "Pinecone", "FAISS", "Prisma", "NestJS", "Snowflake", "BigQuery", "MLflow", "Airflow",
               "XGBoost", "spaCy", "Prophet", "Playwright", "Stripe", "Shopify"}


def job_types(row: dict, job: dict) -> list[str]:
    t = [row["kind"]]
    if row["n_requirements"] >= 4:
        t.append("multi_req_4plus")
    if any(s in job["description"] for s in EXACT_TOOLS):
        t.append("exact_tool_names")
    return t


def build_query(row: dict, job: dict, hyde: dict, clean: bool = False) -> Query:
    desc = strip_injections(job["description"])[0] if clean else job["description"]
    return Query(persona=row["persona"], title=job["title"], text=desc, requirements=decompose(job["description"]),
                 hyde_text=hyde.get(job["job_id"]), industry=job.get("industry"))


async def make_hyde(rows: list[dict], jobs: dict) -> dict:
    from agent import llm
    from rag.query import hyde_text
    llm.start_usage()
    cache = json.loads(HYDE_PATH.read_text(encoding="utf-8")) if HYDE_PATH.exists() else {}
    for r in rows:
        j = jobs[r["job_id"]]
        if j["job_id"] not in cache:
            cache[j["job_id"]] = await hyde_text(j["title"], strip_injections(j["description"])[0])
    HYDE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache


def evaluate(variants: dict[str, Flags], limit: int | None, personas: list[str], k_eval: int = 10) -> dict:
    jobs = load_jobs()
    hyde = json.loads(HYDE_PATH.read_text(encoding="utf-8")) if HYDE_PATH.exists() else {}
    out: dict = {"variants": {}, "n_jobs": {}}
    per_job_rows = []
    for vname, flags in variants.items():
        agg: dict[str, list] = defaultdict(list)
        by_persona: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        by_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        lat = []
        false_ev = []
        t_build = time.perf_counter()
        for persona in personas:
            pipe = Pipeline.get(persona, flags)
            rows = load_dev(persona)[:limit] if limit else load_dev(persona)
            out["n_jobs"][persona] = len(rows)
            for row in rows:
                job = jobs[row["job_id"]]
                res = pipe.retrieve(build_query(row, job, hyde), k=k_eval)
                ranked = [it["item_id"] for it in res.items]
                lat.append(res.latency_s)
                gold = row["gold_evidence"]
                if not gold:
                    false_ev.append(1.0 if ranked else 0.0)
                    continue
                sg = strict_gold(gold)
                m = {"recall@5": recall_at(ranked, sg, 5), "mrr": mrr(ranked, sg), "ndcg@10": ndcg_at(ranked, gold, 10)}
                for kk, vv in m.items():
                    agg[kk].append(vv)
                    by_persona[persona][kk].append(vv)
                    for t in job_types(row, job):
                        by_type[t][kk].append(vv)
                per_job_rows.append({"variant": vname, "job_id": row["job_id"], "persona": persona, "kind": row["kind"], **m})
        out["variants"][vname] = {
            "flags": flags.__dict__,
            "overall": {k: mean(v) for k, v in agg.items()} | {"n": len(agg["mrr"])},
            "by_persona": {p: {k: mean(v) for k, v in d.items()} for p, d in by_persona.items()},
            "by_job_type": {t: {k: mean(v) for k, v in d.items()} | {"n": len(d["mrr"])} for t, d in by_type.items()},
            "false_evidence_rate_on_zero_gold": mean(false_ev),
            "latency_s": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95)},
            "build_plus_eval_s": round(time.perf_counter() - t_build, 1),
        }
        o = out["variants"][vname]["overall"]
        print(f"{vname:16s} R@5={o['recall@5']:.3f} MRR={o['mrr']:.3f} nDCG@10={o['ndcg@10']:.3f} "
              f"p95={out['variants'][vname]['latency_s']['p95']}s", flush=True)
    out["per_job"] = per_job_rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="all")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--personas", default=",".join(PERSONAS))
    ap.add_argument("--make-hyde", action="store_true", help="generate HyDE texts with the LLM first (cached)")
    ap.add_argument("--name", default="rag_variants")
    a = ap.parse_args()
    import os
    os.environ.setdefault("RAG_NO_RELEVANCE", "1")  # relevance scores are for the Fit Matcher, not retrieval metrics
    personas = a.personas.split(",")
    allv = V.all_variants()
    chosen = allv if a.variants == "all" else {n: allv[n] for n in a.variants.split(",")}
    if a.make_hyde:
        rows = [r for p in personas for r in (load_dev(p)[:a.limit] if a.limit else load_dev(p))]
        asyncio.run(make_hyde(rows, load_jobs()))
    res = evaluate(chosen, a.limit, personas)
    path = write_result(a.name, {k: v for k, v in res.items() if k != "per_job"})
    with open(RESULTS / f"{a.name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["variant", "recall@5", "mrr", "ndcg@10", "p95_latency_s", "false_evidence_rate"])
        for n, v in res["variants"].items():
            w.writerow([n, v["overall"]["recall@5"], v["overall"]["mrr"], v["overall"]["ndcg@10"], v["latency_s"]["p95"],
                        v["false_evidence_rate_on_zero_gold"]])
    (RESULTS / f"{a.name}_per_job.jsonl").write_text("\n".join(json.dumps(r) for r in res["per_job"]), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
