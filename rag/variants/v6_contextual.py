"""Contextual retrieval: a generated context line prepended to each chunk."""

from rag.pipeline import Flags

NAME = "v6_contextual"
FLAGS = Flags(chunking='structured', contextual=True)
