"""One-process local stack for development and Playwright: GigSim (:8081) + GigBid API serving the built web app (:8000).

    python -m scripts.dev_stack            # uses your .env models
    GIGBID_FAKE_LLM=1 python -m scripts.dev_stack   # deterministic, offline (used by Playwright and CI)
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if os.getenv("GIGBID_E2E") == "1":
    d = ROOT / "data" / "processed" / "e2e"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.db"):
        f.unlink()
    os.environ.update({"DATABASE_URL": f"sqlite:///{(d / 'app.db').as_posix()}", "GIGSIM_STATE_PATH": str(d / "gigsim.db"),
                       "GIGBID_CHECKPOINT_DB": str(d / "checkpoints.db"), "WORKSPACE_DB": str(d / "workspace.db"),
                       "AUDIT_DIR": str(d / "audit")})
    if os.getenv("GIGBID_DEMO_LLM") != "1":  # E2E tests stay deterministic; demo recordings use the real open models
        os.environ["GIGBID_FAKE_LLM"] = "1"
os.environ.setdefault("GIGBID_LOCAL_SQLITE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_POLICY_VERSION", "2")
os.environ.setdefault("GIGBID_DEV", "1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:8000")

if __name__ == "__main__":
    import uvicorn

    from evals.gigsim_local import running_gigsim
    with running_gigsim(8081):
        # HOST=0.0.0.0 on a cloud host (Render sets PORT); GigSim stays internal on 127.0.0.1:8081
        uvicorn.run("apps.api.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                    log_level="warning")
