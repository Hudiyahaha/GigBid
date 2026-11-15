"""Dense index on Qdrant. Uses a Qdrant server when QDRANT_URL is set (docker compose), otherwise an
in-process Qdrant instance (no lock files, safe for many processes). Embeddings are cached on disk, so
rebuilding an in-memory collection is cheap."""

from __future__ import annotations

import os
import uuid

import numpy as np

from rag.index.embeddings import Embedder, get_embedder
from rag.ingest.chunker import Chunk

_CLIENT = None


def client():
    global _CLIENT
    if _CLIENT is None:
        from qdrant_client import QdrantClient
        url = os.getenv("QDRANT_URL")
        _CLIENT = QdrantClient(url=url, timeout=20) if url else QdrantClient(location=":memory:")
    return _CLIENT


class VectorIndex:
    def __init__(self, name: str, chunks: list[Chunk], embedder: Embedder | None = None):
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.name = name
        self.embedder = embedder or get_embedder()
        self.chunks = chunks
        self.by_id = {c.chunk_id: c for c in chunks}
        vecs = self.embedder.encode([c.indexed_text for c in chunks]) if chunks else np.zeros((0, 384), np.float32)
        self._vecs = vecs
        qc = client()
        if qc.collection_exists(name):
            qc.delete_collection(name)
        qc.create_collection(name, vectors_config=VectorParams(size=vecs.shape[1] if len(chunks) else 384,
                                                               distance=Distance.COSINE))
        pts = [PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, c.chunk_id)), vector=vecs[i].tolist(),
                           payload={"chunk_id": c.chunk_id, "item_id": c.item_id, "type": c.meta.get("type"),
                                    "kind": c.meta.get("kind")}) for i, c in enumerate(chunks)]
        for i in range(0, len(pts), 256):
            qc.upsert(name, pts[i:i + 256])

    def search(self, query: str, k: int = 20, types: list[str] | None = None) -> list[tuple[Chunk, float]]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        qv = self.embedder.encode([query], is_query=True)[0]
        flt = Filter(must=[FieldCondition(key="type", match=MatchAny(any=types))]) if types else None
        res = client().query_points(self.name, query=qv.tolist(), limit=k, query_filter=flt).points
        return [(self.by_id[p.payload["chunk_id"]], float(p.score)) for p in res]
