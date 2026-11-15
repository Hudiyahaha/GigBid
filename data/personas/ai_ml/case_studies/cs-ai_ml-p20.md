---
id: cs-ai_ml-p20
persona: ai_ml
type: case_study
project: ai_ml-p20
title: Semantic product search for a non-profit client
date: 2023-08-02
client_industry: non-profit
skills_listed: [FAISS, FastAPI, RAG, LoRA fine-tuning]
source: synthetic
---

# Semantic product search for a non-profit client

**Client:** Northpath Analytics (synthetic) (non-profit) | **Duration:** 16 weeks | **Year:** 2023

## The problem
The client came to me because an online shop's keyword search missed obvious matches.

## What I did
- Used FAISS for the core of the solution.
- Exposed the model behind an async typed HTTP service, using FastAPI.
- Used RAG for the core of the solution.
- Adapted a 7B model with low-rank adapters on a single GPU, using LoRA fine-tuning.

## Result
The project lifted search click-through by 53% within the first months after launch.

## What I would do differently
Write the runbook earlier.
