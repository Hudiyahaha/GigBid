"""Part A deliverable: one agent run drafting one grounded proposal for a GigSim job (stops at human approval).

    python -m evals.runners.demo_single_proposal --job dev-ai_ml-004 --persona ai_ml
Writes evals/results/demo_proposal.json (draft, claims with evidence, verification, usage, trace summary).
"""

from __future__ import annotations

import argparse
import asyncio
import json

from evals.common import load_dev, write_result
from evals.gigsim_local import running_gigsim


async def run(job_id: str | None, persona: str) -> dict:
    from agent.persistence import open_persistence
    from agent.runner import Graphs, start_bid

    rows = [r for r in load_dev(persona) if r["gold_bid"] and r["kind"] == "normal"]
    candidates = [job_id] if job_id else [r["job_id"] for r in rows[:15]]
    async with open_persistence() as (cp, st):
        g = Graphs(cp, st)
        for jid in candidates:
            events = []

            async def on(ev, _e=events):
                _e.append(ev)
                print(f"  [{ev.get('t', '')}] {ev.get('node', ev.get('type'))}: "
                      f"{ {k: v for k, v in ev.items() if k not in ('type', 'node', 't')} }", flush=True)
            print(f"== {jid}")
            out = await start_bid(g, jid, "demo-user", persona, thread_id=f"demo-user:bid:{jid}", on_event=on)
            if out["interrupt"]:
                req = out["interrupt"]
                return {"job_id": jid, "persona": persona, "status": out["values"].get("status"),
                        "cover_letter_with_citations": req["draft"]["cover_letter"],
                        "client_facing": req["send_payload"], "claims": req["claims"], "verification": req["verification"],
                        "critiques": req["critiques"], "compliance": req["compliance"], "price": req["price"],
                        "fit": {"score": req["fit"]["score"], "matrix": req["fit"]["matrix"]}, "risk": req["risk"],
                        "dry_run_preview": req["preview"], "usage": out["usage"], "latency_s": out["latency_s"],
                        "trace_id": out["trace_id"], "events": events}
            print("   ->", out["values"].get("status"), (out["values"].get("decision") or {}).get("reasons"))
    return {"error": "no candidate reached approval"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default=None)
    ap.add_argument("--persona", default="ai_ml")
    a = ap.parse_args()
    with running_gigsim(error_rate="0"):
        res = asyncio.run(run(a.job, a.persona))
    print(json.dumps({k: res.get(k) for k in ("job_id", "status", "verification", "usage", "latency_s")}, indent=1, default=str))
    print("\n--- COVER LETTER (with citations) ---\n" + str(res.get("cover_letter_with_citations")))
    write_result("demo_proposal", res)


if __name__ == "__main__":
    main()
