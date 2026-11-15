"""Schema snapshot test (A7): fails CI when any MCP tool signature changes unintentionally.

Intentional change? Re-generate with:  UPDATE_SNAPSHOTS=1 pytest tests/contract
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

SNAP = Path(__file__).parent / "snapshots"


def _servers():
    from mcp_servers.marketplace.server import mcp as m
    from mcp_servers.portfolio.server import mcp as p
    from mcp_servers.workspace.server import mcp as w
    return {"portfolio": p, "marketplace": m, "workspace": w}


@pytest.mark.parametrize("name", ["portfolio", "marketplace", "workspace"])
async def test_tool_schema_snapshot(name):
    async with create_connected_server_and_client_session(_servers()[name]) as c:
        tools = (await c.list_tools()).tools
    current = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                        "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
               for t in sorted(tools, key=lambda t: t.name)}
    path = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAP.mkdir(exist_ok=True)
        path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        if os.getenv("CI"):
            pytest.fail(f"snapshot {path.name} was missing in CI")
        return
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert current == expected, f"{name} tool schemas changed; if intentional run UPDATE_SNAPSHOTS=1 pytest tests/contract"
