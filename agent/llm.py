"""Model router: every node's model comes from config (route by node), with caching, fallback,
token/cost accounting and budgets.

Usage:
    data = await llm.call_json("job_analyst", "job_analyst", {"job": ...}, JobSpec, heuristic=fn)
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from agent import config
from agent.guardrails import mask_pii
from agent.prompts import render

log = logging.getLogger("gigbid.llm")
ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = Path(os.getenv("LLM_CACHE_PATH", ROOT / "data" / "processed" / "llm_cache.db"))
_cache_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    latency_s: float = 0.0
    cached_calls: int = 0
    fallbacks: int = 0
    heuristic_calls: int = 0
    by_node: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, node: str, tin: int, tout: int, usd: float, lat: float, cached: bool, model: str) -> None:
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        self.usd += usd
        self.latency_s += lat
        self.cached_calls += int(cached)
        n = self.by_node.setdefault(node, {"calls": 0, "tokens": 0, "usd": 0.0, "latency_s": 0.0, "model": model})
        n["calls"] += 1
        n["tokens"] += tin + tout
        n["usd"] += usd
        n["latency_s"] += lat

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def as_dict(self) -> dict:
        return {"calls": self.calls, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "tokens": self.tokens,
                "usd": round(self.usd, 6), "llm_latency_s": round(self.latency_s, 3), "cached_calls": self.cached_calls,
                "fallbacks": self.fallbacks, "heuristic_calls": self.heuristic_calls, "by_node": self.by_node}


CURRENT_USAGE: contextvars.ContextVar[Usage | None] = contextvars.ContextVar("gigbid_usage", default=None)
TOKEN_BUDGET: contextvars.ContextVar[int | None] = contextvars.ContextVar("gigbid_token_budget", default=None)
PROFILE_OVERRIDE: contextvars.ContextVar[str | None] = contextvars.ContextVar("gigbid_profile", default=None)


def start_usage(budget: int | None = None) -> Usage:
    u = Usage()
    CURRENT_USAGE.set(u)
    TOKEN_BUDGET.set(budget)
    return u


# ------------------------------------------------------------------ model resolution
def _profile() -> dict:
    name = PROFILE_OVERRIDE.get() or config.get("models.profile", "open")
    return config.get(f"models.profiles.{name}") or config.get("models.profiles.open")


def resolve(node: str) -> list[dict]:
    """Return [primary, fallback...] model specs for a node."""
    if os.getenv("GIGBID_FAKE_LLM") == "1":
        return [{"provider": "fake", "model": "fake"}]
    prof = _profile()
    nodes = prof.get("nodes", {})
    tier = nodes.get(node) or nodes.get("default") or "small"
    spec = dict(prof["tiers"].get(tier) or next(iter(prof["tiers"].values())))
    chain = [spec]
    if spec.get("fallback"):
        chain.append(spec["fallback"])
    return chain


def price(model: str, tin: int, tout: int) -> float:
    p = config.get("models.prices", {}).get(model)
    if not p:
        return 0.0
    return (tin * p[0] + tout * p[1]) / 1_000_000


_clients: dict[tuple, Any] = {}


def _chat(spec: dict, json_mode: bool, max_tokens: int):
    from langchain_openai import ChatOpenAI

    prov = config.get(f"models.providers.{spec['provider']}") or {}
    key_env = prov.get("api_key_env") or ""
    key = os.getenv(key_env, "") if key_env else "local"
    if key_env and not key:
        raise RuntimeError(f"{key_env} is not set; add it to .env")
    k = (spec["provider"], spec["model"], json_mode, max_tokens)
    if k not in _clients:
        kwargs: dict[str, Any] = {}
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        _clients[k] = ChatOpenAI(model=spec["model"], base_url=prov.get("base_url"), api_key=key, temperature=0.2,
                                 max_tokens=max_tokens, timeout=60, max_retries=3, **kwargs)
    return _clients[k]


# ------------------------------------------------------------------ cache
def _cache_db() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CACHE_PATH, check_same_thread=False)
    con.execute("CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, v TEXT, tin INT, tout INT, lat REAL, ts REAL)")
    return con


def _cache_get(key: str):
    if not config.get("models.cache", True) or os.getenv("GIGBID_NO_CACHE") == "1":
        return None
    with _cache_lock:
        con = _cache_db()
        row = con.execute("SELECT v, tin, tout, lat FROM cache WHERE k=?", (key,)).fetchone()
        con.close()
    return row


def _cache_put(key: str, v: str, tin: int, tout: int, lat: float) -> None:
    if not config.get("models.cache", True):
        return
    with _cache_lock:
        con = _cache_db()
        con.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?,?,?,?)", (key, v, tin, tout, lat, time.time()))
        con.commit()
        con.close()


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _extract_json(text: str) -> Any:
    text = _strip_think(text)
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON found")
    return json.loads(text[start:])


# ------------------------------------------------------------------ public API
async def _invoke(node: str, system: str, user: str, json_mode: bool, max_tokens: int) -> tuple[str, dict]:
    usage = CURRENT_USAGE.get()
    budget = TOKEN_BUDGET.get()
    if usage is not None and budget is not None and usage.tokens >= budget:
        raise BudgetExceeded(f"token budget {budget} exhausted before node {node}")
    errors = []
    for i, spec in enumerate(resolve(node)):
        if spec["provider"] == "fake":
            raise RuntimeError("fake provider: use heuristic")
        key = hashlib.sha256(json.dumps([spec["model"], system, user, json_mode]).encode()).hexdigest()
        hit = _cache_get(key)
        t0 = time.perf_counter()
        if hit:
            text, tin, tout, _lat = hit
            cached = True
        else:
            from langchain_core.messages import HumanMessage, SystemMessage
            try:
                msg = await asyncio.wait_for(
                    _chat(spec, json_mode, max_tokens).ainvoke([SystemMessage(system), HumanMessage(user)],
                                                               config={"run_name": node, "tags": [node, spec["model"]]}),
                    timeout=float(config.get("models.timeout_s", 90)))
            except Exception as e:  # noqa: BLE001 - try next model in chain
                errors.append(f"{spec['model']}: {type(e).__name__}: {mask_pii(str(e))[:200]}")
                if usage:
                    usage.fallbacks += 1
                continue
            text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            um = getattr(msg, "usage_metadata", None) or {}
            tin, tout = int(um.get("input_tokens", len(system + user) // 4)), int(um.get("output_tokens", len(text) // 4))
            cached = False
        lat = time.perf_counter() - t0
        if not cached:
            _cache_put(key, text, tin, tout, lat)
        usd = price(spec["model"], tin, tout)
        if usage is not None:
            usage.add(node, tin, tout, usd, lat, cached, spec["model"])
        return text, {"model": spec["model"], "tokens_in": tin, "tokens_out": tout, "usd": usd, "latency_s": lat,
                      "cached": cached, "fallback_index": i}
    raise RuntimeError("all models failed: " + " | ".join(errors))


async def call_text(node: str, prompt: str, variables: dict, heuristic: Callable[[], str] | None = None,
                    max_tokens: int = 1200) -> tuple[str, dict]:
    system, user, version = render(prompt, variables)
    try:
        text, meta = await _invoke(node, system, user, False, max_tokens)
        return _strip_think(text), {**meta, "prompt_version": version}
    except BudgetExceeded:
        raise
    except Exception as e:  # noqa: BLE001
        if heuristic is None:
            raise
        u = CURRENT_USAGE.get()
        if u:
            u.heuristic_calls += 1
        return heuristic(), {"model": "heuristic", "degraded": True, "error": str(e)[:200], "prompt_version": version}


async def call_json(node: str, prompt: str, variables: dict, schema: type[BaseModel] | None = None,
                    heuristic: Callable[[], dict] | None = None, max_tokens: int = 1500) -> tuple[Any, dict]:
    system, user, version = render(prompt, variables)
    if schema is not None:
        system += "\n\nReturn ONLY a JSON object that matches this JSON schema:\n" + json.dumps(
            schema.model_json_schema(), separators=(",", ":"))[:4000]
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            text, meta = await _invoke(node, system, user + ("" if attempt == 0 else "\n\nYour last answer was not valid JSON. Return valid JSON only."),
                                       True, max_tokens)
            data = _extract_json(text)
            if schema is not None:
                data = schema.model_validate(data)
            return data, {**meta, "prompt_version": version}
        except BudgetExceeded:
            raise
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            continue
        except Exception as e:  # noqa: BLE001
            last_err = e
            break
    if heuristic is None:
        raise RuntimeError(f"{node}: LLM failed and no heuristic: {last_err}")
    u = CURRENT_USAGE.get()
    if u:
        u.heuristic_calls += 1
    data = heuristic()
    if schema is not None and not isinstance(data, BaseModel):
        data = schema.model_validate(data)
    return data, {"model": "heuristic", "degraded": True, "error": str(last_err)[:200], "prompt_version": version}
