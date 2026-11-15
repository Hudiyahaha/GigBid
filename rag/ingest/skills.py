"""Skill lexicon for chunk metadata: names, aliases and code import signatures -> canonical skill.

This is a generic tech detector (like GitHub linguist / dependency scanners). It only finds skills that
are NAMED in text or IMPORTED in code; implied skills are left to semantic retrieval.
"""

from __future__ import annotations

import re

LEXICON: dict[str, list[str]] = {
    "Python": [r"\bpython\b", r"^import \w+", r"^from \w+ import"],
    "PyTorch": [r"\bpytorch\b", r"\bimport torch\b"], "scikit-learn": [r"scikit-learn", r"\bsklearn\b"],
    "XGBoost": [r"\bxgboost\b"], "LangChain": [r"\blangchain"], "LangGraph": [r"\blanggraph\b"],
    "RAG": [r"\brag\b", r"retrieval[- ]augmented"], "Pinecone": [r"\bpinecone\b"], "FAISS": [r"\bfaiss\b"],
    "Hugging Face Transformers": [r"hugging ?face", r"\btransformers\b"], "LoRA fine-tuning": [r"\blora\b", r"\bpeft\b"],
    "OpenAI API": [r"\bopenai\b"], "FastAPI": [r"\bfastapi\b"], "Docker": [r"\bdocker", r"^FROM \S+"],
    "MLflow": [r"\bmlflow\b"], "YOLO": [r"\byolo", r"ultralytics"], "OpenCV": [r"\bopencv\b", r"\bimport cv2\b"],
    "spaCy": [r"\bspacy\b"], "Prophet": [r"\bprophet\b"], "AWS SageMaker": [r"sagemaker"], "Celery": [r"\bcelery\b"],
    "Airflow": [r"\bairflow\b"], "Computer vision": [r"computer vision"], "NLP": [r"\bnlp\b", r"natural language"],
    "Time series forecasting": [r"time[- ]series"], "Model evaluation": [r"classification_report", r"model evaluation"],
    "React": [r"\breact\b", r"from 'react'"], "Next.js": [r"next\.js", r"\bnextjs\b", r"next/server"],
    "TypeScript": [r"\btypescript\b", r"\binterface \w+ \{"], "Node.js": [r"node\.js", r"\bnodejs\b", r"require\('http'\)"],
    "Express": [r"\bexpress\b"], "NestJS": [r"\bnestjs\b", r"@nestjs"], "PostgreSQL": [r"postgres", r"create index"],
    "Prisma": [r"\bprisma"], "MongoDB": [r"mongo"], "Redis": [r"\bredis\b"], "Stripe": [r"\bstripe\b"],
    "GraphQL": [r"graphql", r"apollo"], "Tailwind CSS": [r"tailwind"], "AWS Lambda": [r"\blambda\b", r"export const handler"],
    "Firebase": [r"firebase"], "Django": [r"\bdjango\b"], "REST API": [r"\brest(ful)? api\b", r"router\.get\("],
    "WebSockets": [r"websocket", r"from 'ws'"], "Playwright": [r"playwright"], "GitHub Actions": [r"github actions", r"on: \[push"],
    "Shopify": [r"shopify", r"\{% section"], "Authentication": [r"\bauth(entication)?\b", r"jsonwebtoken", r"\bjwt\b"],
    "SQL": [r"\bsql\b", r"\bselect .* from\b"], "Excel": [r"\bexcel\b", r"xlookup", r"vlookup"], "Power BI": [r"power ?bi", r"\bdax\b"],
    "Tableau": [r"tableau"], "pandas": [r"\bpandas\b"], "dbt": [r"\bdbt\b", r"\{\{ ?ref\("], "Snowflake": [r"snowflake"],
    "BigQuery": [r"bigquery"], "Looker Studio": [r"looker"], "Google Analytics 4": [r"\bga4\b", r"google analytics", r"gtag\("],
    "A/B testing": [r"a/b test", r"\bab test", r"chi2_contingency"], "R": [r"library\(tidyverse\)", r"\bin r\b"],
    "ETL": [r"\betl\b", r"extract_transform_load"], "Data cleaning": [r"data cleaning", r"drop_duplicates"],
    "Dashboarding": [r"dashboard"], "Google Sheets Apps Script": [r"apps script", r"spreadsheetapp"],
    "Statistics": [r"statistic", r"statsmodels"], "Data visualization": [r"visuali[sz]ation", r"matplotlib"],
    "Forecasting": [r"forecast", r"holtwinters"],
}
_COMPILED = {k: [re.compile(p, re.I | re.M) for p in v] for k, v in LEXICON.items()}


def detect_skills(text: str) -> list[str]:
    return [skill for skill, pats in _COMPILED.items() if any(p.search(text or "") for p in pats)]


def canonical(skill: str) -> str:
    s = skill.strip().lower()
    for k in LEXICON:
        if k.lower() == s:
            return k
    for k, pats in _COMPILED.items():
        if any(p.search(skill) for p in pats):
            return k
    return skill.strip()
