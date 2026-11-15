"""Workspace MCP server (A3): free calendar slots, tentative interview holds and email drafts.

Backed by a documented LOCAL MOCK (SQLite) rather than Google Calendar/Gmail, so it runs offline and in CI.
The agent only ever sees these MCP tools; swapping in Google's APIs changes this file only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import AuditLog, request_context, run

ROOT = Path(__file__).resolve().parents[2]
DB = Path(os.getenv("WORKSPACE_DB", ROOT / "data" / "processed" / "workspace.db"))
mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative interview holds and email drafts.")
audit = AuditLog("workspace")
WORK_HOURS = (9, 17)


def _db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, user TEXT, start TEXT, end TEXT, title TEXT, "
                "status TEXT, idem TEXT UNIQUE)")
    con.execute("CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, user TEXT, to_name TEXT, subject TEXT, body TEXT, "
                "idem TEXT UNIQUE, created TEXT)")
    return con


class Slots(BaseModel):
    timezone: str
    slots: list[str]


class Hold(BaseModel):
    event_id: str
    start: str
    end: str
    status: str
    dry_run: bool = False
    idempotent_replay: bool = False


class Draft(BaseModel):
    draft_id: str
    subject: str
    body: str
    dry_run: bool = False


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False),
          description="Free interview slots in working hours (Mon-Fri 09:00-17:00 UTC) over the next N days.")
async def free_slots(days: Annotated[int, Field(ge=1, le=14)] = 5, duration_min: Annotated[int, Field(ge=15, le=120)] = 30,
                     max_slots: Annotated[int, Field(ge=1, le=10)] = 3, ctx: Context = None) -> Slots:
    user = request_context(ctx)["user_id"]
    with _db() as con:
        busy = [(datetime.fromisoformat(s), datetime.fromisoformat(e)) for s, e in
                con.execute("SELECT start, end FROM events WHERE user=? AND status!='cancelled'", (user,))]
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    out = []
    t = now
    while len(out) < max_slots and t < now + timedelta(days=days):
        end = t + timedelta(minutes=duration_min)
        if t.weekday() < 5 and WORK_HOURS[0] <= t.hour < WORK_HOURS[1] and not any(s < end and t < e for s, e in busy):
            out.append(t.isoformat())
            t += timedelta(hours=3)  # spread suggestions out
        else:
            t += timedelta(minutes=30)
    audit.write("free_slots", {"days": days}, {"n": len(out)})
    return Slots(timezone="UTC", slots=out)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=False),
          description="Create a TENTATIVE calendar hold for an interview (not visible to the client).")
async def create_interview_hold(start: Annotated[str, Field(description="ISO 8601 start time")],
                                title: Annotated[str, Field(min_length=3, max_length=200)],
                                idempotency_key: Annotated[str, Field(min_length=8, max_length=128)],
                                duration_min: Annotated[int, Field(ge=15, le=120)] = 30, dry_run: bool = False,
                                ctx: Context = None) -> Hold:
    user = request_context(ctx)["user_id"]
    s = datetime.fromisoformat(start)
    e = s + timedelta(minutes=duration_min)
    if dry_run:
        return Hold(event_id="(dry-run)", start=s.isoformat(), end=e.isoformat(), status="tentative", dry_run=True)
    with _db() as con:
        row = con.execute("SELECT id, start, end, status FROM events WHERE idem=?", (idempotency_key,)).fetchone()
        if row:
            return Hold(event_id=row[0], start=row[1], end=row[2], status=row[3], idempotent_replay=True)
        eid = "ev-" + uuid.uuid4().hex[:8]
        con.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)", (eid, user, s.isoformat(), e.isoformat(), title, "tentative", idempotency_key))
    audit.write("create_interview_hold", {"start": start, "title": title}, {"event_id": eid})
    return Hold(event_id=eid, start=s.isoformat(), end=e.isoformat(), status="tentative")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=False),
          description="Save an email DRAFT in the freelancer's mailbox (never sends).")
async def create_email_draft(to_name: Annotated[str, Field(max_length=200)], subject: Annotated[str, Field(max_length=300)],
                             body: Annotated[str, Field(max_length=6000)],
                             idempotency_key: Annotated[str, Field(min_length=8, max_length=128)], dry_run: bool = False,
                             ctx: Context = None) -> Draft:
    user = request_context(ctx)["user_id"]
    if dry_run:
        return Draft(draft_id="(dry-run)", subject=subject, body=body, dry_run=True)
    with _db() as con:
        row = con.execute("SELECT id FROM drafts WHERE idem=?", (idempotency_key,)).fetchone()
        did = row[0] if row else "dr-" + uuid.uuid4().hex[:8]
        if not row:
            con.execute("INSERT INTO drafts VALUES(?,?,?,?,?,?,?)", (did, user, to_name, subject, body, idempotency_key,
                                                                     datetime.now(UTC).isoformat()))
    audit.write("create_email_draft", {"to_name": to_name, "subject": subject}, {"draft_id": did})
    return Draft(draft_id=did, subject=subject, body=body)


@mcp.resource("workspace://calendar", mime_type="application/json", description="Upcoming holds")
def calendar() -> str:
    with _db() as con:
        return json.dumps([dict(zip(["id", "start", "end", "title", "status"], r, strict=True))
                           for r in con.execute("SELECT id, start, end, title, status FROM events ORDER BY start")])


if __name__ == "__main__":
    run(mcp, 8103, token_env="WORKSPACE_MCP_TOKEN")
