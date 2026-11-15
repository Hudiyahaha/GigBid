"""CI rules the brief requires:
  1. nothing under gigsim/ changed (checksums in gigsim/CHECKSUMS.sha256; `--update` to regenerate deliberately)
  2. every prompt lives in agent/prompts/ (no inline system prompts in agent code)
  3. no secrets in the repo
  4. every number in README's Results section appears in a file under evals/results/
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMS = ROOT / "gigsim" / "CHECKSUMS.sha256"


def gigsim_files() -> list[Path]:
    return sorted(p for p in (ROOT / "gigsim").rglob("*") if p.is_file() and p.name != SUMS.name and "__pycache__" not in p.parts)


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_gigsim(update: bool) -> list[str]:
    cur = {p.relative_to(ROOT).as_posix(): digest(p) for p in gigsim_files()}
    if update:
        SUMS.write_text("\n".join(f"{h}  {f}" for f, h in cur.items()) + "\n", encoding="utf-8")
        return []
    want = dict(reversed(line.split("  ", 1)) for line in SUMS.read_text(encoding="utf-8").splitlines() if line.strip())
    return [f"gigsim changed: {f}" for f in sorted(set(cur) | set(want)) if cur.get(f) != want.get(f)]


def check_prompts() -> list[str]:
    bad = []
    for p in (ROOT / "agent").rglob("*.py"):
        if re.search(r"(?m)^\s*(SYSTEM_PROMPT|PROMPT)\s*=|\"You are (the|a|an) ", p.read_text(encoding="utf-8")):
            bad.append(f"inline prompt in {p.relative_to(ROOT)}")
    return bad


def check_secrets() -> list[str]:
    files = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    pat = re.compile(r"(gsk_[A-Za-z0-9]{40,}|sk-(proj-)?[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN [A-Z ]*PRIVATE KEY)")
    out = []
    for f in files:
        if f == ".env":
            out.append(".env is tracked")
        p = ROOT / f
        if p.is_file() and p.stat().st_size < 5_000_000:
            if pat.search(p.read_text(encoding="utf-8", errors="ignore")):
                out.append(f"possible secret in {f}")
    return out


def check_numbers() -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"<!-- results:start -->(.*?)<!-- results:end -->", readme, re.S)
    if not m:
        return []
    blob = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "evals" / "results").glob("*.json"))
    nums = set(re.findall(r"(?<![\w.])\d+\.\d+(?![\w.])", m.group(1)))
    return [f"README number {n} not found in evals/results/*.json" for n in sorted(nums) if n not in blob]


if __name__ == "__main__":
    upd = "--update" in sys.argv
    problems = check_gigsim(upd) + ([] if upd else check_prompts() + check_secrets() + check_numbers())
    print(json.dumps(problems, indent=1) if problems else "ci guards: OK")
    sys.exit(1 if problems else 0)
