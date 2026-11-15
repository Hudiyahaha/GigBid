---
id: cs-ai_ml-p11
persona: ai_ml
type: case_study
project: ai_ml-p11
title: Domain LLM fine-tune v2 (logistics)
date: 2026-09-20
client_industry: logistics
skills_listed: [Hugging Face Transformers, PyTorch]
source: synthetic
---

# Domain LLM fine-tune v2 (logistics)

**Client:** Emberline Foods (synthetic) (logistics) | **Duration:** 5 weeks | **Year:** 2026

## The problem
The client came to me because a fintech wanted a small model that answered in their compliance tone.

## What I did
- Fine-tuned a pretrained encoder checkpoint from the model hub, using Hugging Face Transformers.
- Trained the network with a custom training loop and mixed precision, using PyTorch.
- Extracted named entities with an industrial NLP pipeline.

## Result
The project beat the base model on 32 of 60 eval prompts within the first months after launch.

## What I would do differently
Write the runbook earlier.
