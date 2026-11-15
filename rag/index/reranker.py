"""Open cross-encoder reranker (CPU) with an in-process score cache."""

from __future__ import annotations

from functools import lru_cache

from agent import config


class Reranker:
    def __init__(self, model_name: str | None = None):
        from sentence_transformers import CrossEncoder

        self.model_name = model_name or config.get("models.reranker", "BAAI/bge-reranker-base")
        self.model = CrossEncoder(self.model_name, device="cpu", max_length=512)
        self._cache: dict[tuple[str, str], float] = {}

    def score(self, query: str, texts: list[str]) -> list[float]:
        missing = [t for t in texts if (query, t) not in self._cache]
        if missing:
            scores = self.model.predict([(query, t) for t in missing], batch_size=32, show_progress_bar=False)
            for t, s in zip(missing, scores, strict=True):
                self._cache[(query, t)] = float(s)
        return [self._cache[(query, t)] for t in texts]


@lru_cache(maxsize=2)
def get_reranker(model_name: str | None = None) -> Reranker:
    return Reranker(model_name)
