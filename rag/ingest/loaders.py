"""Corpus loaders (B1): PDF CV, Markdown case studies, repo READMEs + code, reviews, past proposals.

A *document* is one evidence item (or one file of a repo). Every document carries metadata:
persona, type, item_id, project, title, skills (detected), date, client_industry, outcome (proposals), kind.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rag.ingest.skills import detect_skills

ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = ROOT / "data" / "personas"
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".yml", ".css", ".liquid", ".dax", ".twb", ".R", ".gs", ".txt"}


@dataclass
class Document:
    item_id: str
    persona: str
    type: str                     # cv | case_study | repo | review | proposal | user_upload
    text: str
    title: str = ""
    project: str | None = None
    kind: str = "summary"         # summary | readme | code | review | proposal | cv
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None    # proposals: won | replied | ignored
    skills: list[str] = field(default_factory=list)
    source: str = ""
    path: str = ""

    def meta(self) -> dict:
        d = asdict(self)
        d.pop("text")
        return d


def _front_matter(raw: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, raw[m.end():]


def load_cv(pdir: Path, persona: str) -> list[Document]:
    pdf = pdir / "cv.pdf"
    text = ""
    if pdf.exists():
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)
    if not text.strip() and (pdir / "cv.md").exists():
        text = _front_matter((pdir / "cv.md").read_text(encoding="utf-8"))[1]
    if not text.strip():
        return []
    return [Document(item_id=f"cv-{persona}", persona=persona, type="cv", kind="cv", text=text, title="Curriculum vitae",
                     skills=detect_skills(text), source="synthetic", path=str(pdf))]


def load_case_studies(pdir: Path, persona: str) -> list[Document]:
    out = []
    for f in sorted((pdir / "case_studies").glob("*.md")):
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        out.append(Document(item_id=meta.get("id", f.stem), persona=persona, type="case_study", kind="summary",
                            text=body, title=meta.get("title", f.stem), project=meta.get("project"),
                            date=meta.get("date"), client_industry=meta.get("client_industry"),
                            skills=detect_skills(body), source=meta.get("source", ""), path=str(f)))
    return out


def load_repos(pdir: Path, persona: str) -> list[Document]:
    out = []
    for rdir in sorted((pdir / "repos").glob("*")):
        if not rdir.is_dir():
            continue
        item_id = rdir.name
        project = item_id.removeprefix("repo-")
        for f in sorted(rdir.rglob("*")):
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            kind = "readme" if f.name.lower() == "readme.md" else "code"
            if kind == "code" and f.suffix not in CODE_EXT and f.name != "Dockerfile":
                continue
            rel = f.relative_to(rdir).as_posix()
            title = (re.search(r"^# (.+)$", text, re.M).group(1) if kind == "readme" and re.search(r"^# (.+)$", text, re.M)
                     else f"{item_id}/{rel}")
            out.append(Document(item_id=item_id, persona=persona, type="repo", kind=kind,
                                text=(f"File: {rel}\n" + text) if kind == "code" else text, title=title, project=project,
                                skills=detect_skills(text), source="synthetic", path=str(f)))
    return out


def load_reviews(pdir: Path, persona: str) -> list[Document]:
    f = pdir / "reviews.json"
    if not f.exists():
        return []
    return [Document(item_id=r["id"], persona=persona, type="review", kind="review",
                     text=f"Client review ({r['stars']}/5) from a {r['client_industry']} client: {r['text']}",
                     title=f"Review: {r['client']}", project=r.get("project"), date=r.get("date"),
                     client_industry=r.get("client_industry"), skills=detect_skills(r["text"]),
                     source=r.get("source", ""), path=str(f)) for r in json.loads(f.read_text(encoding="utf-8"))]


def load_proposals(pdir: Path, persona: str) -> list[Document]:
    f = pdir / "proposals.json"
    if not f.exists():
        return []
    out = []
    for p in json.loads(f.read_text(encoding="utf-8")):
        text = f"Past proposal for '{p['job_title']}' ({p['job_category']}). Outcome: {p['outcome']}.\n{p['text']}"
        out.append(Document(item_id=p["id"], persona=persona, type="proposal", kind="proposal", text=text,
                            title=p["job_title"], project=(p.get("projects_cited") or [None])[0], date=p.get("date"),
                            outcome=p["outcome"], skills=detect_skills(p["text"]), source=p.get("source", ""), path=str(f)))
    return out


def load_uploads(persona: str) -> list[Document]:
    """Work the user added in the UI (incremental re-indexing)."""
    udir = ROOT / "data" / "processed" / "uploads" / persona
    out = []
    for f in sorted(udir.glob("*.md")) if udir.exists() else []:
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        out.append(Document(item_id=meta.get("id", f.stem), persona=persona, type=meta.get("type", "case_study"),
                            kind="summary", text=body, title=meta.get("title", f.stem), project=meta.get("project", f.stem),
                            date=meta.get("date"), skills=detect_skills(body), source="user_upload", path=str(f)))
    return out


def load_persona(persona: str, include_proposals: bool = True) -> list[Document]:
    pdir = PERSONA_DIR / persona
    docs = load_cv(pdir, persona) + load_case_studies(pdir, persona) + load_repos(pdir, persona) + load_reviews(pdir, persona)
    if include_proposals:
        docs += load_proposals(pdir, persona)
    return docs + load_uploads(persona)


def personas() -> list[str]:
    return sorted(p.name for p in PERSONA_DIR.iterdir() if p.is_dir()) if PERSONA_DIR.exists() else []
