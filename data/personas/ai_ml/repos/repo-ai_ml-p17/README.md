# clinical-note-entity-extractor-for-a-log

> source: synthetic | persona: ai_ml | project: ai_ml-p17

Built for a logistics client. The problem: a health-tech team needed medications pulled out of free-text notes.

## Features
- Trained the network with a custom training loop and mixed precision
- Configuration through environment variables
- Unit tests and a small demo dataset

## Stack
Mostly Hugging Face Transformers, plus the usual supporting libraries.

## Results
In production this achieved an F1 of 0.81 on held-out notes.
