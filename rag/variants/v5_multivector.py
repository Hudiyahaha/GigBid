"""Multi-vector items: summary, README and code chunks indexed separately, returned as one project."""

from rag.pipeline import Flags

NAME = "v5_multivector"
FLAGS = Flags(chunking='structured', multivector=True)
