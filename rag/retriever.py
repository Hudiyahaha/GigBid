"""Retriever factory: the deployed variant is chosen by config (rag.variant), which is set from
evals/results/rag_variants.json (R6).

All retrieval runs in a worker thread under ONE process-wide lock: CPU models (embedder, cross-encoder) gain nothing
from running concurrently on a CPU box, and first-time model/index construction is not thread-safe.
"""

from __future__ import annotations

import asyncio
import os
import threading

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from agent import config  # noqa: E402
from rag import variants  # noqa: E402
from rag.pipeline import Pipeline, Query, Result  # noqa: E402

LOCK = threading.RLock()
_torch_set = False


def _limit_torch() -> None:
    global _torch_set
    if not _torch_set:
        try:
            import torch
            torch.set_num_threads(int(os.getenv("TORCH_THREADS", "4")))
        except Exception:  # noqa: BLE001
            pass
        _torch_set = True


def current_variant() -> str:
    return config.get("rag.variant", "v3_rerank")


def get_pipeline(persona: str, variant: str | None = None) -> Pipeline:
    with LOCK:
        _limit_torch()
        return Pipeline.get(persona, variants.get(variant or current_variant()))


async def retrieve(persona: str, title: str, text: str, requirements: list[str] | None = None,
                   industry: str | None = None, k: int = 8, types: list[str] | None = None,
                   variant: str | None = None) -> Result:
    flags = variants.get(variant or current_variant())
    hyde = None
    if flags.hyde:
        from rag.query import hyde_text
        hyde = await hyde_text(title, text)
    q = Query(persona=persona, title=title, text=text, requirements=requirements or [], hyde_text=hyde, industry=industry)

    def run() -> Result:
        with LOCK:
            return get_pipeline(persona, variant).retrieve(q, k, types)
    return await asyncio.to_thread(run)


def reindex(persona: str) -> None:
    """Incremental re-indexing hook: called when the user adds work in the UI."""
    with LOCK:
        Pipeline.invalidate(persona)
