"""Critic (Portfolio read). Checks grounding, personalisation, length, opening and screening answers.
Sends the draft back to the Writer with reasons at most `budgets.max_revisions` times."""

from __future__ import annotations

import re

from agent import config, llm
from agent.handoffs import Critique
from agent.nodes.base import node
from agent.nodes.writer import strip_citations

GENERIC = re.compile(r"(?i)(dear sir|madam|to whom it may concern|i am writing to|passionate|hard[- ]?working|perfect fit|"
                     r"i have read your (job|post)|i am the best|look no further)")


def heuristic_critique(state: dict) -> dict:
    draft, spec = state["draft"], state.get("job_spec") or {}
    text = strip_citations(draft["cover_letter"])
    words = len(text.split())
    ver = (state.get("verification") or {}).get("last") or {}
    n = max(1, ver.get("claims", 0))
    grounding = 1.0 - (ver.get("unsupported_before", 0) + 0.5 * ver.get("partial_before", 0)) / n if ver.get("claims") else 0.5
    if ver.get("unsupported_rate_after", 0) == 0 and ver.get("claims"):
        grounding = max(grounding, 0.9)
    keys = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z.+#/-]{3,}", spec.get("title", ""))}
    keys |= {r.get("skill", "").lower() for r in spec.get("requirements", [])[:6] if len(r.get("skill", "")) < 30}
    keys.discard("")
    low = text.lower()
    personal = sum(1 for k in keys if k in low) / max(1, len(keys))
    issues = []
    first = re.split(r"(?<=[.!?])\s+", text)[0] if text else ""
    if GENERIC.search(first):
        issues.append("generic opening - open with the client's problem")
    if words < 100 or words > 260:
        issues.append(f"length {words} words (target 120-220)")
    if grounding < 0.85:
        issues.append(f"grounding {grounding:.2f}: remove or cite unsupported claims")
    if personal < 0.3:
        issues.append("not specific to this job: mention its deliverables and requirements")
    qs = spec.get("screening_questions") or []
    if len([a for a in draft.get("screening_answers", []) if len(a.get("answer", "").split()) >= 8]) < len(qs):
        issues.append("a screening question is unanswered")
    return {"passed": not issues, "grounding": round(grounding, 3), "personalisation": round(min(1, personal * 1.5), 3),
            "length_ok": 100 <= words <= 260, "issues": issues, "revision_instructions": "; ".join(issues)}


@node("critic")
async def critic(state: dict) -> dict:
    h = heuristic_critique(state)
    draft = state["draft"]
    variables = {"job_spec": {k: (state.get("job_spec") or {}).get(k) for k in ("title", "requirements", "screening_questions", "deliverables")},
                 "verification": (state.get("verification") or {}).get("last"),
                 "draft": {"cover_letter": strip_citations(draft["cover_letter"]), "screening_answers": draft.get("screening_answers")}}
    c, meta = await llm.call_json("critic", "critic", variables, Critique, heuristic=lambda: h)
    # hard checks cannot be overruled by the model
    hard = [i for i in h["issues"] if i.startswith(("length", "generic", "a screening", "grounding"))]
    if hard:
        c.passed = False
        c.issues = list(dict.fromkeys(c.issues + hard))
        c.revision_instructions = "; ".join(dict.fromkeys([c.revision_instructions] + hard)).strip("; ")
    c.grounding = min(c.grounding, h["grounding"]) if meta.get("model") != "heuristic" else c.grounding
    revisions = int(state.get("revisions", 0))
    max_rev = int(config.get("budgets.max_revisions", 2))
    out = {"critiques": [{**c.model_dump(), "version": draft.get("version", 1)}],
           "trace": [{"type": "llm", "node": "critic", **meta}]}
    if not c.passed and revisions < max_rev:
        out["revisions"] = revisions + 1
    return out


def route_after_critic(state: dict) -> str:
    last = (state.get("critiques") or [{}])[-1]
    if state.get("status") in ("needs_attention", "dead_letter", "queued_retry"):
        return "end"
    if not last.get("passed") and int(state.get("revisions", 0)) > len(state.get("drafts") or []) - 1:
        return "writer"
    return "compliance"
