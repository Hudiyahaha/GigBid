"""Open cross-encoder reranker (CPU) with an in-process score cache.

EMBED_BACKEND=fastembed runs the same MS-MARCO MiniLM cross-encoder on ONNX Runtime (no torch) for the
free 512 MB deployment; the default backend is sentence-transformers.
"""

from __future__ import annotations

import os
from functools import lru_cache

from agent import config

FASTEMBED_NAMES = {"cross-encoder/ms-marco-MiniLM-L-6-v2": "Xenova/ms-marco-MiniLM-L-6-v2",
                   "cross-encoder/ms-marco-MiniLM-L-12-v2": "Xenova/ms-marco-MiniLM-L-12-v2"}


class Reranker:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or config.get("models.reranker", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.backend = os.getenv("EMBED_BACKEND", "st")
        if self.backend == "fastembed":
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            self.model = TextCrossEncoder(model_name=FASTEMBED_NAMES.get(self.model_name, self.model_name), threads=1)
        else:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(self.model_name, device="cpu", max_length=512)
        self._cache: dict[tuple[str, str], float] = {}

    def _predict(self, query: str, texts: list[str]) -> list[float]:
        if self.backend == "fastembed":
            return [float(s) for s in self.model.rerank(query, texts, batch_size=16)]
        return [float(s) for s in self.model.predict([(query, t) for t in texts], batch_size=32, show_progress_bar=False)]

    def score(self, query: str, texts: list[str]) -> list[float]:
        missing = [t for t in texts if (query, t) not in self._cache]
        if missing:
            for t, s in zip(missing, self._predict(query, missing), strict=True):
                self._cache[(query, t)] = s
        return [self._cache[(query, t)] for t in texts]


@lru_cache(maxsize=2)
def get_reranker(model_name: str | None = None) -> Reranker:
    return Reranker(model_name)
