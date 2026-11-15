"""Cross-encoder reranking of the dense candidate pool (precision at small k)."""

from rag.pipeline import Flags

NAME = "v3_rerank"
FLAGS = Flags(chunking='fixed', rerank=True)
