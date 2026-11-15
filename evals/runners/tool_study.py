"""R&D question A: does tool granularity change agent behaviour?

40 tasks with known correct calls x 3 tool designs, one tool call per task, local open model (Ollama llama3.2, no
rate limits). Metrics: tool-selection accuracy, argument accuracy, prompt tokens per task.
    python -m evals.runners.tool_study [--model llama3.2] [--n 40]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random

import httpx

from evals.common import load_dev, load_jobs, write_result

REWRITE = {
    "search_evidence": "Use when you need PROOF from the freelancer's own past work for a skill or requirement. "
                       "Example: 'have I used Celery?' -> requirement='Celery background tasks'.",
    "get_case_study": "Use when you already know a case study id like cs-ai_ml-p01 and need its full text.",
    "list_skills": "Use to list every skill the portfolio can prove, with counts. No arguments.",
    "search_jobs": "Use to FIND open job posts by keywords. Example: 'find dashboard jobs' -> query='dashboard'.",
    "get_job": "Use when you have a job id (e.g. dev-ai_ml-004) and need the full post.",
    "get_client_history": "Use to check whether a CLIENT is trustworthy (payment verified, hires, ratings). Needs client_id (cl-0001).",
    "get_connects_balance": "Use to know how many Connects the freelancer has left. No arguments.",
    "get_market_stats": "Use to get typical PRICES (p25/p50/p75) for a job category. Example: category='Dashboards & BI'.",
    "list_messages": "Use to read the messages of one client conversation; needs thread_id.",
    "free_slots": "Use to find free calendar times for an interview; days = how far ahead to look.",
}


def tasks(n: int) -> list[dict]:
    rng = random.Random(7)
    jobs = load_jobs()
    rows = load_dev("ai_ml")
    jids = [r["job_id"] for r in rows[:30]]
    cids = list({jobs[j]["client_id"] for j in jids})
    cats = ["Dashboards & BI", "LLM apps & RAG", "Web app", "ML modelling", "Data engineering"]
    skills = ["Celery", "dbt", "Pinecone", "React", "Power BI", "FastAPI", "XGBoost", "spaCy"]
    T = []
    for i in range(n):
        k = i % 10
        if k == 0:
            s = rng.choice(skills); T.append({"task": f"Have I ever used {s} in a past project? Find proof in my portfolio.", "tool": "search_evidence", "args": {"requirement": s.lower()}, "server": "portfolio"})
        elif k == 1:
            c = f"cs-ai_ml-p{rng.randint(1, 20):02d}"; T.append({"task": f"Open case study {c} and show me the whole thing.", "tool": "get_case_study", "args": {"id": c}, "server": "portfolio"})
        elif k == 2:
            T.append({"task": "Which skills can my portfolio actually prove?", "tool": "list_skills", "args": {}, "server": "portfolio"})
        elif k == 3:
            q = rng.choice(["dashboard", "react", "churn", "chatbot"]); T.append({"task": f"Find open jobs about {q}.", "tool": "search_jobs", "args": {"query": q}, "server": "marketplace"})
        elif k == 4:
            j = rng.choice(jids); T.append({"task": f"Show me the full post for job {j}.", "tool": "get_job", "args": {"job_id": j}, "server": "marketplace"})
        elif k == 5:
            c = rng.choice(cids); T.append({"task": f"Is client {c} trustworthy? Check their record.", "tool": "get_client_history", "args": {"client_id": c}, "server": "marketplace"})
        elif k == 6:
            T.append({"task": "How many Connects do I have left?", "tool": "get_connects_balance", "args": {}, "server": "marketplace"})
        elif k == 7:
            c = rng.choice(cats); T.append({"task": f"What do jobs in '{c}' usually pay?", "tool": "get_market_stats", "args": {"category": c}, "server": "marketplace"})
        elif k == 8:
            t = f"gt-{rng.randint(1000, 9999)}"; T.append({"task": f"Read the conversation in thread {t}.", "tool": "list_messages", "args": {"thread_id": t}, "server": "marketplace"})
        else:
            d = rng.choice([3, 5, 7]); T.append({"task": f"When am I free for a 30-minute interview in the next {d} days?", "tool": "free_slots", "args": {"days": d}, "server": "workspace"})
    return T


async def fine_tools(rewrite: bool) -> list[dict]:
    from mcp.shared.memory import create_connected_server_and_client_session

    from mcp_servers.marketplace.server import mcp as m
    from mcp_servers.portfolio.server import mcp as p
    from mcp_servers.workspace.server import mcp as w
    out = []
    for srv in (p, m, w):
        async with create_connected_server_and_client_session(srv) as s:
            for t in (await s.list_tools()).tools:
                desc = REWRITE.get(t.name, t.description) if rewrite else t.description
                out.append({"type": "function", "function": {"name": t.name, "description": desc or "", "parameters": t.inputSchema}})
    return out


def coarse_tools() -> list[dict]:
    def one(name, actions, desc):
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
            "type": "object", "required": ["action"], "properties": {"action": {"type": "string", "enum": actions},
                                                                        "params": {"type": "object", "description": "arguments for the action"}}}}}
    return [one("portfolio", ["search_evidence", "get_case_study", "list_skills"], "Freelancer portfolio: evidence search, case studies, skills."),
            one("marketplace", ["search_jobs", "get_job", "get_client_history", "get_connects_balance", "get_market_stats", "list_messages"],
                "Marketplace: jobs, clients, Connects, prices, messages."),
            one("workspace", ["free_slots"], "Calendar: free interview slots.")]


def arg_ok(expected: dict, got: dict) -> bool:
    for k, v in expected.items():
        g = got.get(k)
        if isinstance(v, str):
            if not isinstance(g, str) or v.lower() not in g.lower():
                return False
        elif g != v and str(g) != str(v):
            return False
    return True


def ask(model: str, tools: list[dict], task: str) -> tuple[str | None, dict, int]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    r = httpx.post(base + "/chat/completions", timeout=300, json={
        "model": model, "temperature": 0, "tools": tools, "messages": [
            {"role": "system", "content": "Call exactly ONE tool with correct arguments for the user's request."},
            {"role": "user", "content": task}]}).json()
    msg = r["choices"][0]["message"]
    calls = msg.get("tool_calls") or []
    tok = (r.get("usage") or {}).get("prompt_tokens", 0) + (r.get("usage") or {}).get("completion_tokens", 0)
    if not calls:
        return None, {}, tok
    fn = calls[0]["function"]
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return fn["name"], args, tok


async def run(model: str, n: int) -> dict:
    T = tasks(n)
    designs = {"fine_grained": await fine_tools(False), "coarse": coarse_tools(), "fine_rewritten": await fine_tools(True)}
    out = {"model": model, "n_tasks": len(T), "designs": {}}
    for name, tools in designs.items():
        sel = argc = tok = 0
        rows = []
        for t in T:
            tool, args, k = await asyncio.to_thread(ask, model, tools, t["task"])
            if name == "coarse":
                ok_sel = tool == t["server"] and args.get("action") == t["tool"]
                ok_arg = ok_sel and arg_ok(t["args"], args.get("params") or {})
            else:
                ok_sel = tool == t["tool"]
                ok_arg = ok_sel and arg_ok(t["args"], args)
            sel += ok_sel
            argc += ok_arg
            tok += k
            rows.append({"task": t["task"], "expected": t["tool"], "got": tool, "args": args, "selection_ok": ok_sel, "args_ok": ok_arg})
        out["designs"][name] = {"selection_accuracy": round(sel / len(T), 4), "argument_accuracy": round(argc / len(T), 4),
                                "tokens_per_task": round(tok / len(T), 1), "n_tools": len(tools), "rows": rows}
        print(name, out["designs"][name]["selection_accuracy"], out["designs"][name]["argument_accuracy"],
              out["designs"][name]["tokens_per_task"], flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2")
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()
    os.environ.setdefault("GIGBID_LOCAL_SQLITE", "1")
    write_result("tool_study", asyncio.run(run(a.model, a.n)))


if __name__ == "__main__":
    main()
