"""Durable checkpointer + long-term store (C6). Postgres when DATABASE_URL is postgres, SQLite otherwise."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pg_url() -> str | None:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql") and os.getenv("GIGBID_LOCAL_SQLITE") != "1":
        return url.replace("postgresql+psycopg://", "postgresql://")
    return None


@asynccontextmanager
async def open_persistence():
    from agent.memory import store as memory

    pg = _pg_url()
    if pg:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres import AsyncPostgresStore
        async with AsyncPostgresSaver.from_conn_string(pg) as cp, AsyncPostgresStore.from_conn_string(pg) as st:
            await cp.setup()
            await st.setup()
            memory.set_store(st)
            yield cp, st
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.store.sqlite import AsyncSqliteStore
        cp_path = Path(os.getenv("GIGBID_CHECKPOINT_DB", ROOT / "data" / "processed" / "checkpoints.db"))
        st_path = cp_path.with_name(cp_path.stem + "_store.db")
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(cp_path)) as cp, AsyncSqliteStore.from_conn_string(str(st_path)) as st:
            await st.setup()
            memory.set_store(st)
            yield cp, st
