---
id: cs-ai_ml-p14
persona: ai_ml
type: case_study
project: ai_ml-p14
title: Invoice data extraction pipeline v2 (manufacturing)
date: 2023-07-08
client_industry: manufacturing
skills_listed: [OpenAI API, Python, PyTorch]
source: synthetic
---

# Invoice data extraction pipeline v2 (manufacturing)

**Client:** Peakpoint Travel (synthetic) (manufacturing) | **Duration:** 9 weeks | **Year:** 2023

## The problem
The client came to me because an accounts team typed invoice fields into the ERP manually.

## What I did
- Used OpenAI API for the core of the solution.
- Scripted the whole pipeline end to end, using Python.
- Trained the network with a custom training loop and mixed precision, using PyTorch.
- Fanned slow jobs out to a background task queue with retries and a Redis broker.

## Result
The project processed 2500 invoices a day unattended within the first months after launch.

## What I would do differently
Agree on evaluation metrics before building.
