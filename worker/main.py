"""Background worker (E1): scheduled scouting, long agent runs and marketplace event sync, on Arq + Redis.

    arq worker.main.WorkerSettings          # docker / production
    python -m worker.main --local           # no Redis: same jobs on an asyncio loop

Idempotency: Arq job ids are derived from (user, job) so a job is never enqueued twice; bid threads are keyed by
(user, job) and resume from their checkpoint after a restart; marketplace writes carry idempotency keys.
Live mode scouts at most every marketplace.upwork_live.scout_interval_minutes (justified in docs/RUNBOOK.md).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from sqlalchemy import select

from agent import config, runner
from apps.api import services
from apps.api.db import InboxJob, SavedSearch, User, init_db, session

log = logging.getLogger("gigbid.worker")


def interval_minutes() -> int:
    mode = os.getenv("MARKETPLACE_MODE") or config.get("marketplace.mode", "gigsim")
    if mode == "upwork_live":
        return int(config.get("marketplace.upwork_live.scout_interval_minutes", 240))
    return int(config.get("worker.scout_interval_minutes_gigsim", 5))


async def scout_all(ctx: dict | None = None) -> dict:
    """Scout every onboarded user whose saved searches are due, then analyse a few new jobs each (polite)."""
    due = interval_minutes() * 60
    out = {}
    with session() as s:
        users = s.execute(select(User).where(User.onboarded.is_(True))).scalars().all()
    for u in users:
        with session() as s:
            last = max([x.last_run for x in s.execute(select(SavedSearch).where(SavedSearch.user_id == u.id)).scalars()] or [0])
        if time.time() - last < due:
            continue
        try:
            res = await services.scout_user(u)
        except Exception as e:  # noqa: BLE001 - marketplace down: try next cycle (degraded mode)
            log.warning("scout failed for %s: %s", u.id, type(e).__name__)
            continue
        out[u.id] = res
        for jid in res["queued"][:5]:
            await analyse(ctx, u.id, jid)
    return out


async def analyse(ctx: dict | None, user_id: str, job_id: str) -> str | None:
    """Run (or resume) the bid graph for one job. Safe to call twice: a finished or waiting thread is not re-run."""
    with session() as s:
        u = s.get(User, user_id)
        row = s.execute(select(InboxJob).where(InboxJob.user_id == user_id, InboxJob.job_id == job_id)).scalar_one_or_none()
    if row and row.status not in ("queued", "queued_retry"):
        return None
    thread = f"{user_id}:bid:{job_id}"
    snap = await services.GRAPHS.bid.aget_state(runner.cfg(thread))
    waiting = any(t.interrupts for t in snap.tasks)
    if snap.values and snap.next and not waiting:  # crashed mid-run: continue from the last checkpoint
        rid = services.new_run(user_id, "bid", thread, job_id)

        async def go(emit):
            return await runner.continue_thread(services.GRAPHS, "bid", thread, user_id, u.persona, emit)
        await services._run(rid, u, "bid", job_id, go)
        return rid
    if snap.values:
        return None
    rid = services.start_bid(u, job_id)
    while any(not t.done() for t in services.TASKS):
        await asyncio.sleep(0.5)
    return rid


async def retry_queued(ctx: dict | None = None) -> int:
    """Degraded-mode recovery: a thread that stopped with 'marketplace unavailable' is replayed from its last
    good checkpoint once the marketplace answers again (idempotency keys keep writes exactly-once)."""
    with session() as s:
        rows = s.execute(select(InboxJob).where(InboxJob.status == "queued_retry")).scalars().all()
        users = {u.id: u for u in s.execute(select(User)).scalars()}
    n = 0
    for r in rows[:10]:
        thread = r.thread_id or f"{r.user_id}:bid:{r.job_id}"
        hist = await runner.history(services.GRAPHS, "bid", thread)
        good = next((h for h in hist if h["next"] and h["status"] != "queued_retry"), None)
        if not good:
            with session() as s:
                s.get(InboxJob, r.id).status = "queued"
            await analyse(ctx, r.user_id, r.job_id)
        else:
            u = users[r.user_id]
            rid = services.new_run(u.id, "bid", thread, r.job_id)

            async def go(emit, _t=thread, _c=good["checkpoint_id"], _u=u):
                return await runner.replay(services.GRAPHS, "bid", _t, _c, _u.id, _u.persona, on_event=emit)
            await services._run(rid, u, "bid", r.job_id, go)
        n += 1
    return n


async def sync_all(ctx: dict | None = None) -> int:
    with session() as s:
        users = s.execute(select(User).where(User.onboarded.is_(True))).scalars().all()
    n = 0
    for u in users:
        try:
            n += await services.sync_events(u)
        except Exception as e:  # noqa: BLE001
            log.warning("event sync failed for %s: %s", u.id, type(e).__name__)
    return n


async def startup(ctx: dict) -> None:
    init_db()
    from agent.persistence import open_persistence
    ctx["persistence"] = open_persistence()
    cp, st = await ctx["persistence"].__aenter__()
    services.GRAPHS = runner.Graphs(cp, st)


async def shutdown(ctx: dict) -> None:
    await ctx["persistence"].__aexit__(None, None, None)


try:
    from arq import cron
    from arq.connections import RedisSettings

    class WorkerSettings:
        functions = [analyse, scout_all, sync_all, retry_queued]
        cron_jobs = [cron(scout_all, minute=set(range(0, 60, 5))), cron(sync_all, minute=set(range(0, 60, 1))),
                     cron(retry_queued, minute=set(range(2, 60, 5)))]
        on_startup, on_shutdown = startup, shutdown
        redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        max_jobs = 4
        job_timeout = 600
except ImportError:  # pragma: no cover
    pass


async def local_loop() -> None:
    ctx: dict = {}
    await startup(ctx)
    try:
        while True:
            for fn in (scout_all, sync_all, retry_queued):
                try:
                    await fn(ctx)
                except Exception as e:  # noqa: BLE001
                    log.warning("%s failed: %s", fn.__name__, e)
            await asyncio.sleep(60)
    finally:
        await shutdown(ctx)


if __name__ == "__main__" and "--local" in sys.argv:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(local_loop())
