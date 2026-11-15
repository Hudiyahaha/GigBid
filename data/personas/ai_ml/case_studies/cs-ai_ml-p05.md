---
id: cs-ai_ml-p05
persona: ai_ml
type: case_study
project: ai_ml-p05
title: Model serving platform
date: 2025-03-01
client_industry: SaaS
skills_listed: [AWS SageMaker, MLflow]
source: synthetic
---

# Model serving platform

**Client:** Deltawave Studio (synthetic) (SaaS) | **Duration:** 16 weeks | **Year:** 2025

## The problem
The client came to me because data scientists shipped models by emailing pickle files.

## What I did
- Used AWS SageMaker for the core of the solution.
- Tracked every experiment's parameters, metrics and model artefacts, using MLflow.
- Packaged everything into reproducible container images.
- Exposed the model behind an async typed HTTP service.

## Result
The project cut model release time from weeks to 6 days within the first months after launch.

## What I would do differently
Write the runbook earlier.
