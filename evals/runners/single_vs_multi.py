"""R&D question C: one ReAct agent with all tools vs a prebuilt supervisor vs our hand-built graph.

Same open model for all three (Groq gpt-oss-20b), same jobs. Metrics: bid-or-skip accuracy, unsupported claims per
proposal (rag/verify.py against the cited evidence), compliance violations in the final text (rules.yaml patterns the
design failed to remove), tokens and latency. Free-tier rate limits => small n, reported as such.

    python -m evals.runners.single_vs_multi --per-persona 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
import uuid

from evals.common import PERSONAS, load_dev, mean, write_result
from evals.gigsim_local import running_gigsim

MODEL = "openai/gpt-oss-20b"


def chat():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=MODEL, base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"],
                      temperature=0.2, max_retries=6, timeout=120)


def parse_final(text: str) -> dict:
    m = re.findall(r"\{.*\}", text or "", re.S)
    for cand in reversed(m):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return {"decision": "skip" if "skip" in (text or "").lower() else "bid", "cover_letter": text}


def violations(text: str) -> int:
    from agent import policy
    return sum(1 for r in policy.rules()["forbidden_patterns"] for rx in r["_rx"] if rx.search(text or ""))


async def grounding(letter: str) -> dict:
    from agent.nodes.verifier import load_evidence
    from rag import verify as V
    ev = await load_evidence(list(dict.fromkeys(V.CITE.findall(letter or ""))))
    checks = V.verify_text(letter or "", ev)
    return {"claims": len(checks), "unsupported": sum(c.status == "unsupported" for c in checks)}


def tokens_of(msgs) -> int:
    return sum(((getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0)) for m in msgs)


async def run_react(job_id: str, persona: str, floor: float) -> dict:
    from langgraph.prebuilt import create_react_agent

    from agent import mcp_client
    from agent.prompts import render
    tools = [t for t in await mcp_client.langchain_tools("__all__")]
    system, user, _ = render("react_agent", {"persona": persona, "floor": floor, "job_id": job_id})
    agent = create_react_agent(chat(), tools, prompt=system)
    t0 = time.perf_counter()
    out = await agent.ainvoke({"messages": [("user", user)]}, {"recursion_limit": 16})
    msgs = out["messages"]
    return {"final": parse_final(msgs[-1].content), "tokens": tokens_of(msgs), "latency_s": time.perf_counter() - t0,
            "tool_calls": sum(len(getattr(m, "tool_calls", []) or []) for m in msgs)}


async def run_supervisor(job_id: str, persona: str, floor: float) -> dict:
    from langgraph.prebuilt import create_react_agent
    from langgraph_supervisor import create_supervisor

    from agent import mcp_client
    allt = {t.name: t for t in await mcp_client.langchain_tools("__all__")}
    analyst = create_react_agent(chat(), [allt[n] for n in ("get_job", "get_client_history", "search_evidence", "get_market_stats")],
                                 name="analyst", prompt="Analyse the job: fit (search_evidence), client risk, price. Report bid or skip with reasons.")
    writer = create_react_agent(chat(), [allt[n] for n in ("search_evidence", "get_case_study")], name="writer",
                                prompt="Write a 120-220 word proposal citing evidence as [E:item_id]. Never invent experience.")
    sup = create_supervisor([analyst, writer], model=chat(), prompt=(
        f"You manage a freelancer ({persona}, floor ${floor}). Ask the analyst to assess job {job_id}; if it should be bid, "
        "ask the writer for a proposal. Finish with JSON {\"decision\": \"bid|skip\", \"reason\": str, \"cover_letter\": str|null}.")).compile()
    t0 = time.perf_counter()
    out = await sup.ainvoke({"messages": [("user", f"Handle job {job_id}.")]}, {"recursion_limit": 30})
    msgs = out["messages"]
    return {"final": parse_final(msgs[-1].content), "tokens": tokens_of(msgs), "latency_s": time.perf_counter() - t0}


async def run_graph(g, job_id: str, persona: str) -> dict:
    from agent import llm, runner
    tid = f"svm:{uuid.uuid4().hex[:8]}"
    u = llm.start_usage(40000)
    t0 = time.perf_counter()
    await g.ainvoke({"thread_id": tid, "user_id": "eval", "persona": persona, "trace_id": tid, "job_id": job_id, "job": {},
                     "prefs": runner.default_prefs(persona), "revisions": 0}, runner.cfg(tid))
    snap = await g.aget_state(runner.cfg(tid))
    v = snap.values
    intr = [i.value for t in snap.tasks for i in (t.interrupts or [])]
    letter = intr[0]["draft"]["cover_letter"] if intr else None
    return {"final": {"decision": "bid" if intr else "skip", "cover_letter": letter,
                      "caught": len((v.get("compliance") or {}).get("redactions", []))},
            "tokens": u.tokens, "latency_s": time.perf_counter() - t0}


async def run(per_persona: int) -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent import llm, mcp_client, runner
    from agent.graphs.bid_graph import build_bid_graph
    llm.PROFILE_OVERRIDE.set("open_alt") if False else None
    g = build_bid_graph(InMemorySaver(), InMemoryStore())
    res = {"react": [], "supervisor": [], "graph": []}
    for persona in PERSONAS:
        rows = load_dev(persona)
        pick = [r for r in rows if r["gold_bid"] and r["kind"] == "normal"][:per_persona] + \
               [r for r in rows if r["gold_scam"] or r["injection_id"] is not None][:1]
        floor = runner.default_prefs(persona)["hourly_floor"]
        for r in pick:
            mcp_client.RUN_CTX.set({"trace_id": "svm", "user_id": "eval", "persona": persona})
            for name, fn in (("graph", lambda: run_graph(g, r["job_id"], persona)),
                             ("react", lambda: run_react(r["job_id"], persona, floor)),
                             ("supervisor", lambda: run_supervisor(r["job_id"], persona, floor))):
                try:
                    o = await fn()
                except Exception as e:  # noqa: BLE001 - record failures, they are results too
                    o = {"final": {"decision": "error", "cover_letter": None}, "tokens": 0, "latency_s": 0, "error": str(e)[:200]}
                letter = o["final"].get("cover_letter") or ""
                gr = await grounding(letter) if letter else {"claims": 0, "unsupported": 0}
                res[name].append({"job_id": r["job_id"], "kind": r["kind"], "gold_bid": r["gold_bid"], "decision": o["final"].get("decision"),
                                  "correct": (o["final"].get("decision") == "bid") == r["gold_bid"], "violations_left": violations(letter),
                                  **gr, "tokens": o["tokens"], "latency_s": round(o["latency_s"], 1), "error": o.get("error")})
                print(name, r["job_id"], res[name][-1]["decision"], res[name][-1]["correct"], flush=True)
    summary = {k: {"n": len(v), "bid_skip_accuracy": mean([x["correct"] for x in v]),
                   "unsupported_claims_per_proposal": mean([x["unsupported"] for x in v if x["decision"] == "bid"]),
                   "compliance_violations_left": sum(x["violations_left"] for x in v),
                   "tokens_per_job": mean([x["tokens"] for x in v]), "latency_s_per_job": mean([x["latency_s"] for x in v]),
                   "errors": sum(1 for x in v if x["error"])} for k, v in res.items()}
    return {"model": MODEL, "summary": summary, "rows": res}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=2)
    a = ap.parse_args()
    os.environ.setdefault("GIGBID_LOCAL_SQLITE", "1")
    from dotenv import load_dotenv
    load_dotenv(".env")
    os.environ.setdefault("MODEL_PROFILE", "open")
    with running_gigsim(8094, error_rate="0"):
        out = asyncio.run(run(a.per_persona))
    print(json.dumps(out["summary"], indent=1))
    write_result("single_vs_multi", out)


if __name__ == "__main__":
    main()
