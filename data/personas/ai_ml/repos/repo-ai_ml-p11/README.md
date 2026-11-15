# domain-llm-fine-tune-v2-logistics

> source: synthetic | persona: ai_ml | project: ai_ml-p11

Built for a logistics client. The problem: a fintech wanted a small model that answered in their compliance tone.

## Features
- Trained the network with a custom training loop and mixed precision
- Configuration through environment variables
- Unit tests and a small demo dataset

## Stack
Mostly PyTorch, plus the usual supporting libraries.

## Results
In production this beat the base model on 32 of 60 eval prompts.
