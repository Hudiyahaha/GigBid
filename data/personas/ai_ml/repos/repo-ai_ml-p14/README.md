# invoice-data-extraction-pipeline-v2-manu

> source: synthetic | persona: ai_ml | project: ai_ml-p14

Built for a manufacturing client. The problem: an accounts team typed invoice fields into the ERP manually.

## Features
- Called a hosted chat-completion model with json-mode outputs
- Configuration through environment variables
- Unit tests and a small demo dataset

## Stack
Mostly Python, plus the usual supporting libraries.

## Results
In production this processed 2500 invoices a day unattended.
