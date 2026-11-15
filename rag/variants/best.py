"""Best combination found by evals/runners/ablation.py (see evals/results/ablation.json)."""

from rag.pipeline import Flags

NAME = "best"
FLAGS = Flags(chunking='structured', decompose=True, hybrid=True, rerank=True, multivector=True, outcome=True)
