---
id: cs-ai_ml-p04
persona: ai_ml
type: case_study
project: ai_ml-p04
title: Domain LLM fine-tune
date: 2023-11-08
client_industry: legal
skills_listed: [LoRA fine-tuning, Hugging Face Transformers]
source: synthetic
---

# Domain LLM fine-tune

**Client:** Peakline Travel (synthetic) (legal) | **Duration:** 9 weeks | **Year:** 2023

## The problem
The client came to me because a fintech wanted a small model that answered in their compliance tone.

## What I did
- Adapted a 7B model with low-rank adapters on a single GPU, using LoRA fine-tuning.
- Fine-tuned a pretrained encoder checkpoint from the model hub, using Hugging Face Transformers.
- Trained the network with a custom training loop and mixed precision.

## Result
The project beat the base model on 55 of 60 eval prompts within the first months after launch.

## What I would do differently
Agree on evaluation metrics before building.
