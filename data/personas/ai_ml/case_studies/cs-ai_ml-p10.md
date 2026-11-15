---
id: cs-ai_ml-p10
persona: ai_ml
type: case_study
project: ai_ml-p10
title: Clinical note entity extractor v2 (insurance)
date: 2024-08-20
client_industry: insurance
skills_listed: [Hugging Face Transformers]
source: synthetic
---

# Clinical note entity extractor v2 (insurance)

**Client:** Peakbridge Logistics (synthetic) (insurance) | **Duration:** 12 weeks | **Year:** 2024

## The problem
The client came to me because a health-tech team needed medications pulled out of free-text notes.

## What I did
- Fine-tuned a pretrained encoder checkpoint from the model hub, using Hugging Face Transformers.
- Extracted named entities with an industrial NLP pipeline.
- Modelled the agent as a stateful graph with conditional edges and checkpoints.

## Result
The project achieved an F1 of 0.41 on held-out notes within the first months after launch.

## What I would do differently
Involve end users in week one.
