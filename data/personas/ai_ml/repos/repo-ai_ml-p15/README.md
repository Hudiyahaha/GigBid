# support-ticket-triage-agent-for-a-logist

> source: synthetic | persona: ai_ml | project: ai_ml-p15

Built for a logistics client. The problem: a support team was manually routing thousands of tickets a week.

## Features
- Modelled the agent as a stateful graph with conditional edges and checkpoints
- Configuration through environment variables
- Unit tests and a small demo dataset

## Stack
Mostly FastAPI, plus the usual supporting libraries.

## Results
In production this auto-routed 48% of tickets correctly.
