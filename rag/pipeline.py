"""Composable retrieval pipeline. Every RAG variant (rag/variants/vN_*.py) is a preset of these flags,
so ablations are one flag flip and `python -m evals.runners.rag_eval` reruns the whole comparison.

Flags
  chunking     fixed | structured
  decompose    one retrieval per requirement, merged with RRF               (V1)
  hybrid       BM25 + dense fused with reciprocal rank fusion               (V2)
  rerank       cross-encoder reranking of the candidate pool                (V3)
  outcome      boost evidence cited in proposals that won / got replies    (V4)
  multivector  summary / README / code chunks roll up to one project        (V5)
  contextual   generated context line prepended to every chunk              (V6)
  hyde         also retrieve with a hypothetical ideal proposal             (V7)
  corrective   grade evidence per requirement, re-query when weak, refuse   (V8)
  graph        skill graph: skills <-> projects <-> industries <-> outcomes (V9)
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from agent import config
from rag.index.bm25 import BM25Index
from rag.index.vector import VectorIndex
from rag.ingest.chunker import Chunk, fixed_chunks, structured_chunks
from rag.ingest.loaders import Document, load_persona

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_TYPES = ["case_study", "repo", "review", "cv"]
TYPE_ORDER = {"case_study": 0, "repo": 1, "review": 2, "cv": 3, "proposal": 4}


@dataclass(frozen=True)
class Flags:
    chunking: str = "fixed"
    decompose: bool = False
    hybrid: bool = False
    rerank: bool = False
    outcome: bool = False
    multivector: bool = False
    contextual: bool = False
    hyde: bool = False
    corrective: bool = False
    graph: bool = False

    def key(self) -> str:
        return "-".join(f"{k}={v}" for k, v in asdict(self).items())


@dataclass
class Query:
    persona: str
    title: str
    text: str
    requirements: list[str] = field(default_factory=list)
    hyde_text: str | None = None
    industry: str | None = None


@dataclass
class Result:
    items: list[dict]
    per_requirement: dict[str, list[dict]]
    unsupported: list[str]
    latency_s: float
    debug: dict = field(default_factory=dict)


def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    s: dict[str, float] = defaultdict(float)
    for r in rankings:
        for i, x in enumerate(r):
            s[x] += 1.0 / (k + i + 1)
    return s


def load_contexts() -> dict[str, str]:
    p = ROOT / "data" / "processed" / "contexts.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


class Pipeline:
    _cache: dict[tuple[str, str], Pipeline] = {}

    @classmethod
    def get(cls, persona: str, flags: Flags) -> Pipeline:
        key = (persona, flags.key())
        if key not in cls._cache:
            cls._cache[key] = Pipeline(persona, flags)
        return cls._cache[key]

    @classmethod
    def invalidate(cls, persona: str | None = None) -> None:
        for k in list(cls._cache):
            if persona is None or k[0] == persona:
                del cls._cache[k]

    def __init__(self, persona: str, flags: Flags, docs: list[Document] | None = None):
        self.persona, self.flags = persona, flags
        docs = docs if docs is not None else load_persona(persona)
        self.docs = docs
        self.evidence_docs = [d for d in docs if d.type in EVIDENCE_TYPES or d.source == "user_upload"]
        size = int(config.get("rag.chunk_size", 900))
        overlap = int(config.get("rag.chunk_overlap", 120))
        chunking = "structured" if flags.multivector else flags.chunking
        self.chunks: list[Chunk] = (structured_chunks(self.evidence_docs, size) if chunking == "structured"
                                    else fixed_chunks(self.evidence_docs, size, overlap))
        if flags.contextual:
            ctx = load_contexts()
            for c in self.chunks:
                c.context = ctx.get(c.chunk_id) or self._heuristic_context(c)
        self.items: dict[str, dict] = {}
        for d in self.evidence_docs:
            it = self.items.setdefault(d.item_id, {"item_id": d.item_id, "type": d.type, "title": d.title,
                                                   "project": d.project, "date": d.date, "source": d.source,
                                                   "client_industry": d.client_industry, "skills": set()})
            it["skills"].update(d.skills)
            if d.kind in ("summary", "readme", "cv", "review"):
                it["title"] = d.title
        self.project_items: dict[str, list[str]] = defaultdict(list)
        for iid, it in self.items.items():
            if it["project"]:
                self.project_items[it["project"]].append(iid)
        self.vec = VectorIndex(f"{persona}-{abs(hash(flags.key())) % 10**8}", self.chunks)
        self.bm25 = BM25Index(self.chunks) if flags.hybrid else None
        self.outcome_boost = self._outcome_stats(docs) if flags.outcome else {}
        self.graph = None
        if flags.graph:
            from rag.index.graph import SkillGraph
            self.graph = SkillGraph(self.items, docs)

    @staticmethod
    def _heuristic_context(c: Chunk) -> str:
        m = c.meta
        bits = [f"From the freelancer's {m.get('type', 'document').replace('_', ' ')} '{m.get('title', '')}'"]
        if m.get("client_industry"):
            bits.append(f"for a {m['client_industry']} client")
        if m.get("date"):
            bits.append(f"({m['date'][:4]})")
        if m.get("kind") == "code":
            bits.append("- source code file")
        return " ".join(bits) + "."

    @staticmethod
    def _outcome_stats(docs: list[Document]) -> dict[str, float]:
        """project -> boost in [-0.5, 1]: how often proposals citing it won or got replies."""
        cnt: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for d in docs:
            if d.type == "proposal" and d.project:
                cnt[d.project][0] += 1
                cnt[d.project][1] += {"won": 2, "replied": 1}.get(d.outcome or "", 0)
        base = (sum(v[1] for v in cnt.values()) / max(1, sum(v[0] for v in cnt.values())))
        return {p: max(-0.5, min(1.0, (v[1] / v[0] - base))) for p, v in cnt.items() if v[0] >= 2}

    # ------------------------------------------------------------- core
    def _candidates(self, q: str, n: int, types: list[str]) -> list[tuple[Chunk, float]]:
        dense = self.vec.search(q, n, types)
        if not self.bm25:
            return dense
        sparse = self.bm25.search(q, n, types)
        fused = rrf([[c.chunk_id for c, _ in dense], [c.chunk_id for c, _ in sparse]])
        by_id = {c.chunk_id: c for c, _ in dense + sparse}
        return sorted(((by_id[i], s) for i, s in fused.items()), key=lambda x: -x[1])[:n]

    def _rank_items(self, q: str, types: list[str]) -> list[tuple[str, float, str]]:
        """Return [(item_id, score, best_snippet)] for one query string."""
        n = int(config.get("rag.rerank_candidates", 30))
        cands = self._candidates(q, n, types)
        if self.flags.rerank and cands:
            from rag.index.reranker import get_reranker
            scores = get_reranker().score(q, [c.text[:1500] for c, _ in cands])
            cands = sorted(zip([c for c, _ in cands], scores, strict=True), key=lambda x: -x[1])
        best: dict[str, tuple[float, str]] = {}
        for c, s in cands:
            if c.item_id not in best or s > best[c.item_id][0]:
                best[c.item_id] = (s, c.text)
        return sorted(((i, s, t) for i, (s, t) in best.items()), key=lambda x: -x[1])

    def _queries(self, q: Query) -> list[tuple[str, str]]:
        qs: list[tuple[str, str]] = []
        if self.flags.decompose and q.requirements:
            qs += [(r, r) for r in q.requirements]
        else:
            qs.append(("job", f"{q.title}\n{q.text}"))
        if self.flags.hyde and q.hyde_text:
            qs.append(("hyde", q.hyde_text))
        return qs

    def retrieve(self, q: Query, k: int = 10, types: list[str] | None = None) -> Result:
        t0 = time.perf_counter()
        types = types or ["case_study", "repo", "review"]
        threshold = float(config.get("rag.corrective_threshold", 0.0 if self.flags.rerank else 0.55))
        per_query: dict[str, list[tuple[str, float, str]]] = {}
        unsupported: list[str] = []
        requeries = 0
        for label, text in self._queries(q):
            ranked = self._rank_items(text, types)
            if self.flags.corrective and label not in ("job", "hyde"):
                if not ranked or ranked[0][1] < threshold:
                    requeries += 1
                    alt = self._rank_items(f"project experience delivering {text} for a client", types)
                    if alt and alt[0][1] >= threshold:
                        ranked = alt
                    else:
                        unsupported.append(label)
                        ranked = []
                ranked = [r for r in ranked if r[1] >= threshold]
            per_query[label] = ranked
        if self.graph is not None:
            per_query["graph"] = self.graph.rank(q.requirements or [q.title], q.industry)
        fused = rrf([[i for i, _, _ in r] for r in per_query.values() if r])
        snippets = {i: t for r in per_query.values() for i, _, t in reversed(r)}
        if self.outcome_boost:
            for iid in fused:
                proj = self.items.get(iid, {}).get("project")
                if proj in self.outcome_boost:
                    fused[iid] *= 1.0 + 0.35 * self.outcome_boost[proj]
        order = sorted(fused, key=lambda i: -fused[i])
        if self.flags.multivector:
            order = self._expand_projects(order, fused)
        items = [self._item(i, fused.get(i, 0.0), snippets.get(i, "")) for i in order[:k]]
        per_req = {lab: [self._item(i, s, t) for i, s, t in r[:5]] for lab, r in per_query.items() if lab not in ("job", "hyde")}
        if os.getenv("RAG_NO_RELEVANCE") != "1":
            self._add_relevance(f"{q.title}\n{q.text}"[:1500], items)
            for lab, its in per_req.items():
                self._add_relevance(lab, its)
        return Result(items, per_req, unsupported, time.perf_counter() - t0,
                      {"queries": len(per_query), "requeries": requeries, "flags": asdict(self.flags)})

    @staticmethod
    def _add_relevance(query: str, items: list[dict]) -> None:
        """Variant-independent, calibrated 0..1 relevance (sigmoid of the cross-encoder logit) used by the Fit
        Matcher thresholds. Fused scores (RRF, cosine, BM25) are not comparable across variants."""
        if not items:
            return
        from rag.index.reranker import get_reranker
        logits = get_reranker().score(query, [it["snippet"] or it["title"] for it in items])
        for it, z in zip(items, logits, strict=True):
            it["relevance"] = round(1 / (1 + math.exp(-z)), 4)

    def _expand_projects(self, order: list[str], scores: dict[str, float]) -> list[str]:
        proj_score: dict[str, float] = {}
        loose: list[str] = []
        for i in order:
            p = self.items.get(i, {}).get("project")
            if p:
                proj_score[p] = max(proj_score.get(p, 0.0), scores[i])
            else:
                loose.append(i)
        out: list[str] = []
        for p in sorted(proj_score, key=lambda x: -proj_score[x]):
            out += sorted(self.project_items[p], key=lambda i: TYPE_ORDER.get(self.items[i]["type"], 9))
        return out + loose

    def _item(self, iid: str, score: float, snippet: str) -> dict:
        it = self.items.get(iid, {"item_id": iid, "type": "unknown"})
        return {"item_id": iid, "type": it.get("type"), "title": it.get("title", ""), "project": it.get("project"),
                "date": it.get("date"), "source": it.get("source", ""), "client_industry": it.get("client_industry"),
                "skills": sorted(it.get("skills", [])), "snippet": re.sub(r"\s+", " ", snippet)[:400],
                "score": round(float(score), 5)}

    def proposals(self, category_text: str, k: int = 3, outcomes: tuple[str, ...] = ("won", "replied")) -> list[dict]:
        """Past proposals similar to a job, preferring ones that worked (used by Writer, V4)."""
        props = [d for d in self.docs if d.type == "proposal" and d.outcome in outcomes]
        if not props:
            return []
        from rag.index.embeddings import get_embedder
        emb = get_embedder()
        qv = emb.encode([category_text], is_query=True)[0]
        pv = emb.encode([d.text for d in props])
        order = (pv @ qv).argsort()[::-1][:k]
        return [{"item_id": props[i].item_id, "outcome": props[i].outcome, "text": props[i].text[:900]} for i in order]
