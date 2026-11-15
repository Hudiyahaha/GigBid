"""Client Liaison (Marketplace read, write after approval; Workspace). Nodes of the conversation graph."""

from __future__ import annotations

import re
import time

from langgraph.types import interrupt

from agent import approval_token, llm, mcp_client
from agent.guardrails import delimit, injection_signals, strip_injections
from agent.handoffs import MessageIntent
from agent.marketplace_port import MarketplacePort
from agent.nodes.base import node
from agent.nodes.compliance import run_compliance
from agent.nodes.risk_assessor import rule_flags


@node("fetch_thread")
async def fetch_thread(state: dict) -> dict:
    out = await MarketplacePort("client_liaison").list_messages(state["marketplace_thread_id"])
    msgs = out.get("messages", [])
    for m in msgs:
        if m.get("sender") == "client":
            clean, removed = strip_injections(m.get("body", ""))
            m["clean_body"], m["injection_removed"] = clean, removed
    return {"messages": msgs, "status": "analysing", "job": state.get("job") or {"job_id": out.get("thread", {}).get("job_id")}}


def heuristic_intent(text: str) -> dict:
    low = text.lower()
    if rule_flags(text):
        intent = "scam_signal"
    elif re.search(r"\b(call|schedule|meeting|interview|zoom|chat live)\b", low):
        intent = "interview_request"
    elif re.search(r"(\$\s?\d|budget|rate|price|discount|would you consider|lower)", low):
        intent = "negotiation"
    elif "?" in text:
        intent = "question"
    else:
        intent = "other"
    return {"intent": intent, "confidence": 0.6, "summary": text[:120], "injection_detected": bool(injection_signals(text))}


@node("intent")
async def classify_intent(state: dict) -> dict:
    last = next((m for m in reversed(state.get("messages", [])) if m.get("sender") == "client"), None)
    if not last:
        return {"status": "skipped", "attention_reason": "no client message to answer"}
    raw = last.get("body", "")
    rules = heuristic_intent(raw)
    res, meta = await llm.call_json("intent", "intent", {"message": delimit("client_message", raw)}, MessageIntent,
                                    heuristic=lambda: rules)
    if rules["intent"] == "scam_signal":  # deterministic scam rules cannot be overruled
        res.intent = "scam_signal"
    res.injection_detected = res.injection_detected or rules["injection_detected"]
    return {"intent": res.model_dump(), "trace": [{"type": "llm", "node": "intent", **meta}]}


@node("slots")
async def find_slots(state: dict) -> dict:
    if (state.get("intent") or {}).get("intent") != "interview_request":
        return {"slots": []}
    out = await mcp_client.call("client_liaison", "free_slots", {"days": 5, "duration_min": 30, "max_slots": 3})
    return {"slots": out.get("slots", [])}


