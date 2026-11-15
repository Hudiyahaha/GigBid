---
id: cs-ai_ml-p01
persona: ai_ml
type: case_study
project: ai_ml-p01
title: Support-ticket triage agent
date: 2022-01-25
client_industry: education
skills_listed: [FastAPI, Docker]
source: synthetic
---

# Support-ticket triage agent

**Client:** Summitpoint Logistics (synthetic) (education) | **Duration:** 15 weeks | **Year:** 2022

## The problem
The client came to me because a support team was manually routing thousands of tickets a week.

## What I did
- Exposed the model behind an async typed HTTP service, using FastAPI.
- Packaged everything into reproducible container images, using Docker.
- Modelled the agent as a stateful graph with conditional edges and checkpoints.
- Processed free-text customer messages at scale.
- Fanned slow jobs out to a background task queue with retries and a Redis broker.

## Result
The project auto-routed 33% of tickets correctly within the first months after launch.

## What I would do differently
Add monitoring from day one.
