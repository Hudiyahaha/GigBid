"""Profile the raw Kaggle files (columns, dtypes, row counts, null rates, examples) -> data/processed/kaggle_profile.json.
Used to write docs/DATA_CARD.md honestly."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "kaggle"


def profile(path: Path, nrows: int | None = None) -> dict:
    if path.suffix == ".xlsx":
        df = pd.read_excel(path, nrows=nrows or 5000)
        n = None
    else:
        df = pd.read_csv(path, nrows=nrows, low_memory=False, on_bad_lines="skip")
        n = len(df) if nrows is None else None
    cols = {}
    for c in df.columns:
        s = df[c]
        ex = s.dropna().astype(str).head(2).str.slice(0, 120).tolist()
        cols[str(c)] = {"dtype": str(s.dtype), "null_rate": round(float(s.isna().mean()), 3), "examples": ex}
    return {"rows": n if n is not None else len(df), "rows_exact": n is not None, "columns": cols}


def main() -> None:
    out = {}
    for f in sorted(RAW.rglob("*")):
        if f.suffix in (".csv", ".xlsx"):
            key = f.relative_to(RAW).as_posix()
            try:
                out[key] = profile(f)
            except Exception as e:  # noqa: BLE001
                out[key] = {"error": str(e)}
            print(key, out[key].get("rows"), list(out[key].get("columns", {}))[:30])
    (ROOT / "data" / "processed" / "kaggle_profile.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
