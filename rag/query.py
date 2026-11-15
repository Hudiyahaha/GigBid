"""Query-side helpers: heuristic requirement decomposition (no LLM), HyDE text generation."""

from __future__ import annotations

import re

from agent.guardrails import strip_injections

SKIP_SENT = re.compile(r"(?i)^(deliverables|we are a|our small|i run a|our \w+ team|please|to receive|payment will|"
                       r"add me|share your|before we hire|send a complete|buy the|i need someone to make sense|"
                       r"our current setup|we have the data)")


def decompose(description: str, max_reqs: int = 8) -> list[str]:
    """Split a job post into requirement sentences (one retrieval query each)."""
    clean, _ = strip_injections(description)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if len(s.split()) >= 3]
    reqs = [s for s in sents if not SKIP_SENT.search(s)]
    return reqs[:max_reqs] or sents[:max_reqs]


async def hyde_text(title: str, description: str) -> str:
    from agent import llm
    text, _ = await llm.call_text("hyde", "hyde", {"title": title, "job": description[:2500]},
                                  heuristic=lambda: f"{title}. {description[:400]}", max_tokens=300)
    return text
