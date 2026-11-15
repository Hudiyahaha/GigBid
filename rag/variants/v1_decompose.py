"""Requirement decomposition: one retrieval per extracted requirement, merged with RRF."""

from rag.pipeline import Flags

NAME = "v1_decompose"
FLAGS = Flags(chunking='fixed', decompose=True)
