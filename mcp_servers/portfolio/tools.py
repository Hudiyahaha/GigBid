"""Portfolio tool logic (kept separate from the MCP wiring so it is unit-testable)."""

from __future__ import annotations

import os
from collections import defaultdict

from agent import config
from rag.ingest.loaders import load_persona
from rag.retriever import get_pipeline, retrieve


def default_persona() -> str:
    return os.getenv("PORTFOLIO_PERSONA", "ai_ml")


async def search_evidence(persona: str, requirement: str, k: int, filters: dict) -> dict:
    types = filters.get("types") or ["case_study", "repo", "review", "cv"]
    res = await retrieve(persona, title=filters.get("job_title") or "", text=requirement,
                         requirements=filters.get("requirements") or [], industry=filters.get("industry"), k=k, types=types)
    return {"variant": config.get("rag.variant"), "items": res.items, "per_requirement": res.per_requirement,
            "unsupported_requirements": res.unsupported}


def similar_proposals(persona: str, query: str, k: int) -> list[dict]:
    from rag.retriever import LOCK
    with LOCK:
        props = get_pipeline(persona).proposals(query, k)
    return [{"item_id": p["item_id"], "type": "proposal", "title": p["item_id"], "outcome": p["outcome"],
             "snippet": p["text"][:600], "source": "synthetic"} for p in props]


def _docs(persona: str):
    return load_persona(persona)


def get_item(persona: str, item_id: str) -> dict | None:
    docs = [d for d in _docs(persona) if d.item_id == item_id]
    if not docs:
        return None
    head = next((d for d in docs if d.kind in ("summary", "readme", "cv", "review", "proposal")), docs[0])
    text = "\n\n".join(d.text for d in sorted(docs, key=lambda d: d.kind != "readme"))
    skills = sorted({s for d in docs for s in d.skills})
    return {"item_id": item_id, "title": head.title, "project": head.project, "date": head.date,
            "client_industry": head.client_industry, "skills": skills, "text": text[:20000]}


def render_item(persona: str, item_id: str) -> str:
    d = get_item(persona, item_id)
    if not d:
        return f"Not found: {item_id}"
    return f"# {d['title']}\n\nskills: {', '.join(d['skills'])}\n\n{d['text']}"


def list_skills(persona: str) -> list[dict]:
    pipe = get_pipeline(persona)
    support: dict[str, set] = defaultdict(set)
    latest: dict[str, str] = {}
    for iid, it in pipe.items.items():
        for s in it["skills"]:
            support[s].add(iid)
            if it.get("date") and it["date"] > latest.get(s, ""):
                latest[s] = it["date"]
    return sorted(({"skill": s, "items": len(v), "latest": latest.get(s, "")[:4]} for s, v in support.items()),
                  key=lambda x: -x["items"])
