"""Graph runs against a live in-process GigSim through the real MCP servers (fake LLM: heuristics only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent import approval_token
from agent.persistence import open_persistence
from agent.runner import Graphs, history, replay, resume, start_bid

ROOT = Path(__file__).resolve().parents[2]
USER = "u-int"


def dev_rows(persona="ai_ml"):
    return [json.loads(x) for x in (ROOT / "evals" / "datasets" / f"dev_{persona}.jsonl").read_text().splitlines() if x]


async def balance():
    from agent import mcp_client
    mcp_client.RUN_CTX.set({"user_id": USER, "persona": "ai_ml", "trace_id": "t"})
    return (await mcp_client.call("__all__", "get_connects_balance", {}))["connects_balance"]


def approve_decision(interrupt: dict) -> dict:
    return {"action": "approve", "user_id": USER,
            "approval_token": approval_token.mint(USER, "proposal", interrupt["send_payload"])}


async def first_job_reaching_approval(graphs, limit=25):
    for r in [r for r in dev_rows() if r["gold_bid"] and r["kind"] in ("normal", "vague")][:limit]:
        out = await start_bid(graphs, r["job_id"], USER, "ai_ml")
        if out["interrupt"]:
            return r, out
    pytest.fail("no dev job reached human approval")


async def test_scam_is_skipped(gigsim):
    scam = next(r for r in dev_rows() if r["gold_scam"])
    async with open_persistence() as (cp, st):
        out = await start_bid(Graphs(cp, st), scam["job_id"], USER, "ai_ml")
    v = out["values"]
    assert out["interrupt"] is None
    assert v["status"] == "skipped" and v["decision"]["action"] == "skip"
    assert v["risk"]["scam"] is True
    assert any(e.get("type") == "node" and e["node"] == "risk_assessor" for e in v["trace"])


async def test_approval_crash_resume_exactly_once(gigsim):
    async with open_persistence() as (cp, st):
        row, out = await first_job_reaching_approval(Graphs(cp, st))
    req = out["interrupt"]
    assert req["kind"] == "proposal" and req["preview"]["connects_cost"] > 0
    assert req["send_payload"]["cover_letter"] and "[E:" not in req["send_payload"]["cover_letter"]
    assert all(c["status"] in ("supported", "partial", "unsupported") for c in req["claims"])
    thread = out["thread_id"]
    before = await balance()
    # "crash": the first persistence context is gone; a fresh process re-opens the same checkpoint DB
    async with open_persistence() as (cp, st):
        g2 = Graphs(cp, st)
        done = await resume(g2, "bid", thread, approve_decision(req), USER, "ai_ml")
        sub = done["values"]["submission"]
        assert done["values"]["status"] == "submitted" and sub["status"] == "submitted"
        mid = await balance()
        assert before - mid == req["preview"]["connects_cost"]
        # replay from the checkpoint just before the executor: idempotency keys make it a no-op on the marketplace
        hist = await history(g2, "bid", thread)
        cp_exec = next(h for h in hist if h["next"] == ["executor"])
        again = await replay(g2, "bid", thread, cp_exec["checkpoint_id"], USER, "ai_ml")
        assert again["values"]["submission"]["idempotent_replay"] is True
    assert await balance() == mid


async def test_edit_is_rechecked_by_compliance(gigsim):
    async with open_persistence() as (cp, st):
        g = Graphs(cp, st)
        rows = [r for r in dev_rows() if r["gold_bid"] and r["kind"] == "normal"]
        out = None
        for r in rows[10:40]:
            o = await start_bid(g, r["job_id"], USER + "-edit", "ai_ml", thread_id=f"{USER}-edit:bid:{r['job_id']}")
            if o["interrupt"]:
                out = o
                break
        assert out, "no job reached approval"
        edited = out["interrupt"]["send_payload"]["cover_letter"] + " Email me at someone@example.com, results guaranteed."
        o2 = await resume(g, "bid", out["thread_id"], {"action": "edit", "edited_text": edited, "user_id": USER}, USER + "-edit", "ai_ml")
    req2 = o2["interrupt"]
    assert req2, "edit must return to human approval"
    assert "@" not in req2["send_payload"]["cover_letter"] and "guaranteed" not in req2["send_payload"]["cover_letter"].lower()
    assert any(r["rule_id"] == "off_platform_contact" for r in req2["compliance"]["redactions"])
