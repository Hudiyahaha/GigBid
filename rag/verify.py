"""Claim splitting and grounding (B3, R5).

A *claim* is a sentence that asserts something about the freelancer's experience or results (first-person
experience verbs, a citation marker, or a number). Each claim is checked against the full text of the evidence
it cites:
  supported   - every named skill and every number in the claim appears in the cited evidence
  partial     - cited, but some detail (a number, a tool) is not in the evidence
  unsupported - nothing cited, or none of the named skills appear in the cited evidence
Unsupported claims are removed; partial claims are rewritten (LLM) or removed (heuristic) before the Critic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.ingest.skills import detect_skills

CITE = re.compile(r"\[E:([A-Za-z0-9_\-.]+)\]")
EXPERIENCE = re.compile(
    r"\b(i|i've|i have|i'm|my|we|our team)\b[^.]*\b(built|build|used|delivered|shipped|worked|developed|designed|created|"
    r"led|ran|deployed|trained|automated|handled|reduced|raised|cut|improved|grew|migrated|wrote|implemented|launched|"
    r"managed|achieved|helped|did|have done|specialise|specialize|experience|years)\b", re.I)
NUM = re.compile(r"(?<![\w:])\d[\d,.]*\s?%?")


@dataclass
class ClaimCheck:
    index: int
    text: str
    cited: list[str]
    status: str
    reason: str


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def is_claim(sent: str) -> bool:
    plain = CITE.sub("", sent)
    return bool(CITE.search(sent) or EXPERIENCE.search(plain) or (NUM.search(plain) and re.search(r"\b(i|my|we)\b", plain, re.I)))


def check(sent: str, evidence: dict[str, dict]) -> tuple[str, str]:
    cited = [c for c in CITE.findall(sent)]
    plain = CITE.sub("", sent)
    if not cited:
        return "unsupported", "no evidence cited"
    known = [c for c in cited if c in evidence]
    if not known:
        return "unsupported", "cited evidence does not exist"
    ev_text = " ".join(evidence[c].get("text", "") for c in known).lower()
    ev_skills = {s for c in known for s in evidence[c].get("skills", [])} | set(detect_skills(ev_text))
    claim_skills = [s for s in detect_skills(plain) if s not in ("Python",)]
    missing_skills = [s for s in claim_skills if s not in ev_skills]
    nums = [n.strip().rstrip(".,") for n in NUM.findall(plain)]
    missing_nums = [n for n in nums if n and n.replace(",", "") not in ev_text.replace(",", "")]
    if claim_skills and len(missing_skills) == len(claim_skills):
        return "unsupported", f"evidence does not show {', '.join(missing_skills)}"
    if missing_skills or missing_nums:
        return "partial", "not in evidence: " + ", ".join(missing_skills + missing_nums)
    return "supported", "all specifics found in cited evidence"


def verify_text(text: str, evidence: dict[str, dict], offset: int = 0) -> list[ClaimCheck]:
    out = []
    for i, s in enumerate(sentences(text)):
        if is_claim(s):
            st, why = check(s, evidence)
            out.append(ClaimCheck(offset + i, s, CITE.findall(s), st, why))
    return out


def apply(text: str, checks: list[ClaimCheck], rewrites: dict[int, str] | None = None, offset: int = 0) -> str:
    rewrites = rewrites or {}
    by_idx = {c.index: c for c in checks}
    kept = []
    for i, s in enumerate(sentences(text)):
        c = by_idx.get(offset + i)
        if c is None or c.status == "supported":
            kept.append(s)
        elif c.status == "partial" and rewrites.get(c.index):
            kept.append(rewrites[c.index])
        # unsupported, or partial without a rewrite: removed
    return " ".join(kept)


def unsupported_rate(checks: list[ClaimCheck]) -> float:
    return round(sum(c.status == "unsupported" for c in checks) / len(checks), 4) if checks else 0.0
