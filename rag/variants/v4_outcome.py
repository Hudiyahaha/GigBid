"""Outcome-aware ranking: boost evidence cited by proposals that won or got replies."""

from rag.pipeline import Flags

NAME = "v4_outcome"
FLAGS = Flags(chunking='fixed', outcome=True)
