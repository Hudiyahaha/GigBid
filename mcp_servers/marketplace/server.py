"""Marketplace MCP server (A2): wraps GigSim (or live Upwork) behind typed, annotated MCP tools.

    python -m mcp_servers.marketplace.server http     # streamable HTTP on :8102/mcp (bearer: MARKETPLACE_MCP_TOKEN)
    python -m mcp_servers.marketplace.server stdio

Guarantees
  * Pydantic-constrained inputs and declared output schemas; readOnly/destructive/idempotent annotations
  * idempotency_key on every write -> exactly-once ledger (apps/api/db.py:Submission); retries replay the result
  * dry_run on every write returns exactly what would be sent and what it costs
  * non-dry-run writes require an approval token minted by the API when a human approves (agent/approval_token.py)
  * per-user rate limiter below GigSim's limit; append-only hash-chained audit log with trace ids
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent import approval_token as approvals, config
from mcp_servers.common import AuditLog, RateLimiter, request_context, run
from mcp_servers.marketplace.adapters.base import MarketplaceRejected, MarketplaceUnavailable

mcp = FastMCP("gigbid-marketplace", instructions=(
    "Marketplace tools for GigBid. Read tools are safe. Write tools need an idempotency_key; use dry_run=true to "
    "preview. Real writes need an approval_token issued when the human approves in GigBid."))
audit = AuditLog("marketplace")
limiter = RateLimiter(int(config.get("marketplace.gigsim.max_requests_per_minute", 40)))

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITE_DRAFT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITE_SEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

IdemKey = Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9:_\-.]+$",
                               description="Unique key per logical write; retries with the same key never repeat it")]


# ------------------------------------------------------------------ output schemas
class JobList(BaseModel):
    total: int
    tick: int | None = None
    jobs: list[dict[str, Any]]


class Record(BaseModel):
    data: dict[str, Any]


class ConnectsBalance(BaseModel):
    connects_balance: int | None
    submissions_last_24h: int | None = None
    policy_version: Any = None


class Preview(BaseModel):
    operation: str
    target: str
    payload: dict[str, Any]
    connects_cost: int = 0
    connects_balance: int | None = None
    connects_balance_after: int | None = None
    policy_version: Any = None
    warnings: list[str] = Field(default_factory=list)


class WriteResult(BaseModel):
    dry_run: bool
    preview: Preview | None = None
    result: dict[str, Any] | None = None
    idempotent_replay: bool = False


# ------------------------------------------------------------------ backend selection (R1)
def _mode(user_id: str) -> str:
    return os.getenv("MARKETPLACE_MODE") or config.get("marketplace.mode", "gigsim")


def backend(ctx: Context | None):
    rc = request_context(ctx)
    user = rc["user_id"]
    if _mode(user) == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        return UpworkLiveAdapter(user), rc
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
    token = None
    try:
        from apps.api.auth import token_store
        token = (token_store.get(user, "gigsim") or {}).get("token")
    except Exception:  # noqa: BLE001 - token store unavailable (tests); fall back below
        token = None
    if not token and rc.get("persona"):
        token = f"gigsim-dev-token-{rc['persona']}"
    token = token or os.getenv("GIGSIM_TOKEN", "")
    if not token:
        raise ToolError("NOT_CONNECTED: no marketplace account connected for this user")
    return GigSimAdapter(token, trace_id=rc["trace_id"]), rc


async def _guard(ctx, tool: str, args: dict, fn):
    be, rc = backend(ctx)
    await limiter.acquire(rc["user_id"])
    try:
        out = await fn(be)
    except MarketplaceUnavailable as e:
        audit.write(tool, args, {"error": str(e)}, "unavailable")
        raise ToolError(f"MARKETPLACE_UNAVAILABLE: {e}") from e
    except MarketplaceRejected as e:
        audit.write(tool, args, {"error": e.detail, "status": e.status}, "rejected")
        raise ToolError(f"MARKETPLACE_REJECTED({e.status}): {e.detail}") from e
    audit.write(tool, args, out if tool.startswith(("create", "submit", "send")) else {"ok": True}, "ok")
    return out


# ------------------------------------------------------------------ read tools
@mcp.tool(annotations=READ, description="Search open jobs by keywords. Returns newest first.")
async def search_jobs(query: Annotated[str, Field(max_length=200)] = "",
                      limit: Annotated[int, Field(ge=1, le=50)] = 20,
                      since_tick: Annotated[int, Field(ge=0)] = 0,
                      category: Annotated[str | None, Field(max_length=64)] = None, ctx: Context = None) -> JobList:
    out = await _guard(ctx, "search_jobs", {"query": query, "limit": limit}, lambda b: b.search_jobs(query, limit, since_tick, category))
    return JobList(total=out.get("total", 0), tick=out.get("tick"), jobs=out.get("jobs", []))


@mcp.tool(annotations=READ, description="Get one job post by id (title, description, budget, screening questions, client id).")
async def get_job(job_id: Annotated[str, Field(min_length=1, max_length=64)], ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "get_job", {"job_id": job_id}, lambda b: b.get_job(job_id)))


@mcp.tool(annotations=READ, description="Client track record: payment verified, spend, hires, hire rate, ratings, past jobs.")
async def get_client_history(client_id: Annotated[str, Field(min_length=1, max_length=64)], ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "get_client_history", {"client_id": client_id}, lambda b: b.get_client_history(client_id)))


@mcp.tool(annotations=READ, description="The freelancer's current Connects balance and submissions in the last 24h.")
async def get_connects_balance(ctx: Context = None) -> ConnectsBalance:
    out = await _guard(ctx, "get_connects_balance", {}, lambda b: b.get_connects_balance())
    return ConnectsBalance(connects_balance=out.get("connects_balance"), submissions_last_24h=out.get("submissions_last_24h"),
                           policy_version=out.get("policy_version"))


@mcp.tool(annotations=READ, description="Price statistics (p25/p50/p75/p90 of final prices) of closed jobs, by category or domain.")
async def get_market_stats(category: Annotated[str | None, Field(max_length=64)] = None,
                           domain: Annotated[str | None, Field(max_length=32)] = None,
                           pay_type: Literal["fixed", "hourly"] | None = None, ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "get_market_stats", {"category": category, "pay_type": pay_type},
                                    lambda b: b.get_market_stats(category, domain, pay_type)))


@mcp.tool(annotations=READ, description="Current platform policy: rules, Connects surcharges and submission limits.")
async def get_policy(ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "get_policy", {}, lambda b: b.get_policy()))


@mcp.tool(annotations=READ, description="List client conversation threads.")
async def list_threads(ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "list_threads", {}, lambda b: b.list_threads()))


@mcp.tool(annotations=READ, description="List the messages in one conversation thread (oldest first).")
async def list_messages(thread_id: Annotated[str, Field(min_length=1, max_length=64)], ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "list_messages", {"thread_id": thread_id}, lambda b: b.list_messages(thread_id)))


@mcp.tool(annotations=READ, description="List this freelancer's proposals and their pipeline status.")
async def list_proposals(ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "list_proposals", {}, lambda b: b.list_proposals()))


@mcp.tool(annotations=READ, description="Marketplace events (proposal viewed/replied/interview/hired/lost) after a sequence number.")
async def list_events(after: Annotated[int, Field(ge=0)] = 0, ctx: Context = None) -> Record:
    return Record(data=await _guard(ctx, "list_events", {"after": after}, lambda b: b.list_events(after)))


# ------------------------------------------------------------------ write helpers
def _ledger_get(key: str) -> dict | None:
    try:
        from apps.api.db import Submission, session
        with session() as s:
            row = s.get(Submission, key)
            return dict(row.result) if row else None
    except Exception:  # noqa: BLE001
        return None


def _ledger_put(key: str, user: str, op: str, result: dict) -> None:
    from apps.api.db import Submission, session
    with session() as s:
        if not s.get(Submission, key):
            s.add(Submission(idempotency_key=key, user_id=user, operation=op, result=result))


async def _cost_preview(b, job_id: str) -> tuple[int, int | None, Any, list[str]]:
    job = await b.get_job(job_id)
    pol = await b.get_policy()
    cost = int(job.get("connects_cost", 0))
    warnings = []
    surcharge = int((pol.get("connects") or {}).get("surcharge_unverified_client", 0) or 0)
    if surcharge and job.get("client_id"):
        client = await b.get_client_history(job["client_id"])
        if not client.get("payment_verified", True):
            cost += surcharge
            warnings.append(f"+{surcharge} Connects: client payment not verified (policy v{pol.get('version')})")
    bal = (await b.get_connects_balance()).get("connects_balance")
    return cost, bal, pol.get("version"), warnings


# ------------------------------------------------------------------ write tools
@mcp.tool(annotations=WRITE_DRAFT, description=(
    "Create a proposal DRAFT on the marketplace (spends no Connects). dry_run=true returns the exact payload and cost. "
    "A real call needs approval_token from a human approval in GigBid."))
async def create_proposal_draft(
        job_id: Annotated[str, Field(min_length=1, max_length=64)],
        cover_letter: Annotated[str, Field(min_length=50, max_length=5000)],
        bid_amount: Annotated[float, Field(gt=0, le=100000)],
        pay_type: Literal["fixed", "hourly"],
        idempotency_key: IdemKey,
        screening_answers: Annotated[list[Annotated[str, Field(max_length=2000)]], Field(max_length=10)] = [],  # noqa: B006
        dry_run: bool = False,
        approval_token: str | None = None,
        ctx: Context = None) -> WriteResult:
    payload = {"job_id": job_id, "cover_letter": cover_letter, "screening_answers": list(screening_answers),
               "bid_amount": bid_amount, "pay_type": pay_type}
    be, rc = backend(ctx)
    if dry_run:
        async def prev(b):
            cost, bal, ver, warns = await _cost_preview(b, job_id)
            return Preview(operation="create_proposal_draft + submit_proposal", target=be.name, payload=payload,
                           connects_cost=cost, connects_balance=bal, connects_balance_after=(bal - cost) if bal is not None else None,
                           policy_version=ver, warnings=warns).model_dump()
        return WriteResult(dry_run=True, preview=Preview(**await _guard(ctx, "create_proposal_draft[dry_run]", payload, prev)))
    replay = _ledger_get(idempotency_key)
    if replay is not None:
        return WriteResult(dry_run=False, result=replay, idempotent_replay=True)
    ok, why = approvals.verify(approval_token, rc["user_id"], "proposal", payload)
    if not ok:
        audit.write("create_proposal_draft", payload, {"error": why}, "denied")
        raise ToolError(f"APPROVAL_REQUIRED: {why}")
    out = await _guard(ctx, "create_proposal_draft", payload, lambda b: b.create_proposal_draft(payload, idempotency_key))
    out["_payload"] = payload
    _ledger_put(idempotency_key, rc["user_id"], "create_proposal_draft", out)
    return WriteResult(dry_run=False, result=out)


@mcp.tool(annotations=WRITE_SEND, description=(
    "Submit a drafted proposal (spends Connects, irreversible). Needs the same approval_token as the draft. "
    "Idempotent per idempotency_key."))
async def submit_proposal(proposal_id: Annotated[str, Field(min_length=1, max_length=64)],
                          draft_idempotency_key: IdemKey, idempotency_key: IdemKey, dry_run: bool = False,
                          approval_token: str | None = None,
                          ctx: Context = None) -> WriteResult:
    be, rc = backend(ctx)
    draft = _ledger_get(draft_idempotency_key)
    if not draft or draft.get("proposal_id") != proposal_id:
        raise ToolError("UNKNOWN_DRAFT: submit only drafts created through create_proposal_draft")
    payload = draft["_payload"]
    if dry_run:
        async def prev(b):
            cost, bal, ver, warns = await _cost_preview(b, payload["job_id"])
            return Preview(operation="submit_proposal", target=be.name, payload={"proposal_id": proposal_id, **payload},
                           connects_cost=cost, connects_balance=bal,
                           connects_balance_after=(bal - cost) if bal is not None else None, policy_version=ver,
                           warnings=warns).model_dump()
        return WriteResult(dry_run=True, preview=Preview(**await _guard(ctx, "submit_proposal[dry_run]", {"proposal_id": proposal_id}, prev)))
    replay = _ledger_get(idempotency_key)
    if replay is not None:
        return WriteResult(dry_run=False, result=replay, idempotent_replay=True)
    ok, why = approvals.verify(approval_token, rc["user_id"], "proposal", payload)
    if not ok:
        audit.write("submit_proposal", {"proposal_id": proposal_id}, {"error": why}, "denied")
        raise ToolError(f"APPROVAL_REQUIRED: {why}")
    out = await _guard(ctx, "submit_proposal", {"proposal_id": proposal_id}, lambda b: b.submit_proposal(proposal_id, idempotency_key))
    _ledger_put(idempotency_key, rc["user_id"], "submit_proposal", out)
    return WriteResult(dry_run=False, result=out)


@mcp.tool(annotations=WRITE_SEND, description=(
    "Send a message to a client thread. dry_run=true previews it. A real call needs approval_token from GigBid."))
async def send_message(thread_id: Annotated[str, Field(min_length=1, max_length=64)],
                       body: Annotated[str, Field(min_length=1, max_length=4000)], idempotency_key: IdemKey,
                       dry_run: bool = False,
                       approval_token: str | None = None,
                       ctx: Context = None) -> WriteResult:
    payload = {"thread_id": thread_id, "body": body}
    be, rc = backend(ctx)
    if dry_run:
        return WriteResult(dry_run=True, preview=Preview(operation="send_message", target=be.name, payload=payload))
    replay = _ledger_get(idempotency_key)
    if replay is not None:
        return WriteResult(dry_run=False, result=replay, idempotent_replay=True)
    ok, why = approvals.verify(approval_token, rc["user_id"], "message", payload)
    if not ok:
        audit.write("send_message", payload, {"error": why}, "denied")
        raise ToolError(f"APPROVAL_REQUIRED: {why}")
    out = await _guard(ctx, "send_message", payload, lambda b: b.send_message(thread_id, body, idempotency_key))
    _ledger_put(idempotency_key, rc["user_id"], "send_message", out)
    return WriteResult(dry_run=False, result=out)


if __name__ == "__main__":
    run(mcp, 8102, token_env="MARKETPLACE_MCP_TOKEN")
