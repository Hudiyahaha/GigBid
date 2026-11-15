r"""Conversation graph (one thread per client conversation), C1.

    fetch_thread -> intent -> slots -> client_liaison -> compliance -> preview -> human_approval
                                                             ^                      |--approve--> executor -> END
                                                             \-------- edit --------|--reject--> END
"""

from __future__ import annotations

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agent import config
from agent.nodes.base import Transient
from agent.nodes.client_liaison import (classify_intent, draft_reply, execute_message, fetch_thread, find_slots,
                                        reply_approval, reply_compliance, reply_preview)
from agent.state import ConversationState

STOP = {"needs_attention", "dead_letter", "queued_retry", "skipped"}


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    retry = RetryPolicy(max_attempts=int(config.get("budgets.node_retries", 3)), retry_on=(Transient, httpx.TransportError))
    t = float(config.get("budgets.node_timeout_s", 180))
    for name, fn in [("fetch_thread", fetch_thread), ("intent", classify_intent), ("slots", find_slots),
                     ("client_liaison", draft_reply), ("compliance", reply_compliance), ("preview", reply_preview),
                     ("executor", execute_message)]:
        g.add_node(name, fn, retry_policy=retry, timeout=t)
    g.add_node("human_approval", reply_approval)
    g.add_edge(START, "fetch_thread")
    g.add_conditional_edges("fetch_thread", lambda s: END if s.get("status") in STOP else "intent", ["intent", END])
    g.add_conditional_edges("intent", lambda s: END if s.get("status") in STOP else "slots", ["slots", END])
    g.add_edge("slots", "client_liaison")
    g.add_edge("client_liaison", "compliance")
    g.add_conditional_edges("compliance", lambda s: END if s.get("status") in STOP else "preview", ["preview", END])
    g.add_edge("preview", "human_approval")

    def after(s):
        if s.get("status") == "approved":
            return "executor"
        if (s.get("approval") or {}).get("action") == "edit":
            return "compliance"
        return END
    g.add_conditional_edges("human_approval", after, ["executor", "compliance", END])
    g.add_edge("executor", END)
    return g.compile(checkpointer=checkpointer, store=store)
