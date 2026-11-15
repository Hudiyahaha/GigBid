---
id: cs-ai_ml-p08
persona: ai_ml
type: case_study
project: ai_ml-p08
title: Support-ticket triage agent v2 (travel)
date: 2021-05-28
client_industry: travel
skills_listed: [LangGraph, NLP, Celery]
source: synthetic
---

# Support-ticket triage agent v2 (travel)

**Client:** Cobaltfield Media (synthetic) (travel) | **Duration:** 4 weeks | **Year:** 2021

## The problem
The client came to me because a support team was manually routing thousands of tickets a week.

## What I did
- Used LangGraph for the core of the solution.
- Used NLP for the core of the solution.
- Used Celery for the core of the solution.
- Exposed the model behind an async typed HTTP service.
- Adapted a 7B model with low-rank adapters on a single GPU.

## Result
The project auto-routed 64% of tickets correctly within the first months after launch.

## What I would do differently
Agree on evaluation metrics before building.
