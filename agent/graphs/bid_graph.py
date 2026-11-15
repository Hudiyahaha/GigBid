r"""Bid graph (one thread per job), hand-written LangGraph StateGraph (R3, C1).

    scout --Send--> job_analyst  --\
          --Send--> risk_assessor --> decision --bid--> pricing --worth--> writer -> verifier -> critic
          --Send--> fit_matcher  --/        \--skip/watch--> END            ^                    |
                                                                            \---- revise (<=2) --/
    critic -> compliance -> preview -> human_approval --approve--> executor -> END
                    ^                        |--edit--> compliance (re-check)
                    \------------------------|--reject--> END
"""

from __future__ import annotations

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from agent import config
from agent.nodes.analyst import job_analyst
from agent.nodes.approval import execute_proposal, human_approval, preview, route_after_approval
from agent.nodes.base import Transient
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.decision import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.scout import scout_intake
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState

STOP = {"needs_attention", "dead_letter", "queued_retry"}


def fan_out(state: dict):
    if state.get("status") in STOP:
        return END
    return [Send("job_analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


def after_decision(state: dict) -> str:
    if state.get("status") in STOP:
        return END
    return "pricing" if (state.get("decision") or {}).get("action") == "bid" else END


def after_pricing(state: dict) -> str:
    if state.get("status") in STOP | {"skipped"}:
        return END
    return "writer"


def after_critic(state: dict) -> str:
    r = route_after_critic(state)
    return END if r == "end" else r


def after_compliance(state: dict) -> str:
    return END if state.get("status") in STOP else "preview"


def after_approval(state: dict) -> str:
    r = route_after_approval(state)
    return {"execute": "executor", "compliance": "compliance", "human_approval": "human_approval"}.get(r, END)


def build_bid_graph(checkpointer=None, store=None, interrupt_before: list[str] | None = None):
    g = StateGraph(BidState)
    retry = RetryPolicy(max_attempts=int(config.get("budgets.node_retries", 3)), retry_on=(Transient, httpx.TransportError))
    t = float(config.get("budgets.node_timeout_s", 180))
    for name, fn in [("scout", scout_intake), ("job_analyst", job_analyst), ("risk_assessor", risk_assessor),
                     ("fit_matcher", fit_matcher), ("decision", decide), ("pricing", pricing), ("writer", writer),
                     ("verifier", verifier), ("critic", critic), ("compliance", compliance), ("preview", preview),
                     ("executor", execute_proposal)]:
        g.add_node(name, fn, retry_policy=retry, timeout=t)
    g.add_node("human_approval", human_approval)
    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", fan_out, ["job_analyst", "risk_assessor", "fit_matcher", END])
    for n in ("job_analyst", "risk_assessor", "fit_matcher"):
        g.add_edge(n, "decision")
    g.add_conditional_edges("decision", after_decision, ["pricing", END])
    g.add_conditional_edges("pricing", after_pricing, ["writer", END])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", END])
    g.add_conditional_edges("compliance", after_compliance, ["preview", END])
    g.add_edge("preview", "human_approval")
    g.add_conditional_edges("human_approval", after_approval, ["executor", "compliance", "human_approval", END])
    g.add_edge("executor", END)
    return g.compile(checkpointer=checkpointer, store=store, interrupt_before=interrupt_before)
