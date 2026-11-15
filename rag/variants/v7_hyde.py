"""HyDE: also retrieve with a hypothetical ideal proposal for the job."""

from rag.pipeline import Flags

NAME = "v7_hyde"
FLAGS = Flags(chunking='fixed', hyde=True)
