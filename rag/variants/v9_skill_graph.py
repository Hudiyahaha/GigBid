"""Skill graph (GraphRAG-lite): skills, projects, industries and outcomes as a graph, fused with dense."""

from rag.pipeline import Flags

NAME = "v9_skill_graph"
FLAGS = Flags(chunking='structured', graph=True)
