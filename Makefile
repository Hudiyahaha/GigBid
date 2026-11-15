.PHONY: install dev test eval seed demo lint web
PY ?= .venv/bin/python

install:
	uv sync --extra dev
	cd apps/web && npm ci

seed:
	$(PY) -m data.generators.kaggle_stats || true
	$(PY) -m data.generators.synth --seed 42

dev:
	$(PY) -m scripts.dev_stack

web:
	cd apps/web && npx vite build

test:
	GIGBID_FAKE_LLM=1 $(PY) -m pytest -q
	cd apps/web && npx playwright test --project=desktop

lint:
	$(PY) -m ruff check .
	$(PY) scripts/ci_guards.py

eval:
	$(PY) -m evals.runners.rag_eval --name rag_variants
	GIGBID_FAKE_LLM=1 $(PY) -m evals.runners.decision_eval --limit 40
	GIGBID_FAKE_LLM=1 $(PY) -m evals.runners.gigsim_outcomes --per-persona 8
	$(PY) -m scripts.make_tables

demo:
	$(PY) -m evals.runners.demo_single_proposal
