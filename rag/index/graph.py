"""V9 skill graph (GraphRAG-lite): skills, projects, items, industries and outcomes as a networkx graph.
Answers "have I done X for a client in industry Y?" by walking skill -> project -> industry edges."""

from __future__ import annotations

import networkx as nx

from rag.ingest.loaders import Document
from rag.ingest.skills import canonical, detect_skills


class SkillGraph:
    def __init__(self, items: dict[str, dict], docs: list[Document]):
        g = nx.Graph()
        for iid, it in items.items():
            g.add_node(iid, kind="item", type=it["type"])
            if it.get("project"):
                g.add_edge(iid, f"project:{it['project']}")
            for s in it.get("skills", []):
                g.add_edge(iid, f"skill:{s}")
            if it.get("client_industry"):
                g.add_edge(f"project:{it.get('project')}", f"industry:{it['client_industry']}")
        for d in docs:
            if d.type == "proposal" and d.project and d.outcome in ("won", "replied"):
                g.add_edge(f"project:{d.project}", f"outcome:{d.outcome}")
        self.g = g

    def rank(self, requirements: list[str], industry: str | None = None) -> list[tuple[str, float, str]]:
        scores: dict[str, float] = {}
        for r in requirements:
            for s in detect_skills(r) or [canonical(r)]:
                node = f"skill:{s}"
                if node not in self.g:
                    continue
                for item in self.g.neighbors(node):
                    if self.g.nodes[item].get("kind") != "item":
                        continue
                    scores[item] = scores.get(item, 0.0) + 1.0
                    for proj in (n for n in self.g.neighbors(item) if n.startswith("project:")):
                        if industry and self.g.has_edge(proj, f"industry:{industry}"):
                            scores[item] += 0.5
                        if self.g.has_edge(proj, "outcome:won"):
                            scores[item] += 0.25
        return sorted(((i, s, "") for i, s in scores.items()), key=lambda x: -x[1])
