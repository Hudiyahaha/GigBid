"""Portfolio MCP server tests through an in-memory MCP client (A7)."""

from __future__ import annotations

import json

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.portfolio.server import mcp


def data(res):
    assert not res.isError, res.content[0].text if res.content else res
    return res.structuredContent or json.loads(res.content[0].text)


async def test_search_evidence_returns_typed_items():
    async with create_connected_server_and_client_session(mcp) as c:
        out = data(await c.call_tool("search_evidence", {"requirement": "background task queue with retries", "k": 5}))
    assert out["items"] and len(out["items"]) <= 5
    it = out["items"][0]
    assert {"item_id", "type", "source", "date"} <= set(it)
    assert it["type"] in {"case_study", "repo", "review", "cv"}


async def test_get_case_study_and_skills():
    async with create_connected_server_and_client_session(mcp) as c:
        cs = data(await c.call_tool("get_case_study", {"id": "cs-ai_ml-p01"}))
        skills = data(await c.call_tool("list_skills", {}))
        missing = await c.call_tool("get_case_study", {"id": "cs-does-not-exist"})
    assert cs["item_id"] == "cs-ai_ml-p01" and cs["text"]
    assert skills["skills"] and "skill" in skills["skills"][0]
    assert missing.isError


async def test_resources_and_prompts():
    async with create_connected_server_and_client_session(mcp) as c:
        templates = [t.uriTemplate for t in (await c.list_resource_templates()).resourceTemplates]
        prompts = [p.name for p in (await c.list_prompts()).prompts]
        res = await c.read_resource("portfolio://case/cs-ai_ml-p01")
    assert "portfolio://case/{id}" in templates and "portfolio://proposal/{id}" in templates
    assert "answer_screening_question" in prompts
    assert "#" in res.contents[0].text
