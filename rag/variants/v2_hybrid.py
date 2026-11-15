"""Hybrid BM25 + dense with reciprocal rank fusion (exact tool names)."""

from rag.pipeline import Flags

NAME = "v2_hybrid"
FLAGS = Flags(chunking='fixed', hybrid=True)
