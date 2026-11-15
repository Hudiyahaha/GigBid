"""Compliance Guard (no MCP access). Enforces data/policy_pack/rules.yaml plus the live marketplace policy:
redacts contact details, guarantees and inflated experience; BLOCKS off-platform payment and free work; enforces
length limits. Also re-checks every human edit. A small model looks for subtle violations (shown as warnings)."""

from __future__ import annotations

import re

from agent import llm, policy
from agent.handoffs import ComplianceVerdict, Redaction
from agent.nodes.base import node
from agent.nodes.writer import strip_citations


def check_text(text: str, pol: dict) -> tuple[str, list[Redaction], list[str]]:
    reds: list[Redaction] = []
    blocked: list[str] = []
    for rule in policy.rules().get("forbidden_patterns", []):
        for rx in rule["_rx"]:
            for m in list(rx.finditer(text)):
                if rule["action"] == "block":
                    blocked.append(f"{rule['id']}: {rule['message']} ('{m.group(0)}')")
                else:
                    reds.append(Redaction(rule_id=rule["id"], original=m.group(0)))
            if rule["action"] == "redact":
                text = rx.sub("", text)
    text = re.sub(r"\s{2,}", " ", re.sub(r"\s+([.,;:!?])", r"\1", text)).strip()
    limits = (pol or {}).get("limits") or policy.rules().get("limits", {})
    plain = strip_citations(text)
    mx = limits.get("max_cover_letter_chars")
    if mx and len(plain) > int(mx):
        blocked.append(f"length: cover letter is {len(plain)} characters; policy v{(pol or {}).get('marketplace_version') or policy.rules().get('version')} allows {mx}")
    return text, reds, list(dict.fromkeys(blocked))


async def run_compliance(text: str, pol: dict) -> tuple[ComplianceVerdict, dict]:
    cleaned, reds, blocked = check_text(text, pol)
    warnings: list[str] = []
    messages = [r["message"] for r in policy.rules().get("forbidden_patterns", [])] + list((pol or {}).get("marketplace_rules", []))

    def heuristic():
        return {"violations": []}
    res, meta = await llm.call_json("compliance", "compliance", {"policy": messages, "text": strip_citations(cleaned)},
                                    None, heuristic=heuristic, max_tokens=400)
    for v in (res.get("violations") or []) if isinstance(res, dict) else []:
        if isinstance(v, dict) and v.get("quote"):
            warnings.append(f"possible {v.get('rule_id', 'policy')} issue: '{v['quote'][:120]}'")
    verdict = ComplianceVerdict(allowed=not blocked, blocked_reasons=blocked, redactions=reds, cleaned_text=cleaned,
                                rules_version=int(policy.rules().get("version", 1)))
    return verdict, {"meta": meta, "warnings": warnings}


@node("compliance")
async def compliance(state: dict) -> dict:
    draft = dict(state["draft"])
    pol = state.get("policy") or {}
    verdict, extra = await run_compliance(draft["cover_letter"], pol)
    answers = []
    all_blocked = list(verdict.blocked_reasons)
    reds = list(verdict.redactions)
    for a in draft.get("screening_answers", []):
        cleaned, r2, b2 = check_text(a.get("answer", ""), {})
        answers.append({**a, "answer": cleaned})
        reds += r2
        all_blocked += b2
    draft["cover_letter"] = verdict.cleaned_text
    draft["screening_answers"] = answers
    v = {**verdict.model_dump(), "blocked_reasons": list(dict.fromkeys(all_blocked)), "allowed": not all_blocked,
         "redactions": [r.model_dump() for r in reds], "warnings": extra["warnings"]}
    out = {"draft": draft, "compliance": v, "trace": [{"type": "llm", "node": "compliance", **extra["meta"]}]}
    out["status"] = "blocked" if all_blocked else "awaiting_approval"
    return out
