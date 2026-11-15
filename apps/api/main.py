"""GigBid API (FastAPI). Serves the built React app too, so one container is enough to deploy.

    uvicorn apps.api.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent.guardrails import mask_pii
from apps.api import services
from apps.api.db import User, UserSettings, init_db, session
from apps.api.routers import analytics, approvals, auth, jobs, messages, runs
from apps.api.security import current_user, hash_pw

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "dist"


class MaskPII(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_pii(str(record.msg))
        if record.args:
            record.args = tuple(mask_pii(str(a)) for a in record.args) if isinstance(record.args, tuple) else record.args
        return True


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    for h in logging.getLogger().handlers:
        h.addFilter(MaskPII())
    logging.getLogger("httpx").setLevel(logging.WARNING)


def setup_tracing() -> None:
    """Arize Phoenix (OpenTelemetry). One trace per run; tokens/cost per node come from the LangChain spans."""
    if not os.getenv("PHOENIX_COLLECTOR_ENDPOINT"):
        return
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from phoenix.otel import register
    LangChainInstrumentor().instrument(tracer_provider=register(project_name="gigbid", auto_instrument=False))


def seed_reviewer() -> None:
    """Reviewer login preloaded with a persona (credentials come from env, never from the repo)."""
    email, pw = os.getenv("REVIEWER_EMAIL"), os.getenv("REVIEWER_PASSWORD")
    if not email or not pw:
        return
    from apps.api.auth import token_store
    from apps.api.db import SavedSearch
    with session() as s:
        if s.get(User, "u-reviewer"):
            return
        s.add(User(id="u-reviewer", email=email.lower(), password_hash=hash_pw(pw), display_name="Reviewer",
                   persona=os.getenv("REVIEWER_PERSONA", "ai_ml"), onboarded=True))
        s.add(UserSettings(user_id="u-reviewer", hourly_floor=32, min_project=120))
        for q in ("model", "llm", "data", "api"):
            s.add(SavedSearch(user_id="u-reviewer", query=q))
    token_store.put("u-reviewer", "gigsim", {"token": f"gigsim-dev-token-{os.getenv('REVIEWER_PERSONA', 'ai_ml')}"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    setup_tracing()
    init_db()
    seed_reviewer()
    from agent.persistence import open_persistence
    from agent.runner import Graphs
    async with open_persistence() as (cp, st):
        services.GRAPHS = Graphs(cp, st)
        warm = asyncio.create_task(asyncio.to_thread(warm_indexes))  # first user request must not build indexes
        yield
        warm.cancel()


def warm_indexes() -> None:
    """Build each persona's retrieval index and load the models once, in the background, at startup."""
    try:
        from rag.retriever import get_pipeline
        from rag.index.reranker import get_reranker
        get_reranker().score("warm-up", ["warm-up"])
        for p in os.getenv("WARM_PERSONAS", "ai_ml,fullstack,data").split(","):
            if p:
                get_pipeline(p.strip())
        logging.getLogger("gigbid").info("retrieval indexes warm")
    except Exception as e:  # noqa: BLE001 - warm-up is best effort
        logging.getLogger("gigbid").warning("warm-up failed: %s", e)


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, jobs.router, approvals.router, messages.router, runs.router, analytics.router):
    app.include_router(r, prefix="/api")

_status_cache: dict = {"t": 0, "v": None}


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "gigbid-api"}


@app.get("/api/status")
async def status(u: User = Depends(current_user)) -> dict:
    """Degraded-mode signal for the UI banner: is the marketplace MCP server (and GigSim behind it) reachable?"""
    if time.time() - _status_cache["t"] < 5 and _status_cache["v"]:
        return _status_cache["v"]
    from agent import mcp_client
    mcp_client.RUN_CTX.set({"trace_id": "status", "user_id": u.id, "persona": u.persona})
    try:
        bal = await mcp_client.call("api_reader", "get_connects_balance", {}, retries=1)
        v = {"marketplace": "ok", "connects_balance": bal.get("connects_balance"), "policy_version": bal.get("policy_version")}
    except Exception as e:  # noqa: BLE001
        v = {"marketplace": "unavailable", "detail": str(e)[:200]}
    from sqlalchemy import func, select

    from apps.api.db import InboxJob
    with session() as s:
        v["queued_jobs"] = s.execute(select(func.count()).select_from(InboxJob).where(
            InboxJob.user_id == u.id, InboxJob.status.in_(["queued", "queued_retry"]))).scalar()
    _status_cache.update(t=time.time(), v=v)
    return v


if os.getenv("GIGBID_DEV") == "1":
    @app.post("/api/dev/marketplace/{state}", include_in_schema=False)
    def dev_marketplace(state: str) -> dict:
        """Dev/test only: simulate the marketplace going down (degraded-mode demo and Playwright)."""
        from agent import config as cfg
        os.environ["GIGSIM_BASE_URL"] = "http://127.0.0.1:1" if state == "down" else os.getenv("GIGSIM_REAL_URL", "http://127.0.0.1:8081")
        cfg.reload()
        _status_cache.update(t=0, v=None)
        return {"marketplace": state}


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        f = WEB / path
        return FileResponse(f if path and f.is_file() else WEB / "index.html")
