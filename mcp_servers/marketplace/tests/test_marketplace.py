"""Marketplace MCP server tests through an in-memory MCP client (A7)."""

from __future__ import annotations

import json
import os

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from agent import approval_token
from mcp_servers.marketplace.server import mcp

JOB = "dev-ai_ml-001"
LETTER = ("Your project matches the support-ticket triage agent I built for an education client, where I modelled the "
          "agent as a stateful graph with checkpoints. Happy to walk you through it.")


def payload(**kw):
    p = {"job_id": JOB, "cover_letter": LETTER, "screening_answers": [], "bid_amount": 900.0, "pay_type": "fixed"}
    p.update(kw)
    return p


def data(res):
    assert not res.isError, res.content[0].text if res.content else res
    return res.structuredContent or json.loads(res.content[0].text)


@pytest.fixture(autouse=True)
def _persona(monkeypatch):
    monkeypatch.setenv("GIGBID_USER", "u-test")
    monkeypatch.setenv("PORTFOLIO_PERSONA", "ai_ml")


async def test_tools_have_annotations(gigsim):
    async with create_connected_server_and_client_session(mcp) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert {"search_jobs", "get_job", "get_client_history", "get_connects_balance", "list_messages",
            "create_proposal_draft", "submit_proposal", "send_message"} <= set(tools)
    assert tools["search_jobs"].annotations.readOnlyHint is True
    assert tools["submit_proposal"].annotations.destructiveHint is True
    assert tools["create_proposal_draft"].annotations.idempotentHint is True
    assert tools["create_proposal_draft"].outputSchema is not None
    assert "idempotency_key" in tools["submit_proposal"].inputSchema["required"]


async def test_read_tools(gigsim):
    async with create_connected_server_and_client_session(mcp) as c:
        jobs = data(await c.call_tool("search_jobs", {"query": "model", "limit": 5}))
        assert jobs["jobs"] and len(jobs["jobs"]) <= 5
        job = data(await c.call_tool("get_job", {"job_id": JOB}))["data"]
        assert job["job_id"] == JOB
        client = data(await c.call_tool("get_client_history", {"client_id": job["client_id"]}))["data"]
        assert "hire_rate" in client
        bal = data(await c.call_tool("get_connects_balance", {}))
        assert bal["connects_balance"] >= 0


async def test_dry_run_previews_cost_and_sends_nothing(gigsim):
    async with create_connected_server_and_client_session(mcp) as c:
        before = data(await c.call_tool("get_connects_balance", {}))["connects_balance"]
        res = data(await c.call_tool("create_proposal_draft", {**payload(), "idempotency_key": "dry-0001", "dry_run": True}))
        after = data(await c.call_tool("get_connects_balance", {}))["connects_balance"]
    assert res["dry_run"] is True
    assert res["preview"]["connects_cost"] > 0
    assert res["preview"]["connects_balance_after"] == before - res["preview"]["connects_cost"]
    assert before == after


async def test_write_requires_human_approval(gigsim):
    async with create_connected_server_and_client_session(mcp) as c:
        res = await c.call_tool("create_proposal_draft", {**payload(), "idempotency_key": "noapproval-1"})
    assert res.isError and "APPROVAL_REQUIRED" in res.content[0].text


async def test_tampered_payload_rejected(gigsim):
    tok = approval_token.mint("u-test", "proposal", payload())
    async with create_connected_server_and_client_session(mcp) as c:
        res = await c.call_tool("create_proposal_draft", {**payload(bid_amount=5.0), "idempotency_key": "tamper-001",
                                                          "approval_token": tok})
    assert res.isError and "payload changed" in res.content[0].text


async def test_submit_exactly_once(gigsim):
    p = payload(job_id="dev-ai_ml-002")
    tok = approval_token.mint("u-test", "proposal", p)
    async with create_connected_server_and_client_session(mcp) as c:
        before = data(await c.call_tool("get_connects_balance", {}))["connects_balance"]
        d1 = data(await c.call_tool("create_proposal_draft", {**p, "idempotency_key": "draft-key-01", "approval_token": tok}))
        d2 = data(await c.call_tool("create_proposal_draft", {**p, "idempotency_key": "draft-key-01", "approval_token": tok}))
        assert d2["idempotent_replay"] and d1["result"]["proposal_id"] == d2["result"]["proposal_id"]
        args = {"proposal_id": d1["result"]["proposal_id"], "draft_idempotency_key": "draft-key-01",
                "idempotency_key": "submit-key-01", "approval_token": tok}
        s1 = data(await c.call_tool("submit_proposal", args))
        s2 = data(await c.call_tool("submit_proposal", args))  # retried call (e.g. worker crash) -> no second spend
        after = data(await c.call_tool("get_connects_balance", {}))["connects_balance"]
    assert s1["result"]["status"] == "submitted"
    assert s2["idempotent_replay"] is True
    assert before - after == s1["result"]["connects_spent"]


async def test_unavailable_marketplace_is_reported(monkeypatch, gigsim):
    monkeypatch.setenv("GIGSIM_BASE_URL", "http://127.0.0.1:1")
    from agent import config
    config.reload()
    try:
        async with create_connected_server_and_client_session(mcp) as c:
            res = await c.call_tool("get_job", {"job_id": JOB})
        assert res.isError and "MARKETPLACE_UNAVAILABLE" in res.content[0].text
    finally:
        monkeypatch.setenv("GIGSIM_BASE_URL", gigsim)
        config.reload()


def test_audit_log_is_hash_chained(gigsim):
    from mcp_servers.common import AuditLog
    log = AuditLog("marketplace")
    if not log.path.exists():
        pytest.skip("no audit records yet")
    ok, n = log.verify()
    assert ok and n > 0
    os.environ.setdefault("X", "1")
