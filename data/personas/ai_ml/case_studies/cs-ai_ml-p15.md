---
id: cs-ai_ml-p15
persona: ai_ml
type: case_study
project: ai_ml-p15
title: Support-ticket triage agent for a logistics client
date: 2025-10-18
client_industry: logistics
skills_listed: [Docker]
source: synthetic
---

# Support-ticket triage agent for a logistics client

**Client:** Maplefin Foods (synthetic) (logistics) | **Duration:** 3 weeks | **Year:** 2025

## The problem
The client came to me because a support team was manually routing thousands of tickets a week.

## What I did
- Packaged everything into reproducible container images, using Docker.
- Modelled the agent as a stateful graph with conditional edges and checkpoints.
- Processed free-text customer messages at scale.
- Exposed the model behind an async typed HTTP service.
- Built an in-process approximate nearest-neighbour index.

## Result
The project auto-routed 48% of tickets correctly within the first months after launch.

## What I would do differently
Add monitoring from day one.
