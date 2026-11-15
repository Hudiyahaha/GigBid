"""Typed graph state with reducers wherever parallel branches write (C2).

Three things are kept apart:
  * State (this file): what one job / conversation needs right now.
  * Execution trace (`trace` field + audit log + OpenTelemetry spans): every tool call and observation.
  * Long-term memory (agent/memory/store.py): only promoted knowledge, written by explicit rules.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
            out[k] = out[k] + v
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def merge_evidence(a: list | None, b: list | None) -> list:
    """Union of evidence items by item_id, keeping the higher score."""
    seen: dict[str, dict] = {e["item_id"]: e for e in (a or [])}
    for e in b or []:
        if e["item_id"] not in seen or e.get("score", 0) > seen[e["item_id"]].get("score", 0):
            seen[e["item_id"]] = e
    return sorted(seen.values(), key=lambda e: -e.get("score", 0))


def last_value(a: Any, b: Any) -> Any:
    return b if b is not None else a


_SEVERITY = {"dead_letter": 5, "needs_attention": 4, "queued_retry": 3, "blocked": 2}


def status_reducer(a: str | None, b: str | None) -> str | None:
    """Parallel branches may both set a status; the most severe wins, otherwise the newest value."""
    if b is None:
        return a
    sa, sb = _SEVERITY.get(a or "", 0), _SEVERITY.get(b, 0)
    if sa and sb and sa > sb:  # two failures in one superstep: keep the worse one
        return a
    return b


def text_join(a: str | None, b: str | None) -> str | None:
    if not b:
        return a
    if not a or a == b:
        return b
    return f"{a}; {b}"


class BidState(TypedDict, total=False):
    # identity
    thread_id: str
    user_id: str
    persona: str
    trace_id: str
    strategy: str
    # the job (untrusted input)
    job_id: str
    job: dict
    policy: dict          # local rules + live marketplace policy (limits, Connects surcharges)
    prefs: dict           # user's rates, budgets, autonomy (snapshot at thread start)
    # parallel analyses (each branch owns one key)
    job_spec: dict
    risk: dict
    fit: dict
    evidence: Annotated[list[dict], merge_evidence]
    # decision + downstream
    decision: dict
    price: dict
    draft: dict
    drafts: Annotated[list[dict], operator.add]
    verification: Annotated[dict, merge_dict]
    critiques: Annotated[list[dict], operator.add]
    revisions: int
    compliance: dict
    dry_run: dict
    approval: dict
    submission: dict
    outcome: dict
    status: Annotated[str, status_reducer]
    attention_reason: Annotated[str, text_join]
    # bookkeeping
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[dict], operator.add]
    steps: Annotated[int, operator.add]
    usage: Annotated[dict, merge_dict]


class ConversationState(TypedDict, total=False):
    thread_id: str
    user_id: str
    persona: str
    trace_id: str
    marketplace_thread_id: str
    job: dict
    messages: list[dict]
    intent: dict
    slots: list[str]
    reply: dict
    compliance: dict
    dry_run: dict
    approval: dict
    sent: dict
    status: Annotated[str, status_reducer]
    attention_reason: Annotated[str, text_join]
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[dict], operator.add]
    steps: Annotated[int, operator.add]
    usage: Annotated[dict, merge_dict]
