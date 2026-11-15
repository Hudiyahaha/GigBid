"""Fail CI if bid-or-skip F1 drops or unsupported claims rise past evals/thresholds.yaml."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

R = Path(__file__).resolve().parent / "results"
t = yaml.safe_load((Path(__file__).resolve().parent / "thresholds.yaml").read_text())
dec = json.loads((R / "decision_eval.json").read_text())["overall"]
out = json.loads((R / "gigsim_outcomes_smoke.json").read_text()) if (R / "gigsim_outcomes_smoke.json").exists() else {}
fails = []
if dec["bid_skip"]["f1"] < t["min_bid_skip_f1"]:
    fails.append(f"bid/skip F1 {dec['bid_skip']['f1']} < {t['min_bid_skip_f1']}")
if dec["scam"]["recall"] < t["min_scam_recall"]:
    fails.append(f"scam recall {dec['scam']['recall']} < {t['min_scam_recall']}")
u = out.get("unsupported_rate_after_verification")
if u is not None and u == u and u > t["max_unsupported_rate_after_verification"]:
    fails.append(f"unsupported claim rate {u} > {t['max_unsupported_rate_after_verification']}")
print("\n".join(fails) or "thresholds: OK")
sys.exit(1 if fails else 0)
