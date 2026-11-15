"""Proposal Writer (Portfolio read: search_evidence, get_case_study, similar_proposals).

Every experience claim carries an [E:item_id] citation; citations are stripped from the client-facing text
and shown on hover in the Proposal studio. Style memory rules are applied after drafting (deterministically),
so learned edits take effect even when the model ignores them.
"""

from __future__ import annotations

import json
import re

from agent import config, llm, mcp_client
from agent.guardrails import delimit
from agent.memory import store as memory
from agent.nodes.base import node

CITE = re.compile(r"\s*\[E:([A-Za-z0-9_\-.]+)\]")


def strip_citations(text: str) -> str:
    return re.sub(r"\s+([.,;:!?])", r"\1", CITE.sub("", text or "")).strip()


def cited_ids(text: str) -> list[str]:
    return list(dict.fromkeys(CITE.findall(text or "")))


def _outcome_sentence(snippet: str) -> str | None:
    m = re.search(r"(?:The project|In production this|this) ((?:cut|raised|reduced|auto-routed|reached|achieved|beat|lifted|"
                  r"moved|grew|served|removed|kept|sold|onboarded|replaced|re-allocated|found|saved|merged|made|gave|processed)[^.]*)\.",
                  snippet or "")
    return m.group(1).strip() if m else None


def heuristic_draft(state: dict, evidence: list[dict], strategy: str) -> dict:
    """Template writer used when no LLM is available. Grounded by construction: it only restates evidence."""
    job, spec = state["job"], state.get("job_spec") or {}
    fit = state.get("fit") or {}
    strong = [m for m in fit.get("matrix", []) if m.get("strength") == "strong" and m.get("evidence_ids")]
    by_id = {e["item_id"]: e for e in evidence}
    focus = (strong[0]["requirement"] if strong else (spec.get("requirements") or [{"skill": job.get("title", "")}])[0].get("skill", ""))
    focus = re.sub(r"^(must have hands-on experience with|strong|experience with|we need someone who|you will be working mainly in)\s*",
                   "", focus.rstrip("."), flags=re.I)
    lines = []
    if strategy == "question_first":
        lines.append(f"Before anything else: what would a successful {job.get('title', 'project').lower()} look like for you in the first month?")
    else:
        lines.append(f"Your {job.get('title', 'project')} needs someone who can handle {focus[:120].lower()} from day one.")
    used = []
    for m in strong[:2] if strategy != "question_first" else strong[:1]:
        iid = next((i for i in m["evidence_ids"] if i in by_id and i not in used), None)
        if not iid:
            continue
        used.append(iid)
        ev = by_id[iid]
        ind = f" for a {ev['client_industry']} client" if ev.get("client_industry") else ""
        lines.append(f"I delivered a closely related project, {ev['title']}{ind} [E:{iid}].")
        oc = _outcome_sentence(ev.get("snippet", ""))
        if oc:
            lines.append(f"That project {oc} [E:{iid}].")
    if strategy == "question_first":
        lines.append("My plan: agree the scope and success metric in week one, ship a working first version for your feedback, "
                     "then harden and document it.")
    else:
        lines.append("I would start by agreeing the scope and the success metric in week one, then ship a first working version "
                     "for your feedback before polishing and documenting it.")
    lines.append("Could you share a sample of your current setup so I can confirm the plan and timeline?")
    answers = []
    for q in spec.get("screening_questions") or job.get("screening_questions") or []:
        ev = by_id.get(used[0]) if used else (evidence[0] if evidence else None)
        if "availability" in q.lower():
            a = "I can commit around 20 hours per week and reply to messages within one business day."
        elif ev:
            a = (f"The closest example is {ev['title']} [E:{ev['item_id']}]. I would apply the same approach here: "
                 f"clarify the goal, deliver in small reviewed steps, and measure the result against the agreed metric.")
        else:
            a = "I would clarify the goal first, deliver in small reviewed steps, and measure the result against an agreed metric."
        answers.append({"question": q, "answer": a})
    return {"cover_letter": " ".join(lines), "screening_answers": answers, "evidence_ids": used}


@node("writer")
async def writer(state: dict) -> dict:
    job = state["job"]
    user = state.get("user_id", "local")
    strategy = state.get("strategy") or (state.get("prefs") or {}).get("strategy") or config.get("writer.default_strategy")
    evidence = (state.get("evidence") or [])[:8]
    try:
        past = await mcp_client.call("writer", "similar_proposals", {"query": job.get("title", ""), "k": 2})
        past_items = past.get("items", [])
    except Exception:  # noqa: BLE001 - optional context
        past_items = []
    style_rules = await memory.style_rules(user)
    outcome_hints = await memory.outcome_hints(user, job.get("category", ""))
    crit = (state.get("critiques") or [])[-1:] or [{}]
    revision = crit[0].get("revision_instructions", "") if state.get("revisions") else ""
    ev_view = [{"item_id": e["item_id"], "type": e["type"], "title": e["title"], "industry": e.get("client_industry"),
                "snippet": e.get("snippet", "")[:400]} for e in evidence]
    variables = {
        "strategy": config.get(f"writer.strategies.{strategy}", strategy),
        "job_spec": {k: (state.get("job_spec") or {}).get(k) for k in ("title", "deliverables", "requirements", "screening_questions", "hidden_needs")},
        "price": {k: (state.get("price") or {}).get(k) for k in ("amount", "pay_type")},
        "evidence": json.dumps(ev_view, ensure_ascii=False),
        "outcome_hints": json.dumps({"memory": outcome_hints, "past": [p.get("snippet", "")[:300] for p in past_items]}),
        "style_rules": style_rules or "none yet", "revision": revision,
        "job": delimit("job_post", job.get("clean_description") or job.get("description", "")),
    }
    data, meta = await llm.call_json("writer", "writer", variables, None,
                                     heuristic=lambda: heuristic_draft(state, evidence, strategy), max_tokens=1800)
    cover = data.get("cover_letter") or ""
    answers = [a if isinstance(a, dict) else {"question": "", "answer": str(a)} for a in data.get("screening_answers") or []]
    cover = memory.apply_style(cover, style_rules)
    version = len(state.get("drafts") or []) + 1
    ids = list(dict.fromkeys(cited_ids(cover) + [i for a in answers for i in cited_ids(a.get("answer", ""))]))
    draft = {"job_id": job["job_id"], "cover_letter": cover, "screening_answers": answers, "evidence_ids": ids,
             "version": version, "strategy": strategy, "claims": []}
    return {"draft": draft, "drafts": [draft], "trace": [{"type": "llm", "node": "writer", **meta}]}
