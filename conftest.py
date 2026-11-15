"""Test fixtures: isolated temp state, fake LLM (no API calls in CI), and a live in-process GigSim."""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="gigbid-test-"))


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


GIGSIM_PORT = _free_port()


def pytest_configure(config):
    os.environ.update({
        "GIGBID_FAKE_LLM": "1",
        "DATABASE_URL": f"sqlite:///{(_TMP / 'app.db').as_posix()}",
        "AUDIT_DIR": str(_TMP / "audit"),
        "GIGSIM_STATE_PATH": str(_TMP / "gigsim.db"),
        "GIGSIM_ERROR_RATE": "0",
        "GIGSIM_RATE_LIMIT": "100000",
        "GIGSIM_BASE_URL": f"http://127.0.0.1:{GIGSIM_PORT}",
        "WORKSPACE_DB": str(_TMP / "workspace.db"),
        "LLM_CACHE_PATH": str(_TMP / "llm_cache.db"),
        "APPROVAL_SECRET": "test-secret",
        "PORTFOLIO_PERSONA": "ai_ml",
        "GIGBID_CHECKPOINT_DB": str(_TMP / "checkpoints.db"),
        "MARKETPLACE_MODE": "gigsim",
    })
    os.environ.pop("QDRANT_URL", None)


@pytest.fixture(scope="session")
def gigsim():
    import uvicorn

    from apps.api.db import init_db
    from gigsim import server as gs

    init_db()
    cfg = uvicorn.Config(gs.app, host="127.0.0.1", port=GIGSIM_PORT, log_level="error")
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{GIGSIM_PORT}"
    srv.should_exit = True


@pytest.fixture
def tmp_dir() -> Path:
    return _TMP
