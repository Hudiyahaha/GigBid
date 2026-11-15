---
id: cs-ai_ml-p19
persona: ai_ml
type: case_study
project: ai_ml-p19
title: Model serving platform for a travel client
date: 2026-02-25
client_industry: travel
skills_listed: [LangGraph]
source: synthetic
---

# Model serving platform for a travel client

**Client:** Northfield Ventures (synthetic) (travel) | **Duration:** 13 weeks | **Year:** 2026

## The problem
The client came to me because data scientists shipped models by emailing pickle files.

## What I did
- Modelled the agent as a stateful graph with conditional edges and checkpoints, using LangGraph.
- Deployed the model to a managed cloud inference endpoint.
- Tracked every experiment's parameters, metrics and model artefacts.
- Exposed the model behind an async typed HTTP service.

## Result
The project cut model release time from weeks to 2 days within the first months after launch.

## What I would do differently
Involve end users in week one.
