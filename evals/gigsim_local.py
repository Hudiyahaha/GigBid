"""Start GigSim in-process (background thread) for scripts and evals, unless one is already running."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager

import httpx


@contextmanager
def running_gigsim(port: int = 8081, error_rate: str | None = None):
    url = os.environ.setdefault("GIGSIM_BASE_URL", f"http://127.0.0.1:{port}")
    try:
        httpx.get(url + "/health", timeout=1.5).raise_for_status()
        yield url
        return
    except Exception:  # noqa: BLE001 - not running: start one
        pass
    if error_rate is not None:
        os.environ["GIGSIM_ERROR_RATE"] = error_rate
    import uvicorn

    from apps.api.db import init_db
    from gigsim import server as gs

    init_db()
    srv = uvicorn.Server(uvicorn.Config(gs.app, host="127.0.0.1", port=int(url.rsplit(":", 1)[1]), log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        yield url
    finally:
        srv.should_exit = True