def heuristic_reply(state: dict) -> dict:
    intent = (state.get("intent") or {}).get("intent", "other")
    prefs, prop = state.get("prefs") or {}, state.get("proposal") or {}
    title = (state.get("job") or {}).get("title") or "your project"
    if intent == "interview_request":
        slots = ", ".join(s.replace("T", " ")[:16] + " UTC" for s in state.get("slots", [])) or "any weekday afternoon (UTC)"
        text = f"Thanks for the invitation, I'd be glad to talk about {title.lower()}. I'm free at {slots}. Which works best for you?"
    elif intent == "negotiation":
        last = next((m.get("clean_body", m.get("body", "")) for m in reversed(state.get("messages", [])) if m.get("sender") == "client"), "")
        offers = [float(x.replace(",", "")) for x in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", last)]
        bid = float(prop.get("bid") or (offers[0] if offers else 0) or 0)
        offer = min(offers) if offers else bid
        floor = float(prefs.get("min_project") if prop.get("pay_type", "fixed") == "fixed" else prefs.get("hourly_floor", 0) or 0)
        counter = max(floor, round((bid + offer) / 2, 0)) if bid else floor
        text = (f"Thanks for being open about the budget. I can do ${counter:.0f} if we keep the scope to the deliverables in the "
                f"post; that keeps the quality where it needs to be. Shall I outline the milestones on that basis?")
    elif intent == "scam_signal":
        text = ("Thanks for the message. I keep all communication and payments on this platform, as its terms require, "
                "so let's continue the conversation here.")
    elif intent == "question":
        text = ("Good question. I'd start with a short discovery step to confirm the requirements and success metric, then "
                "deliver in small reviewed milestones so you can steer early. Happy to go through it on a quick call.")
    else:
        text = "Thanks for your message! Let me know how you'd like to proceed and I'll get back to you promptly."
    return {"text": text, "notes": ["heuristic reply"]}


@node("client_liaison")
async def draft_reply(state: dict) -> dict:
    prefs, prop = state.get("prefs") or {}, state.get("proposal") or {}
    convo = "\n".join(f"{m.get('sender')}: {m.get('clean_body', m.get('body', ''))}" for m in state.get("messages", [])[-8:])
    variables = {"intent": (state.get("intent") or {}).get("intent"), "job_title": (state.get("job") or {}).get("title"),
                 "proposal": (prop.get("cover_letter") or "")[:600], "floor": prefs.get("min_project") or prefs.get("hourly_floor"),
                 "bid": prop.get("bid"), "slots": state.get("slots", []), "conversation": delimit("conversation", convo)}
    res, meta = await llm.call_json("client_liaison", "client_liaison", variables, None, heuristic=lambda: heuristic_reply(state))
    text = (res.get("text") if isinstance(res, dict) else None) or heuristic_reply(state)["text"]
    return {"reply": {"thread_id": state["marketplace_thread_id"], "text": text, "slots": state.get("slots", []),
                      "intent": (state.get("intent") or {}).get("intent"), "notes": res.get("notes", []) if isinstance(res, dict) else []},
            "trace": [{"type": "llm", "node": "client_liaison", **meta}]}


@node("compliance")
async def reply_compliance(state: dict) -> dict:
    verdict, extra = await run_compliance(state["reply"]["text"], state.get("policy") or {})
    reply = {**state["reply"], "text": verdict.cleaned_text}
    return {"reply": reply, "compliance": {**verdict.model_dump(), "warnings": extra["warnings"]},
            "status": "awaiting_approval" if verdict.allowed else "blocked"}


@node("preview")
async def reply_preview(state: dict) -> dict:
    payload = {"thread_id": state["marketplace_thread_id"], "body": state["reply"]["text"]}
    res = await MarketplacePort("approval_executor").send_message(payload["thread_id"], payload["body"],
                                                                   f"{state['thread_id']}:dry", dry_run=True)
    return {"dry_run": {"payload": payload, "preview": res.get("preview")}}


@node("human_approval")
async def reply_approval(state: dict) -> dict:
    decision = interrupt({"kind": "message", "thread_id": state["thread_id"], "send_payload": state["dry_run"]["payload"],
                          "preview": state["dry_run"].get("preview"), "reply": state["reply"], "intent": state.get("intent"),
                          "messages": state.get("messages", [])[-8:], "compliance": state.get("compliance"),
                          "can_approve": bool((state.get("compliance") or {}).get("allowed"))})
    action = (decision or {}).get("action")
    rec = {**(decision or {}), "decided_at": time.time()}
    if action == "approve" and (state.get("compliance") or {}).get("allowed"):
        return {"approval": rec, "status": "approved"}
    if action == "edit":
        return {"reply": {**state["reply"], "text": decision.get("edited_text") or state["reply"]["text"]},
                "approval": rec, "status": "analysing"}
    return {"approval": {**rec, "action": "reject"}, "status": "rejected"}


@node("executor")
async def execute_message(state: dict) -> dict:
    token = (state.get("approval") or {}).get("approval_token")
    payload = state["dry_run"]["payload"]
    h = approval_token.payload_hash(payload)[:12]
    res = await MarketplacePort("approval_executor").send_message(payload["thread_id"], payload["body"],
                                                                   f"{state['thread_id']}:send:{h}", approval_token=token)
    hold = None
    slot = (state.get("approval") or {}).get("chosen_slot") or (state.get("slots") or [None])[0]
    if (state.get("intent") or {}).get("intent") == "interview_request" and slot:
        hold = await mcp_client.call("approval_executor", "create_interview_hold",
                                     {"start": slot, "title": f"Interview: {(state.get('job') or {}).get('title', 'client')}",
                                      "idempotency_key": f"{state['thread_id']}:hold:{h}"})
    return {"sent": {**(res.get("result") or {}), "hold": hold, "idempotent_replay": bool(res.get("idempotent_replay"))},
            "status": "sent"}
