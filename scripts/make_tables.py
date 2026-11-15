"""Regenerate every results table in README.md and docs/report/REPORT.md from evals/results/*.json.
Numbers are never typed by hand: `python -m scripts.make_tables` after any eval run."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "evals" / "results"


def j(name: str) -> dict | None:
    p = R / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def f(x, nd=3) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "-"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def rag_table() -> str:
    full, sub = j("rag_variants") or {"variants": {}}, j("rag_variants_rerank_subset") or {"variants": {}}
    out = ["| Variant | Recall@5 | MRR | nDCG@10 | p95 latency (s) | n jobs |", "|---|---|---|---|---|---|"]
    for name, v in list(full["variants"].items()) + [(k + " (subset)", v) for k, v in sub["variants"].items()]:
        o = v["overall"]
        out.append(f"| {name} | {f(o['recall@5'])} | {f(o['mrr'])} | {f(o['ndcg@10'])} | {f(v['latency_s']['p95'], 4)} | {o['n']} |")
    return "\n".join(out)


def headline_table() -> str:
    full = (j("rag_variants") or {}).get("variants", {})
    out_now, out_v0 = j("gigsim_outcomes"), j("gigsim_outcomes_v0")
    demo = j("demo_proposal") or {}
    rows = ["| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 latency (s) | Cost / proposal (USD) |",
            "|---|---|---|---|---|---|---|---|"]
    for name, o in (("V0 (naive dense)", out_v0), ("Shipped: V9 skill graph", out_now)):
        key = "v0_naive" if name.startswith("V0") else "v9_skill_graph"
        v = full.get(key, {}).get("overall", {})
        rows.append(f"| {name} | {f(v.get('recall@5'))} | {f(v.get('ndcg@10'))} | "
                    f"{f((o or {}).get('unsupported_claims_per_proposal_before'))} | see judge_labels.csv | "
                    f"{f(((o or {}).get('reply_rate') or {}).get('evidence_first'))} | "
                    f"{f(((o or {}).get('latency_s_per_proposal') or {}).get('p95'), 1)} | "
                    f"{f(demo.get('usage', {}).get('usd'), 4) if name.startswith('Shipped') else '-'} |")
    return "\n".join(rows)


def decision_table() -> str:
    rows = ["| Profile | Bid/skip F1 | Accuracy | Scam precision | Scam recall | Price in fair band | p95 latency / job (s) | Tokens / job | n |",
            "|---|---|---|---|---|---|---|---|---|"]
    for name in ("decision_eval", "decision_eval_llm"):
        d = j(name)
        if not d:
            continue
        o = d["overall"]
        rows.append(f"| {d.get('profile', name)} | {f(o['bid_skip']['f1'])} | {f(o['bid_skip']['accuracy'])} | {f(o['scam']['precision'])} | "
                    f"{f(o['scam']['recall'])} | {f(o['price_in_fair_band'])} | {f(o['latency_s_per_job']['p95'], 1)} | "
                    f"{f(o['tokens_per_job'], 0)} | {o['bid_skip']['n']} |")
    return "\n".join(rows)


def outcome_table() -> str:
    o = j("gigsim_outcomes")
    if not o:
        return "_pending: run `python -m evals.runners.gigsim_outcomes`_"
    x = o["x2_ab_test"]
    return "\n".join([
        "| Strategy | Reply rate | Hire rate |", "|---|---|---|",
        f"| evidence_first | {f(o['reply_rate']['evidence_first'])} | {f(o['hire_rate']['evidence_first'])} |",
        f"| question_first | {f(o['reply_rate']['question_first'])} | {f(o['hire_rate']['question_first'])} |",
        f"| generic template (floor) | {f(o['reply_rate']['generic_template'])} | - |", "",
        f"Two-proportion z-test (evidence_first vs question_first): diff {f(x.get('diff'))}, z {f(x.get('z'))}, "
        f"p {f(x.get('p_value'), 4)}, n {x.get('n_a')} per arm ({o['jobs']} jobs x {o['seeds_per_job']} simulated clients)."])


def svm_table() -> str:
    s = (j("single_vs_multi") or {}).get("summary")
    if not s:
        return "_pending: run `python -m evals.runners.single_vs_multi`_"
    rows = ["| Design | Bid/skip accuracy | Unsupported claims / proposal | Compliance violations left | Tokens / job | Latency / job (s) | Errors | n |",
            "|---|---|---|---|---|---|---|---|"]
    for k in ("react", "supervisor", "graph"):
        v = s[k]
        rows.append(f"| {k} | {f(v['bid_skip_accuracy'])} | {f(v['unsupported_claims_per_proposal'])} | {v['compliance_violations_left']} | "
                    f"{f(v['tokens_per_job'], 0)} | {f(v['latency_s_per_job'], 1)} | {v['errors']} | {v['n']} |")
    return "\n".join(rows)


def tool_table() -> str:
    t = j("tool_study")
    if not t:
        return "_pending: run `python -m evals.runners.tool_study`_"
    rows = [f"Model: {t['model']} (local), {t['n_tasks']} tasks.", "", "| Tool design | Tools | Selection accuracy | Argument accuracy | Tokens / task |",
            "|---|---|---|---|---|"]
    for k, v in t["designs"].items():
        rows.append(f"| {k} | {v['n_tools']} | {f(v['selection_accuracy'])} | {f(v['argument_accuracy'])} | {f(v['tokens_per_task'], 0)} |")
    return "\n".join(rows)


def injection_table() -> str:
    i = j("injection_eval")
    if not i:
        return "_pending_"
    return (f"Planted-injection dev jobs: {i['n_injection_jobs']}; rule detection rate {f(i['rule_detection_rate'])}. "
            f"LLM sample n={i['llm_sample']}: attack success before stripping/delimiting {f(i['attack_success_before'])}, "
            f"after {f(i['attack_success_after'])}.")


def failures_table() -> str:
    d = j("decision_eval")
    if not d:
        return "_pending_"
    rows = ["| Job | Persona | Type | Gold | Predicted | Taxonomy | Evidence from the trace |", "|---|---|---|---|---|---|---|"]
    picked = 0
    for r in d["rows"]:
        wrong_dec = (r["pred"] == "bid") != r["gold_bid"]
        mispriced = r.get("in_band") is False
        if not (wrong_dec or mispriced) or picked >= 14:
            continue
        reasons = "; ".join(r.get("reasons") or [])[:90]
        if wrong_dec and r["gold_bid"]:
            tax = "missed evidence (vague post)" if r["kind"] == "vague" else ("wrong skip (budget rule)" if "budget" in reasons else "missed evidence / wrong skip")
        elif wrong_dec:
            tax = "wrong bid (partial fit accepted)"
        else:
            tax = "mispriced"
        rows.append(f"| {r['job_id']} | {r['persona']} | {r['kind']} | {'bid' if r['gold_bid'] else 'skip'} | {r['pred']} | {tax} | "
                    f"{reasons or ('price ' + str(r.get('price')) + ' vs band ' + str(r['fair_band']))} |")
        picked += 1
    return "\n".join(rows)


def holdout_table() -> str:
    d = j("decision_eval_holdout")
    if not d:
        return "_pending: hidden-set run_"
    o = d["overall"]
    return (f"Held-out set ({o['bid_skip']['n']} jobs, never used for tuning): bid/skip F1 {f(o['bid_skip']['f1'])}, "
            f"accuracy {f(o['bid_skip']['accuracy'])}, scam precision {f(o['scam']['precision'])} / recall {f(o['scam']['recall'])}, "
            f"price in fair band {f(o['price_in_fair_band'])}, p95 latency per job {f(o['latency_s_per_job']['p95'], 1)} s.")


BLOCKS = {"failures": failures_table, "holdout": holdout_table, "rag": rag_table, "headline": headline_table, "decision": decision_table, "outcomes": outcome_table,
          "svm": svm_table, "tools": tool_table, "injection": injection_table}


def fill(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for k, fn in BLOCKS.items():
        text = re.sub(rf"(<!-- table:{k} -->)(.*?)(<!-- /table:{k} -->)", lambda m, fn=fn: f"{m.group(1)}\n{fn()}\n{m.group(3)}", text, flags=re.S)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    for p in (ROOT / "README.md", ROOT / "docs" / "report" / "REPORT.md"):
        fill(p)
    print("tables regenerated")
