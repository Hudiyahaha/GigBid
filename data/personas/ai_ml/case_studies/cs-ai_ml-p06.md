---
id: cs-ai_ml-p06
persona: ai_ml
type: case_study
project: ai_ml-p06
title: Semantic product search
date: 2024-05-12
client_industry: healthcare
skills_listed: [Hugging Face Transformers, RAG]
source: synthetic
---

# Semantic product search

**Client:** Harborgate Travel (synthetic) (healthcare) | **Duration:** 6 weeks | **Year:** 2024

## The problem
The client came to me because an online shop's keyword search missed obvious matches.

## What I did
- Fine-tuned a pretrained encoder checkpoint from the model hub, using Hugging Face Transformers.
- Grounded the assistant's answers in retrieved document passages with citations, using RAG.
- Built an in-process approximate nearest-neighbour index.
- Exposed the model behind an async typed HTTP service.

## Result
The project lifted search click-through by 31% within the first months after launch.

## What I would do differently
Write the runbook earlier.
