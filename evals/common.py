"""Shared helpers for evaluation runners: dataset loading, metrics, result writing."""

from __future__ import annotations

import json
import math
import platform
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "evals" / "datasets"
RESULTS = ROOT / "evals" / "results"
PERSONAS = ["ai_ml", "fullstack", "data"]


def load_dev(persona: str, split: str = "dev") -> list[dict]:
    path = (DATASETS / f"dev_{persona}.jsonl") if split == "dev" else (ROOT / "data" / "holdout" / f"holdout_{persona}.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_jobs(split: str = "dev") -> dict[str, dict]:
    path = ROOT / "gigsim" / "seed" / "jobs_dev.json" if split == "dev" else ROOT / "data" / "holdout" / "jobs_holdout.json"
    return {j["job_id"]: j for j in json.loads(path.read_text(encoding="utf-8"))}


def strict_gold(gold: dict[str, int]) -> dict[str, int]:
    """Items that are STRONG evidence: relevance >= 2 when any such item exists, else all relevant items.
    Used for Recall@5 and MRR (a single shared generic skill like Python is not 'evidence' for a job)."""
    if not gold:
        return {}
    thr = min(2, max(gold.values()))
    return {i: r for i, r in gold.items() if r >= thr}


def recall_at(ranked: list[str], gold: dict[str, int], k: int) -> float:
    if not gold:
        return float("nan")
    return len(set(ranked[:k]) & set(gold)) / min(k, len(gold))


def mrr(ranked: list[str], gold: dict[str, int]) -> float:
    for i, x in enumerate(ranked):
        if x in gold:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at(ranked: list[str], gold: dict[str, int], k: int) -> float:
    if not gold:
        return float("nan")
    dcg = sum((2 ** gold.get(x, 0) - 1) / math.log2(i + 2) for i, x in enumerate(ranked[:k]))
    ideal = sorted(gold.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def mean(xs) -> float:
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return round(sum(xs) / len(xs), 4) if xs else float("nan")


def pct(xs, p: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    return round(xs[min(len(xs) - 1, int(math.ceil(p * len(xs))) - 1)], 4)


def f1(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def provenance() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                                         stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        commit = "uncommitted"
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "git_commit": commit,
            "python": platform.python_version(), "machine": platform.processor() or platform.machine()}


def write_result(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps({"provenance": provenance(), **payload}, indent=2, default=str), encoding="utf-8")
    return path
