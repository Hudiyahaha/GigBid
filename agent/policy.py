"""Platform rules, loaded from data/policy_pack/rules.yaml (+ the live marketplace policy). No rule is hard-coded."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from agent import config

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def rules() -> dict:
    path = ROOT / config.get("policy.rules_file", "data/policy_pack/rules.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for r in data.get("forbidden_patterns", []):
        r["_rx"] = [re.compile(p) for p in r["regex"]]
    return data


def merged(live: dict | None) -> dict:
    """Local rules overlaid with the marketplace's current policy (limits and Connects surcharges)."""
    r = rules()
    out = {"version": r.get("version"), "limits": dict(r.get("limits", {})), "connects": dict(r.get("connects", {})),
           "marketplace_version": None, "marketplace_rules": []}
    if live:
        out["marketplace_version"] = live.get("version")
        out["marketplace_rules"] = live.get("rules", [])
        for k, v in (live.get("limits") or {}).items():
            if v is not None:
                cur = out["limits"].get(k)
                out["limits"][k] = min(cur, v) if isinstance(cur, (int, float)) and isinstance(v, (int, float)) else v
        for k, v in (live.get("connects") or {}).items():
            if isinstance(v, (int, float)):
                out["connects"][k] = max(out["connects"].get(k, 0) or 0, v)
    return out


def reload() -> None:
    rules.cache_clear()
