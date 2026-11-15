# customer-churn-model

> source: synthetic | persona: ai_ml | project: ai_ml-p02

Built for a media client. The problem: a subscription business could not see which customers were about to leave.

## Features
- Reported precision, recall and calibration on a held-out split
- Configuration through environment variables
- Unit tests and a small demo dataset

## Stack
Mostly XGBoost, plus the usual supporting libraries.

## Results
In production this raised recall on churners to 0.21.
