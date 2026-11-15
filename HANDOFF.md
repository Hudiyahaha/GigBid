# GigBid: handoff for the next agent (updated after commit "Docs, tables, snapshots")

Project root: `D:\GigBid` (git, branch `main`). Brief: `C:\Users\hudiyahaha\Downloads\Assignment-II_AI-4016-GigBid.docx.pdf`.
The system is essentially COMPLETE; what is left is mostly eval runs finishing, regenerating tables/PDF, and the
user-only deliverables. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/report/REPORT.md` first.

## Environment facts (Windows)
- Run Python as `.\.venv\Scripts\python.exe -m ...` (Python 3.12, deps pinned in `uv.lock`; add deps with
  `py -3.14 -m uv add <pkg> --python .venv\Scripts\python.exe`). `python3` is a Store stub (hangs) - never use it.
- PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM: edit files with the editor tool. Commit with `git commit -F <file>`.
- Always set for local runs: `$env:GIGBID_LOCAL_SQLITE='1'; $env:HF_HUB_OFFLINE='1'; $env:TOKENIZERS_PARALLELISM='false'`.
- `.env` holds the user's GROQ_API_KEY (never print/commit). Groq models: openai/gpt-oss-20b, openai/gpt-oss-120b,
  qwen/qwen3.8-27b. Free tier rate-limits hard: keep LLM evals small; use `GIGBID_FAKE_LLM=1` for big runs.
- CPU contention is the #1 cause of "hangs": before starting heavy runs, check for leftover python processes
  (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`) and kill stale eval processes.
- Local Ollama (`llama3.2`) is running and used by the tool study.

## Done (all committed)
Data (synthetic personas + Kaggle-calibrated, dev + holdout sets), GigSim, 3 MCP servers + adapters (15 tests pass,
schema snapshots regenerated), RAG variants V0-V10 measured (shipped: `v9_skill_graph`), both LangGraph graphs with
interrupts/persistence/memory (integration tests pass, also under policy v2), API + worker + React UI (5/5 Playwright
pass; report copied to `docs/playwright-report/`), change request commit `ebb03eb` (policy v2), Docker/compose/CI/eval
workflows + `scripts/ci_guards.py`, docs (TOOLS, DATA_CARD, RUNBOOK, EXTENSION, AI_USAGE, ARCHITECTURE, adr/),
report skeleton `docs/report/REPORT.md` with generated tables.

## Left to do
1. Wait for / re-run evals whose result files may be missing (each writes `evals/results/<name>.json`):
   - `decision_eval_holdout` : `$env:GIGSIM_INCLUDE_HOLDOUT='1'; python -m evals.runners.decision_eval --split holdout --limit 60`
   - `gigsim_outcomes` and `gigsim_outcomes_v0` : `python -m evals.runners.gigsim_outcomes --per-persona 8`
     then `$env:RAG_VARIANT='v0_naive'; ... --name gigsim_outcomes_v0`
   - `single_vs_multi` : `python -m evals.runners.single_vs_multi --per-persona 1` (Groq; slow)
   - `tool_study` : `python -m evals.runners.tool_study` (Ollama llama3.2; ~30-60 min)
   - `rag_variants_rerank_subset` : `python -m evals.runners.rag_eval --variants v3_rerank,v8_corrective,best --limit 40 --name rag_variants_rerank_subset`
   - judge: `python -m evals.runners.judge_calibration score` (after gigsim_outcomes exists) -> `evals/results/judge_labels.csv`;
     the USER fills `human_score`, then `python -m evals.runners.judge_calibration kappa`.
2. `python -m scripts.make_tables` (fills README + REPORT tables), `python -m scripts.build_report` (PDF),
   `python scripts/ci_guards.py` (must print OK), then commit.
3. Re-read REPORT.md sections 3, 5, 7, 10 and adjust the prose to the final numbers (the prose was written before
   tool_study / single_vs_multi / outcomes / holdout finished).
4. User-only: start Docker Desktop and run compose; deploy a public URL with REVIEWER_EMAIL/PASSWORD env; record the
   3-minute video + docs/images/demo.gif; publish the technical write-up and the portfolio MCP server (push the repo to
   GitHub, then `uvx --from git+https://github.com/<user>/gigbid gigbid-portfolio-mcp`); label judge CSV; rotate Groq key.
