"""Explicit promotion rules (R7). Raw edits and outcomes live in the database (apps/api/db.py: Edit, Outcome);
only these functions may write long-term memory, and only when the evidence threshold in config is met.

STYLE rule: an edit pattern is promoted when it occurs in >= memory.style.min_occurrences approved drafts across
>= memory.style.min_distinct_jobs different jobs. Patterns: cut_first_sentence, ban_word:<w>, replace:<a>-><b>,
max_words (the user consistently shortens drafts by >20%).

OUTCOME rule: a category insight is promoted when the category has >= memory.outcome.min_samples_per_category
submitted proposals and the best strategy's reply rate beats the other by >= memory.outcome.min_reply_rate_delta.
"""

from __future__ import annotations

import difflib
import re
import time
from collections import defaultdict

from sqlalchemy import select

from agent import config
from agent.memory import store as memory

STOP = set("that this with from your have will would about there their them they what which when where into also "
           "just very more most some such than then only over well".split())


def _sents(t: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", (t or "").strip()) if s]


def analyse_edit(before: str, after: str) -> list[dict]:
    """Turn a before/after pair into candidate style patterns (not memory yet)."""
    ops: list[dict] = []
    bs = _sents(before)
    if len(bs) >= 2 and bs[0] not in after and any(s in after for s in bs[1:3]):
        ops.append({"key": "cut_first_sentence", "op": "cut_first_sentence", "rule": "Always cut the first sentence"})
    bw, aw = re.findall(r"[A-Za-z']+", before.lower()), re.findall(r"[A-Za-z']+", after.lower())
    aset = set(aw)
    removed = [w for w in dict.fromkeys(bw) if len(w) >= 5 and w not in STOP and w not in aset]
    for w in removed[:8]:
        ops.append({"key": f"ban_word:{w}", "op": "ban_word", "word": w, "rule": f"Never say '{w}'"})
    sm = difflib.SequenceMatcher(a=before.split(), b=after.split())
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and i2 - i1 <= 3 and j2 - j1 <= 3:
            a = " ".join(before.split()[i1:i2]).strip(".,;:!?").lower()
            b = " ".join(after.split()[j1:j2]).strip(".,;:!?")
            if a and b and a != b.lower():
                ops.append({"key": f"replace:{a}->{b.lower()}", "op": "replace", "from": a, "to": b,
                            "rule": f"Write '{b}' instead of '{a}'"})
    if len(aw) < 0.8 * len(bw) and len(bw) > 60:
        n = int(round(len(aw), -1))
        ops.append({"key": "max_words", "op": "max_words", "n": n, "rule": f"Keep cover letters under ~{n} words"})
    return ops


def record_edit(user_id: str, job_id: str, before: str, after: str) -> list[dict]:
    """Store the raw edit (diff + candidate patterns). This is NOT memory."""
    from apps.api.db import Edit, session
    ops = analyse_edit(before, after)
    with session() as s:
        s.add(Edit(user_id=user_id, job_id=job_id, before=before, after=after, ops=ops))
    return ops


async def promote_style(user_id: str) -> list[str]:
    from apps.api.db import Edit, session
    cfg = config.get("memory.style", {}) or {}
    min_occ, min_jobs, cap = int(cfg.get("min_occurrences", 3)), int(cfg.get("min_distinct_jobs", 3)), int(cfg.get("max_items", 25))
    support: dict[str, dict] = {}
    jobs: dict[str, set] = defaultdict(set)
    with session() as s:
        rows = s.execute(select(Edit).where(Edit.user_id == user_id)).scalars().all()
    for e in rows:
        for op in e.ops or []:
            support.setdefault(op["key"], {**op, "count": 0, "edit_ids": []})
            support[op["key"]]["count"] += 1
            support[op["key"]]["edit_ids"].append(e.id)
            jobs[op["key"]].add(e.job_id)
    st = memory.get()
    if st is None:
        return []
    existing = {it.key for it in await st.asearch(("style", user_id), limit=200)}
    promoted = []
    for key, op in sorted(support.items(), key=lambda kv: -kv[1]["count"]):
        if op["count"] >= min_occ and len(jobs[key]) >= min_jobs and key not in existing and len(existing) < cap:
            val = {k: v for k, v in op.items() if k not in ("key",)}
            val.update({"support": op["count"], "jobs": sorted(jobs[key])[:10], "promoted_at": time.strftime("%Y-%m-%d %H:%M"),
                        "promotion_rule": f">= {min_occ} edits across >= {min_jobs} jobs"})
            await st.aput(("style", user_id), key, val)
            existing.add(key)
            promoted.append(key)
    return promoted


async def promote_outcomes(user_id: str) -> list[str]:
    from apps.api.db import Outcome, session
    cfg = config.get("memory.outcome", {}) or {}
    min_n, min_delta = int(cfg.get("min_samples_per_category", 5)), float(cfg.get("min_reply_rate_delta", 0.10))
    with session() as s:
        rows = s.execute(select(Outcome).where(Outcome.user_id == user_id)).scalars().all()
    sub: dict[tuple, set] = defaultdict(set)
    rep: dict[tuple, set] = defaultdict(set)
    for o in rows:
        k = (o.category or "uncategorised", o.strategy or "default")
        if o.stage == "submitted":
            sub[k].add(o.proposal_id)
        if o.stage in ("replied", "interview", "hired"):
            rep[k].add(o.proposal_id)
    by_cat: dict[str, dict] = defaultdict(dict)
    for (cat, strat), ids in sub.items():
        by_cat[cat][strat] = (len(rep[(cat, strat)] & ids) / len(ids), len(ids))
    st = memory.get()
    if st is None:
        return []
    promoted = []
    for cat, strats in by_cat.items():
        n = sum(v[1] for v in strats.values())
        if n < min_n:
            continue
        ranked = sorted(strats.items(), key=lambda kv: -kv[1][0])
        best, (r1, n1) = ranked[0]
        if len(ranked) > 1:
            other, (r2, n2) = ranked[1]
            if r1 - r2 < min_delta:
                continue
            rule = f"In {cat}, '{best}' proposals got {r1:.0%} replies (n={n1}) vs {r2:.0%} for '{other}' (n={n2})."
        else:
            rule = f"In {cat}, proposals got {r1:.0%} replies (n={n1}) with the '{best}' strategy."
        await st.aput(("outcome", user_id), cat, {"rule": rule, "best_strategy": best, "n": n,
                                                  "rates": {k: round(v[0], 3) for k, v in strats.items()},
                                                  "promoted_at": time.strftime("%Y-%m-%d %H:%M"),
                                                  "promotion_rule": f">= {min_n} outcomes and >= {min_delta:.0%} reply-rate gap"})
        promoted.append(cat)
    return promoted


def should_promote_style_edit(edit_count: int, distinct_jobs: int) -> bool:
    """Kept for the starter-kit interface; the real rule is promote_style()."""
    cfg = config.get("memory.style", {}) or {}
    return edit_count >= int(cfg.get("min_occurrences", 3)) and distinct_jobs >= int(cfg.get("min_distinct_jobs", 3))
