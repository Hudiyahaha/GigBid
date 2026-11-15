"""Loads agent/config.yaml with ${VAR:-default} environment expansion."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(v: Any) -> Any:
    if isinstance(v, str):
        return _VAR.sub(lambda m: os.getenv(m.group(1), m.group(2) or ""), v)
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


@lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    path = Path(os.getenv("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))
    return _expand(yaml.safe_load(path.read_text(encoding="utf-8")))


def get(path: str, default: Any = None) -> Any:
    cur: Any = settings()
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def reload() -> None:
    settings.cache_clear()
