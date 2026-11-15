"""Export the four required execution traces to docs/traces/*.json (node-by-node, every MCP tool call with masked
args, latency, tokens, cost). Deterministic heuristic profile so they can be regenerated anywhere:
    GIGBID_FAKE_LLM=1 python -m scripts.export_traces
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

os.environ.setdefault("GIGBID_FAKE_LLM", "1")
os.environ.setdefault("GIGBID_LOCAL_SQLITE", "1")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "traces"
TMP = ROOT / "data" / "processed" / "traces"
TMP.mkdir(parents=True, exist_ok=True)
os.environ["GIGBID_CHECKPOINT_DB"] = str(TMP / "checkpoints.db")
os.environ["GIGSIM_STATE_PATH"] = str(TMP / "gigsim.db")
for f in TMP.glob("*.db"):
    f.unlink()


def dump(name: str, title: str, outs: list[dict], note: str = "") -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs = []
    for o in outs:
        v = o["values"]
        runs.append({"trace_id": o["trace_id"], "thread_id": o["thread_id"], "status": v.get("status"),
                     "decision": v.get("decision"), "risk": {k: (v.get("risk") or {}).get(k) for k in ("score", "scam", "flags")},
                     "fit_score": (v.get("fit") or {}).get("score"), "price": (v.get("price") or {}).get("amount"),
                     "critiques": [{k: c.get(k) for k in ("version", "passed", "issues")} for c in v.get("critiques") or []],
                     "verification": (v.get("verification") or {}).get("last"), "submission": v.get("submission"),
                     "usage": v.get("usage"), "latency_s": o["latency_s"], "trace": v.get("trace")})
    (OUT / f"{name}.json").write_text(json.dumps({"case": title, "note": note, "runs": runs}, indent=1, default=str), encoding="utf-8")
    print("wrote", name)


async def main() -> None:
    from agent import approval_token
    from agent.persistence import open_persistence
    from agent.runner import Graphs, resume, start_bid
    from evals.common import load_dev
    rows = load_dev("ai_ml")
    user = "trace-user"
    async with open_persistence() as (cp, st):
        g = Graphs(cp, st)
        scam = next(r for r in rows if r["gold_scam"] and r["domain"] == "ai_ml") if any(
            r["gold_scam"] and r["domain"] == "ai_ml" for r in rows) else next(r for r in rows if r["gold_scam"])
        dump("skipped_scam", "A scam post is skipped with reasons (no proposal drafted)",
             [await start_bid(g, scam["job_id"], user, "ai_ml")])
        approved = loop = None
        for r in [r for r in rows if r["gold_bid"] and r["kind"] in ("normal", "vague")][:40]:
            o = await start_bid(g, r["job_id"], user, "ai_ml")
            if o["interrupt"]:
                if len(o["values"].get("critiques") or []) > 1 and loop is None:
                    loop = o
                elif approved is None:
                    approved = o
            if approved and loop:
                break
        if approved:
            req = approved["interrupt"]
            done = await resume(g, "bid", approved["thread_id"], {"action": "approve", "user_id": user,
                                "approval_token": approval_token.mint(user, "proposal", req["send_payload"])}, user, "ai_ml")
            dump("approved_proposal", "Draft -> claim verification -> critic -> compliance -> human approval -> submitted",
                 [approved, done])
        if loop:
            dump("critic_loop", "The Critic sends the draft back to the Writer (bounded at 2 revisions)", [loop])
        crash = next(r for r in rows if r["gold_bid"] and r["kind"] == "normal" and (not approved or r["job_id"] != approved["values"]["job_id"]))
        first = await start_bid(g, crash["job_id"], user, "ai_ml", thread_id=f"{user}:bid:crash")
    # "crash": the process's persistence is closed while the thread waits for approval; a new one resumes it
    async with open_persistence() as (cp, st):
        g2 = Graphs(cp, st)
        if first["interrupt"]:
            req = first["interrupt"]
            dec = {"action": "approve", "user_id": user, "approval_token": approval_token.mint(user, "proposal", req["send_payload"])}
            after = await resume(g2, "bid", first["thread_id"], dec, user, "ai_ml")
            again = await resume(g2, "bid", first["thread_id"], dec, user, "ai_ml")
            dump("crash_and_resume", "Run stops at approval; persistence is closed (crash) and reopened; approval resumes the "
                 "SAME thread; a duplicate resume does not submit twice", [first, after, again],
                 note="runs[1].submission is the single submission; runs[2] shows no new executor call / idempotent replay")


if __name__ == "__main__":
    asyncio.run(main())
