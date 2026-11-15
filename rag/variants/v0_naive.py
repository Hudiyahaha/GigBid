"""Naive dense: fixed chunks, top-k cosine on the whole job post (baseline)."""

from rag.pipeline import Flags

NAME = "v0_naive"
FLAGS = Flags(chunking='fixed')
