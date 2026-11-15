"""Corrective RAG: grade evidence per requirement, re-query when weak, refuse to claim when none."""

from rag.pipeline import Flags

NAME = "v8_corrective"
FLAGS = Flags(chunking='structured', decompose=True, hybrid=True, rerank=True, corrective=True)
