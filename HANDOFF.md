# GigBid: handoff for the next agent

Project root: `D:\GigBid` (git repo, branch `main`). Assignment brief: `C:\Users\hudiyahaha\Downloads\Assignment-II_AI-4016-GigBid.docx.pdf`
(AI-4016 "GigBid": multi-agent freelancer copilot; parts A MCP 20, B RAG 20, C LangGraph 25, D UI 15, E prod 10, report 10).
Read the brief first, then this file. Keep the brief's directory layout. Commit in small steps (the brief penalises one giant commit).

## Environment facts (Windows)
- Python venv: `.venv` (Python 3.12, deps pinned in `uv.lock`). Run things as `.\.venv\Scripts\python.exe -m ...`.
  Install new deps with `py -3.14 -m uv add <pkg> --python .venv\Scripts\python.exe`.
- Shell gotchas: `python3` is a Microsoft Store stub (hangs). PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM
  (breaks TOML/py) - edit files with the editor tool instead. `git commit -F <file>` (here-strings to `-F -` fail).
- Always set for local runs: `$env:GIGBID_LOCAL_SQLITE='1'; $env:HF_HUB_OFFLINE='1'` (.env has a Postgres URL meant for docker;
  HF downloads are slow; cached models: `BAAI/bge-small-en-v1.5`, `cross-encoder/ms-marco-MiniLM-L-6-v2`).
- `.env` contains the user's `GROQ_API_KEY` (never print it, never commit `.env`). Groq models that exist:
  `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`. Free tier rate-limits hard (429s): ~25 s and ~10k tokens per job.
  Use `GIGBID_FAKE_LLM=1` (deterministic heuristics, no API) for large evals; use real LLM only on small samples (n~10).
- Docker Desktop is installed but needs the user to start it once; disk is tight (C: ~8 GB, D: ~8 GB free).
- Kaggle raw data: `data/raw/kaggle/*` (git-ignored). Processed by `python -m data.generators.kaggle_stats`.

## What is DONE (and how)
- **Data**: `data/generators/synth.py` (deterministic, seed 42) builds 3 synthetic personas (`data/personas/`), GigSim seed
  (`gigsim/seed/`), dev sets with gold labels (`evals/datasets/dev_<persona>.jsonl`, 200 each), held-out set (`data/holdout/`,
  git-ignored). Calibrated with real Kaggle prices (`data/generators/kaggle_stats.py` -> `data/processed/market_stats.json`);
  1,500 real Kaggle jobs in GigSim history, 150 in the live stream; trial-1 -> `data/processed/scam_validation.jsonl`.
