"""Hybrid BM25 + dense (V2) combined with outcome-aware ranking (V4): the two components that individually helped."""

from rag.pipeline import Flags

NAME = "v10_hybrid_outcome"
FLAGS = Flags(chunking="fixed", hybrid=True, outcome=True)
