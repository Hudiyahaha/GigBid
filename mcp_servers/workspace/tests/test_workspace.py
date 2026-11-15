"""Workspace MCP server tests through an in-memory MCP client (A7)."""

from __future__ import annotations

import json

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.workspace.server import mcp


def data(res):
    assert not res.isError, res.content[0].text if res.content else res
    return res.structuredContent or json.loads(res.content[0].text)


async def test_slots_hold_and_draft_are_idempotent():
    async with create_connected_server_and_client_session(mcp) as c:
        slots = data(await c.call_tool("free_slots", {"days": 7, "max_slots": 3}))["slots"]
        assert slots
        a = data(await c.call_tool("create_interview_hold", {"start": slots[0], "title": "Interview", "idempotency_key": "hold-0001"}))
        b = data(await c.call_tool("create_interview_hold", {"start": slots[0], "title": "Interview", "idempotency_key": "hold-0001"}))
        assert a["event_id"] == b["event_id"] and b["idempotent_replay"]
        slots2 = data(await c.call_tool("free_slots", {"days": 7, "max_slots": 3}))["slots"]
        assert slots[0] not in slots2
        d = data(await c.call_tool("create_email_draft", {"to_name": "Client", "subject": "Hi", "body": "Draft",
                                                          "idempotency_key": "draft-0001", "dry_run": True}))
        assert d["dry_run"] is True