- **GigSim** (our own simulator, the instructor's was not provided): `gigsim/server.py`, client model `gigsim/sim_client.py`.
  Policy v1/v2 via `GIGSIM_POLICY_VERSION` (v2 = the "change request": +4 Connects for unverified clients, 10 submissions/day,
  3,000-char cover letters). `/admin/tick` advances time; `/admin/evaluate` scores a proposal statelessly (for evals).
- **MCP servers** (A): `mcp_servers/{portfolio,marketplace,workspace}/server.py` (FastMCP, annotations, output schemas,
  idempotency ledger, dry_run, approval tokens `agent/approval_token.py`, hash-chained audit log `mcp_servers/common.py`).
  Adapters: `mcp_servers/marketplace/adapters/{gigsim.py,upwork_live.py}` (Upwork = OAuth via MCP SDK, untested live).
  Tests pass: `pytest mcp_servers tests/contract` (15) - schema snapshots in `tests/contract/snapshots/` (regenerate with
  `UPDATE_SNAPSHOTS=1` after the `similar_proposals` tool + `relevance` field were added - NOT yet regenerated).
- **RAG** (B): composable `rag/pipeline.py`; variants `rag/variants/v0..v9 + best.py` (flag presets); verifier `rag/verify.py`;
  eval `python -m evals.runners.rag_eval` -> `evals/results/rag_variants.json|csv` (full run was started in background;
  check the file exists - rerun if not; ~30-60 min CPU). V6/V7 need LLM (`--make-hyde`; contexts.json not built).
- **Agents** (C): nodes in `agent/nodes/`, graphs `agent/graphs/{bid_graph,conversation_graph}.py` (Send fan-out, critic loop <=2,
  interrupt approval, executor), state+reducers `agent/state.py`, memory `agent/memory/{store,promotion_rules}.py`,
  persistence `agent/persistence.py` (SQLite/Postgres), runner `agent/runner.py` (start/resume/replay/history).
  Integration tests pass: `pytest tests/integration` (scam skip, crash-resume exactly-once, edit re-checked).
  Real-LLM demo: `python -m evals.runners.demo_single_proposal` -> `evals/results/demo_proposal.json` (25 s, 9.8k tok, $0.0025).
- **API** (D/E): `apps/api/main.py` + `routers/` + `services.py` + `security.py`; worker `worker/main.py` (Arq, or `--local`).
  OpenAPI exported to `apps/api/openapi.json`; TS client generated (`apps/web/src/lib/api/schema.d.ts`).
- **Web** (D): `apps/web` (Vite+React+TS), all 9 screens in `src/app/`, components in `src/components/`. Builds clean.
  Dev stack: `python -m scripts.dev_stack` (GigSim :8081 + API :8000 serving `apps/web/dist`). Playwright: `cd apps/web;
  npx playwright test --project=desktop` (5 tests; 2 passed, 3 failed due to a bug now FIXED: decide/analyze endpoints were
  sync -> "no running event loop"; re-run to confirm).

## What is LEFT (in priority order) and how
1. Re-run Playwright; fix anything left; `git add -A; git commit`.
2. Regenerate contract snapshots: `UPDATE_SNAPSHOTS=1 pytest tests/contract`; run full `pytest -q` (set GIGBID_FAKE_LLM=1).
3. **Evals** (write runners in `evals/runners/`, results to `evals/results/*.json` via `evals.common.write_result`):
   - `decision_eval.py`: run bid graph to the decision node on dev jobs (FAKE_LLM, all 600; real LLM n=10/persona):
     bid-or-skip F1, scam precision/recall, price in fair band (`fair_band`), p50/p95 latency, tokens/USD.
   - `gigsim_outcomes.py`: for jobs reaching approval, call GigSim `POST /admin/evaluate` (admin token `gigsim-admin`)
     with the client-facing letter -> reply/hire rate. Also X2 A/B: strategies `evidence_first` vs `question_first`
     (state["strategy"]) + chi-square/two-proportion test (scipy) -> `evals/results/x2_ab.json`.
   - `judge_calibration.py`: LLM judge (prompt `judge`) on 30 proposals; export CSV for the USER to label (kappa needs human
     labels - never fabricate); compute Cohen's kappa once labels exist.
   - `ablation.py`: rag_eval with `best` minus one flag at a time.
   - `injection_eval.py`: attack success rate before/after defences on dev jobs with `injection_id` (check output for the
     injected effect: "15 years", email/phone, "$5", "guaranteed", "for free").
   - R&D A `tool_study.py`: 40 tasks with known correct calls; compare fine-grained vs coarse vs rewritten descriptions
     (LLM tool-calling, small model) -> selection/argument accuracy, tokens.
   - R&D C `single_vs_multi.py`: ReAct (`langgraph.prebuilt.create_react_agent` + `agent.mcp_client.langchain_tools()`,
     prompt `react_agent`), `langgraph_supervisor.create_supervisor`, and our graph on ~10-20 jobs (rate limits!).
   - Set `rag.variant` in `agent/config.yaml` to the measured best variant.
4. **Change request**: set `GIGSIM_POLICY_VERSION=2`; update `data/policy_pack/rules.yaml` (version 2, limits) - pricing already
   reads the surcharge from the live policy; commit separately and record the diff size for the report.
5. **Docker/CI**: `infra/docker/Dockerfile` (one python image reused for api/worker/mcp/gigsim; web built in a node stage
   and copied to `apps/web/dist`), `infra/docker-compose.yml` (web/api, worker, 3 MCP servers on 8101-8103 with
   `MCP_MODE=http`, gigsim, postgres, redis, qdrant, ollama, phoenix). `.github/workflows/ci.yml` (ruff, pytest with
   FAKE_LLM, contract, Playwright, "nothing under gigsim/ changed" checksum, secret scan) + `eval.yml` (30-job smoke eval with
   thresholds). Add `.gitattributes` (`* text=auto eol=lf`).
6. **Docs**: README (pitch, architecture mermaid from `graph.get_graph().draw_mermaid()`, results tables from
   evals/results), `docs/ARCHITECTURE.md`, `docs/TOOLS.md` (one row per tool + trust rationale for Upwork + GitHub MCP),
   `docs/DATA_CARD.md` (Kaggle sources/licences/limitations; synthetic vs real), `docs/RUNBOOK.md` (live-mode interval
   240 min justification), `docs/EXTENSION.md` (X2), `docs/AI_USAGE.md` (Claude Code; one thing it got wrong: e.g. the
   sync endpoints / interrupt swallowed by the node wrapper), `docs/adr/*.md`, `mcp_servers/portfolio/README.md` (uvx/docker
   install for Claude Desktop), R&D report (`docs/report/REPORT.md` -> PDF), failure taxonomy of >=10 failed dev jobs.
7. Things only the USER can do: start Docker, deploy a public URL + reviewer login (set `REVIEWER_EMAIL/PASSWORD` env),
   3-minute video, publish write-up, classmate panel, label 30 items for kappa, rotate the Groq key, push to GitHub.
