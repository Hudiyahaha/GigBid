"""Simulated GigSim client: decides whether to reply / interview / hire.

Every job has HIDDEN preferences that GigBid never sees:
  must_have      - 1-2 skills the client cares about most
  ceiling        - the most the client will pay (fixed total or hourly rate)
  dislikes_generic - penalises template openings ("Dear Sir/Madam", "passionate", ...)
  prefers_concise  - penalises proposals over ~220 words

The decision is a transparent logistic model (default, deterministic given a seed) so evaluations are
reproducible and cheap. An optional LLM judge can override it (see gigsim/server.py, GIGSIM_CLIENT_LLM).
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass, field

GENERIC_PATTERNS = [
    r"dear sir", r"madam", r"to whom it may concern", r"i am writing to express",
    r"passionate", r"hard[- ]?working", r"perfect fit", r"i have read your job",
    r"i am the best", r"\bguru\b", r"rockstar", r"i can do this job",
]
CONTACT_PATTERNS = [
    r"[\w.+-]+@[\w-]+\.[\w.]+", r"\+?\d[\d\s\-()]{8,}\d", r"whatsapp", r"telegram", r"skype", r"wechat",
]


@dataclass
class HiddenPrefs:
    must_have: list[str]
    ceiling: float
    dislikes_generic: bool
    prefers_concise: bool
    true_value: float
    pay_type: str = "fixed"  # fixed | hourly


@dataclass
class ClientDecision:
    reply: bool
    interview: bool
    hire: bool
    reply_prob: float
    features: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def _mentions(text: str, skill: str) -> bool:
    return re.search(r"(?<![A-Za-z])" + re.escape(skill.lower()) + r"(?![A-Za-z])", text.lower()) is not None


def proposal_features(text: str, job: dict, bid: float, prefs: HiddenPrefs,
                      persona_skills: set[str] | None, screening_answers: list[str] | None,
                      all_skill_names: list[str] | None = None) -> dict:
    t = text or ""
    low = t.lower()
    first = re.split(r"(?<=[.!?])\s+", t.strip(), maxsplit=1)[0].lower() if t.strip() else ""
    words = len(t.split())
    must = prefs.must_have or []
    m = sum(_mentions(t, s) for s in must) / max(1, len(must))
    sentences = re.split(r"(?<=[.!?])\s+", t)
    spec = min(1.0, sum(1 for s in sentences if re.search(r"\d", s)) / 2.0)
    generic = any(re.search(p, first) for p in GENERIC_PATTERNS) or any(
        re.search(p, low) for p in GENERIC_PATTERNS[4:8])
    title_words = {w for w in re.findall(r"[a-z]{5,}", (job.get("title") or "").lower())}
    personal = 1.0 if any(w in first for w in title_words) or (job.get("industry") or "x").lower() in low else 0.0
    qs = job.get("screening_questions") or []
    answered = 1.0 if not qs else min(1.0, len([a for a in (screening_answers or []) if len(a.split()) >= 8]) / len(qs))
    overprice = bid > prefs.ceiling * 1.0001 if bid else False
    too_long = words > 220
    contact = any(re.search(p, low) for p in CONTACT_PATTERNS)
    fabricated = 0
    if persona_skills is not None and all_skill_names:
        for s in all_skill_names:
            if s not in persona_skills and _mentions(t, s) and re.search(
                    r"(i|i've|i have|we)\s+(have\s+)?(built|used|shipped|delivered|worked|developed)[^.]*" + re.escape(s.lower()), low):
                fabricated += 1
    if re.search(r"\b(1[0-9]|[2-9][0-9])\+?\s+years", low):
        fabricated += 1
    return dict(must_have_cov=round(m, 3), specificity=round(spec, 3), generic=bool(generic),
                personal=personal, answered=round(answered, 3), overprice=bool(overprice),
                too_long=too_long, contact_leak=bool(contact), fabricated=fabricated, words=words)


def _seeded_rng(*parts: str) -> random.Random:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def decide(text: str, job: dict, bid: float, prefs: HiddenPrefs, persona_skills: set[str] | None = None,
           screening_answers: list[str] | None = None, run_seed: str = "0",
           all_skill_names: list[str] | None = None) -> ClientDecision:
    f = proposal_features(text, job, bid, prefs, persona_skills, screening_answers, all_skill_names)
    reasons: list[str] = []
    if f["contact_leak"]:
        return ClientDecision(False, False, False, 0.0, f, ["platform blocked: off-platform contact details"])
    z = -1.9
    z += 1.7 * f["must_have_cov"]
    z += 0.9 * f["specificity"]
    z += 0.4 * f["personal"]
    z += 0.5 * f["answered"]
    if f["generic"]:
        z -= 1.3 if prefs.dislikes_generic else 0.4
        reasons.append("generic opening")
    if f["overprice"]:
        z -= 1.0
        reasons.append("over budget ceiling")
    if f["too_long"] and prefs.prefers_concise:
        z -= 0.6
        reasons.append("too long")
    if f["must_have_cov"] < 0.5:
        reasons.append("did not address must-have skills")
    competition = 1.0 / (1.0 + 0.012 * float(job.get("proposals_count", 15)))
    p_reply = (1.0 / (1.0 + math.exp(-z))) * (0.55 + 0.45 * competition)
    rng = _seeded_rng(job.get("job_id", ""), hashlib.md5(text.encode()).hexdigest(), str(bid), run_seed)
    reply = rng.random() < p_reply
    p_int = 0.35 + 0.35 * f["must_have_cov"] + (0.0 if f["overprice"] else 0.15)
    interview = reply and rng.random() < p_int
    p_hire = 0.45 + (0.2 if not f["overprice"] else -0.2) - 0.3 * min(2, f["fabricated"])
    if f["fabricated"]:
        reasons.append("claims did not hold up in interview")
    hire = interview and rng.random() < max(0.02, p_hire)
    return ClientDecision(reply, interview, hire, round(p_reply, 4), f, reasons)
