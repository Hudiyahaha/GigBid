"""Prompt loader. Every prompt is a versioned Markdown file in this folder (no inline prompts).

File format:
    ---
    version: 3
    node: writer
    ---
    ## system
    ...
    ## user
    ... {{variable}} ...
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent


@lru_cache(maxsize=64)
def load(name: str) -> tuple[str, str, str]:
    raw = (DIR / f"{name}.md").read_text(encoding="utf-8")
    version = "0"
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if m:
        vm = re.search(r"version:\s*(\S+)", m.group(1))
        version = vm.group(1) if vm else "0"
        raw = raw[m.end():]
    parts = re.split(r"^## (system|user)\s*$", raw, flags=re.M)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return sections.get("system", ""), sections.get("user", ""), version


def render(name: str, variables: dict) -> tuple[str, str, str]:
    system, user, version = load(name)

    def sub(m: re.Match) -> str:
        v = variables.get(m.group(1), "")
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)

    return re.sub(r"\{\{(\w+)\}\}", sub, system), re.sub(r"\{\{(\w+)\}\}", sub, user), f"{name}@v{version}"
