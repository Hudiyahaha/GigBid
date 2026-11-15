"""Retriever factory: the deployed variant is chosen by config (rag.variant), which is set from
evals/results/rag_variants.json (R6)."""

from __future__ import annotations

from agent import config
from rag import variants
from rag.pipeline import Pipeline, Query, Result


def current_variant() -> str:
    return config.get("rag.variant", "v3_rerank")


def get_pipeline(persona: str, variant: str | None = None) -> Pipeline:
    return Pipeline.get(persona, variants.get(variant or current_variant()))


async def retrieve(persona: str, title: str, text: str, requirements: list[str] | None = None,
                   industry: str | None = None, k: int = 8, types: list[str] | None = None,
                   variant: str | None = None) -> Result:
    import asyncio

    pipe = get_pipeline(persona, variant)
    hyde = None
    if pipe.flags.hyde:
        from rag.query import hyde_text
        hyde = await hyde_text(title, text)
    q = Query(persona=persona, title=title, text=text, requirements=requirements or [], hyde_text=hyde, industry=industry)
    return await asyncio.to_thread(pipe.retrieve, q, k, types)


def reindex(persona: str) -> None:
    """Incremental re-indexing hook: called when the user adds work in the UI."""
    Pipeline.invalidate(persona)
