---
id: cs-ai_ml-p17
persona: ai_ml
type: case_study
project: ai_ml-p17
title: Clinical note entity extractor for a logistics client
date: 2022-02-23
client_industry: logistics
skills_listed: [spaCy, Hugging Face Transformers, PyTorch]
source: synthetic
---

# Clinical note entity extractor for a logistics client

**Client:** Northstone Studio (synthetic) (logistics) | **Duration:** 15 weeks | **Year:** 2022

## The problem
The client came to me because a health-tech team needed medications pulled out of free-text notes.

## What I did
- Used spaCy for the core of the solution.
- Fine-tuned a pretrained encoder checkpoint from the model hub, using Hugging Face Transformers.
- Trained the network with a custom training loop and mixed precision, using PyTorch.

## Result
The project achieved an F1 of 0.81 on held-out notes within the first months after launch.

## What I would do differently
Agree on evaluation metrics before building.
