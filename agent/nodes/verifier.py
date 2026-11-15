"""Claim verification node (Portfolio read: get_item). Runs after every draft, before the Critic."""

from __future__ import annotations

import asyncio
import json

from agent import llm, mcp_client
from agent.nodes.base import node
from rag import verify as V


async def load_evidence(ids: list[str]) -> dict[str, dict]:
    async def one(i):
        try:
            d = await mcp_client.call("verifier", "get_item", {"id": i})
            return i, {"text": d.get("text", ""), "skills": d.get("skills", []), "title": d.get("title", "")}
        except Exception:  # noqa: BLE001 - missing item => claim citing it is unsupported
            return i, None
    pairs = await asyncio.gather(*(one(i) for i in ids))
    return {i: d for i, d in pairs if d}


@node("verifier")
async def verifier(state: dict) -> dict:
    draft = dict(state["draft"])
    answers = [dict(a) for a in draft.get("screening_answers", [])]
    all_text = draft["cover_letter"] + " " + " ".join(a.get("answer", "") for a in answers)
    evidence = await load_evidence(list(dict.fromkeys(V.CITE.findall(all_text))))
    checks = V.verify_text(draft["cover_letter"], evidence)
    ans_checks = [V.verify_text(a.get("answer", ""), evidence, offset=1000 * (k + 1)) for k, a in enumerate(answers)]
    flat = checks + [c for cs in ans_checks for c in cs]
    before = V.unsupported_rate(flat)
    rewrites: dict[int, str] = {}
    trace = []
    doubtful = [c for c in flat if c.status != "supported" or not c.cited]
    if flat:
        view = "\n".join(f"{c.index}. {c.text}" for c in flat)
        ev_view = json.dumps({i: d["text"][:1200] for i, d in evidence.items()}, ensure_ascii=False)

        def heuristic():
            return {"claims": [{"index": c.index, "status": c.status, "rewritten": None, "reason": c.reason} for c in flat]}
        res, meta = await llm.call_json("verifier", "verifier", {"claims": view, "evidence": ev_view}, None, heuristic=heuristic)
        trace.append({"type": "llm", "node": "verifier", **meta})
        if meta.get("model") != "heuristic":
            by = {int(r.get("index", -1)): r for r in (res.get("claims") or []) if isinstance(r, dict)}
            for c in flat:
                r = by.get(c.index)
                if not r or r.get("status") not in ("supported", "partial", "unsupported"):
                    continue
                # an LLM may not upgrade a claim the deterministic check found uncited or unknown
                if c.status == "unsupported" and not c.cited:
                    continue
                if r["status"] == "supported" and c.status != "supported" and c.cited:
                    c.status, c.reason = "partial", f"LLM says supported, but: {c.reason}"
                elif r["status"] != c.status:
                    c.status, c.reason = r["status"], f"LLM: {r.get('reason', '')}"[:200]
                if c.status == "partial" and r.get("rewritten") and V.CITE.search(r["rewritten"]):
                    rewrites[c.index] = r["rewritten"]
    draft["cover_letter"] = V.apply(draft["cover_letter"], checks, rewrites)
    for k, a in enumerate(answers):
        a["answer"] = V.apply(a.get("answer", ""), ans_checks[k], rewrites, offset=1000 * (k + 1)) or \
            "I would clarify this with you on a short call before committing to an approach."
    after_text = draft["cover_letter"] + " " + " ".join(a["answer"] for a in answers)
    after_checks = V.verify_text(after_text, evidence)
    draft["screening_answers"] = answers
    draft["claims"] = [{"text": c.text, "status": c.status, "evidence_ids": c.cited,
                        "action": "kept" if c.status == "supported" else ("rewritten" if c.index in rewrites else "removed"),
                        "rewritten": rewrites.get(c.index), "reason": c.reason} for c in flat]
    ver = {"claims": len(flat), "unsupported_before": sum(c.status == "unsupported" for c in flat),
           "partial_before": sum(c.status == "partial" for c in flat), "unsupported_rate_before": before,
           "unsupported_rate_after": V.unsupported_rate(after_checks), "removed": sum(c.status == "unsupported" for c in flat),
           "rewritten": len(rewrites), "doubtful": len(doubtful)}
    return {"draft": draft, "verification": {f"v{draft.get('version', 1)}": ver, "last": ver}, "trace": trace}
