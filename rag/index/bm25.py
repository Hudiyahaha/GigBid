"""BM25 keyword index with a tokenizer that keeps technical names intact (dbt, next.js, c++, a/b)."""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from rag.ingest.chunker import Chunk

STOP = set("a an the and or of to in for on with by is are was were be been it this that as at from your our we you i "
           "my me us they their has have had will would can could should not no but if into about than then so".split())


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9][a-z0-9+#./-]*[a-z0-9+#]|[a-z0-9]", (text or "").lower())
    return [t for t in toks if t not in STOP]


class BM25Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c.indexed_text) for c in chunks]) if chunks else None

    def search(self, query: str, k: int = 20, types: list[str] | None = None) -> list[tuple[Chunk, float]]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            if types and self.chunks[i].meta.get("type") not in types:
                continue
            out.append((self.chunks[i], float(scores[i])))
            if len(out) >= k:
                break
        return out
