"""Long-term memory on a LangGraph store (Postgres in docker, SQLite locally).

Namespaces (only promotion_rules.py writes here; raw tool output never does):
  ("style", user_id)    key = pattern id     value = {rule, op, support, jobs, promoted_at}
  ("outcome", user_id)  key = job category   value = {rule, best_strategy, rates, n, promoted_at}
"""

from __future__ import annotations

import re

_STORE = None


def set_store(store) -> None:
    global _STORE
    _STORE = store


def get() -> object | None:
    if _STORE is not None:
        return _STORE
    try:
        from langgraph.config import get_store
        return get_store()
    except Exception:  # noqa: BLE001 - outside a graph run and no global store
        return None


async def style_rules(user_id: str) -> list[dict]:
    s = get()
    if s is None:
        return []
    items = await s.asearch(("style", user_id), limit=50)
    return [{"id": it.key, **it.value} for it in items]


async def outcome_hints(user_id: str, category: str) -> list[str]:
    s = get()
    if s is None:
        return []
    out = []
    if category:
        it = await s.aget(("outcome", user_id), category)
        if it:
            out.append(it.value.get("rule", ""))
    return out


async def list_all(user_id: str) -> dict[str, list[dict]]:
    s = get()
    if s is None:
        return {"style": [], "outcome": []}
    return {ns: [{"id": it.key, **it.value} for it in await s.asearch((ns, user_id), limit=100)] for ns in ("style", "outcome")}


async def delete(user_id: str, namespace: str, key: str) -> None:
    s = get()
    if s is not None:
        await s.adelete((namespace, user_id), key)


def apply_style(text: str, rules: list[dict]) -> str:
    """Deterministically apply promoted style rules to a draft."""
    for r in rules or []:
        op = r.get("op")
        if op == "cut_first_sentence":
            parts = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
            if len(parts) == 2 and len(parts[1].split()) > 60:
                text = parts[1]
        elif op == "ban_word" and r.get("word"):
            text = re.sub(rf"(?i)\b{re.escape(r['word'])}\b\s?", "", text)
        elif op == "replace" and r.get("from"):
            text = re.sub(rf"(?i)\b{re.escape(r['from'])}\b", r.get("to", ""), text)
        elif op == "max_words" and r.get("n"):
            words = text.split()
            if len(words) > int(r["n"]) * 1.15:
                sents = re.split(r"(?<=[.!?])\s+", text)
                while len(" ".join(sents).split()) > int(r["n"]) and len(sents) > 3:
                    sents.pop(-2)
                text = " ".join(sents)
    return re.sub(r"\s{2,}", " ", text).strip()
