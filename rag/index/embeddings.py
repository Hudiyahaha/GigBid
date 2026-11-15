"""Open embedding model (CPU) with a persistent per-text cache."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from agent import config

ROOT = Path(__file__).resolve().parents[2]
_lock = threading.Lock()


class Embedder:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or config.get("models.embeddings", "BAAI/bge-small-en-v1.5")
        self._model = None
        path = Path(os.getenv("EMB_CACHE_PATH", ROOT / "data" / "processed" / "emb_cache.db"))
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS e(k TEXT PRIMARY KEY, v BLOB)")

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    @property
    def dim(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def _key(self, text: str, is_query: bool) -> str:
        return hashlib.sha256(f"{self.model_name}|{int(is_query)}|{text}".encode()).hexdigest()

    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        prefix = "Represent this sentence for searching relevant passages: " if is_query and "bge" in self.model_name.lower() else ""
        keys = [self._key(t, is_query) for t in texts]
        out: list[np.ndarray | None] = [None] * len(texts)
        with _lock:
            for i, k in enumerate(keys):
                row = self._db.execute("SELECT v FROM e WHERE k=?", (k,)).fetchone()
                if row:
                    out[i] = np.frombuffer(row[0], dtype=np.float32)
        missing = [i for i, v in enumerate(out) if v is None]
        if missing:
            vecs = self.model.encode([prefix + texts[i] for i in missing], batch_size=32, normalize_embeddings=True,
                                     show_progress_bar=False).astype(np.float32)
            with _lock:
                for j, i in enumerate(missing):
                    out[i] = vecs[j]
                    self._db.execute("INSERT OR REPLACE INTO e VALUES(?,?)", (keys[i], vecs[j].tobytes()))
                self._db.commit()
        return np.vstack(out) if out else np.zeros((0, 1), dtype=np.float32)


@lru_cache(maxsize=4)
def get_embedder(model_name: str | None = None) -> Embedder:
    return Embedder(model_name)
