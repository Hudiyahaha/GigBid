"""Build REAL-data artefacts from the Kaggle datasets (see docs/DATA_CARD.md for attribution and licences).

Outputs (data/processed/, git-ignored except where copied into gigsim/seed by synth.py):
  market_stats.json          price percentiles by domain/category (posted budgets 50k+200k, realised prices 1.3M contracts),
                             competition (applicants) from the 60k set, freelancer rates from the success dataset
  kaggle_history_jobs.json   ~1,500 real job posts (title, description, budget) normalised to GigSim's job schema
  kaggle_stream_jobs.json    ~150 real job posts injected into GigSim's live stream (source=kaggle, unlabelled)
  scam_validation.jsonl      labelled real/fake postings from trial_1 for external scam-detector validation

Real text is PII-masked (emails, phones) on import. Links are dropped; nothing is fetched from Upwork.
Usage: python -m data.generators.kaggle_stats
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd

from agent.guardrails import mask_pii

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "kaggle"
OUT = ROOT / "data" / "processed"

# keyword -> (domain, category). Order matters: first match wins.
KEYWORDS: list[tuple[str, str, str]] = [
    (r"\b(rag|llm|gpt|chatbot|openai|langchain|ai agent|generative ai|prompt engineer)", "ai_ml", "LLM apps & RAG"),
    (r"\b(computer vision|object detection|yolo|opencv|image recognition|image classification)", "ai_ml", "Computer vision"),
    (r"\b(nlp|text classification|sentiment|named entity|ner\b|transformers|bert)", "ai_ml", "NLP"),
    (r"\b(mlops|model deploy|sagemaker|mlflow|kubeflow)", "ai_ml", "MLOps"),
    (r"\b(machine learning|ml model|deep learning|predictive model|xgboost|pytorch|tensorflow|scikit)", "ai_ml", "ML modelling"),
    (r"\b(shopify|woocommerce|stripe|e-?commerce)", "fullstack", "E-commerce"),
    (r"\b(playwright|cypress|selenium test|ci/cd|github actions|devops)", "fullstack", "Testing & DevOps"),
    (r"\b(websocket|real-?time|serverless|aws lambda|firebase)", "fullstack", "Realtime & serverless"),
    (r"\b(api|backend|node\.?js|express|nestjs|graphql|django|fastapi)", "fullstack", "API backend"),
    (r"\b(react|next\.?js|vue|angular|frontend|front-end|tailwind|figma to)", "fullstack", "Frontend UI"),
    (r"\b(web app|saas|full[- ]?stack|web application|mvp)", "fullstack", "Web app"),
    (r"\b(power bi|tableau|looker|dashboard)", "data", "Dashboards & BI"),
    (r"\b(dbt|snowflake|bigquery|etl|data pipeline|data engineer|warehouse)", "data", "Data engineering"),
    (r"\b(google analytics|ga4|marketing analytics|attribution)", "data", "Marketing analytics"),
    (r"\b(excel|google sheets|spreadsheet|vba|apps script)", "data", "Spreadsheet automation"),
    (r"\b(forecast)", "data", "Forecasting"),
    (r"\b(data analy|statistic|a/b test|sql|data scien|r programming|spss)", "data", "Analytics & statistics"),
    (r"\b(ios|android|flutter|react native|swift|kotlin|mobile app)", "other", "Mobile apps"),
    (r"\b(unity|unreal|game)", "other", "Games"),
    (r"\b(blockchain|smart contract|solidity|nft|web3|crypto)", "other", "Blockchain"),
    (r"\b(salesforce|hubspot|crm)", "other", "CRM"),
    (r"\b(wordpress|wix|webflow|squarespace)", "other", "CMS"),
    (r"\b(logo|graphic design|illustrat|video edit|youtube|seo|copywrit|content writ|article|blog)", "other", "Content & design"),
    (r"\b(bookkeep|accountant|accounting|quickbooks|tax)", "other", "Finance"),
    (r"\b(firmware|embedded|arduino|rust|c\+\+)", "other", "Embedded & systems"),
]
_KW = [(re.compile(p, re.I), d, c) for p, d, c in KEYWORDS]


def classify(title: str, desc: str = "") -> tuple[str, str] | None:
    text = f"{title} {desc[:400]}"
    for rx, d, c in _KW:
        if rx.search(text):
            return d, c
    return None


def _pcts(s: pd.Series) -> dict:
    s = s.dropna()
    s = s[(s > 0) & (s < s.quantile(0.995))] if len(s) > 50 else s[s > 0]
    if s.empty:
        return {"n": 0}
    q = s.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    return {"n": int(len(s)), "p10": round(q[0.1], 1), "p25": round(q[0.25], 1), "p50": round(q[0.5], 1),
            "p75": round(q[0.75], 1), "p90": round(q[0.9], 1)}


def load_postings() -> pd.DataFrame:
    frames = []
    f50 = RAW / "upwork_jobs_50k" / "upwork-jobs.csv"
    if f50.exists():
        df = pd.read_csv(f50, low_memory=False)
        df["src"] = "kaggle:upwork-job-postings-50k"
        frames.append(df)
    for f in sorted((RAW / "all_upwork_jobs_200k").glob("*.csv")):
        df = pd.read_csv(f, low_memory=False)
        df["description"] = ""
        df["src"] = "kaggle:all-jobs-on-upwork-200k"
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["title", "published_date"])
    df["title"] = df["title"].astype(str)
    df["description"] = df["description"].fillna("").astype(str)
    df["is_hourly"] = df["is_hourly"].astype(str).str.lower().isin(["true", "1"])
    for c in ("hourly_low", "hourly_high", "budget"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["hourly_mid"] = df[["hourly_low", "hourly_high"]].mean(axis=1)
    cls = [classify(t, d) for t, d in zip(df["title"], df["description"], strict=True)]
    df["domain"] = [c[0] if c else None for c in cls]
    df["category"] = [c[1] if c else None for c in cls]
    return df


def main(seed: int = 7) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    df = load_postings()
    stats: dict = {"sources": {}, "by_domain": {}, "by_category": {}}
    stats["sources"]["postings_rows"] = int(len(df))
    stats["sources"]["postings_classified"] = int(df["domain"].notna().sum())
    for dom, g in df[df["domain"].notna()].groupby("domain"):
        fixed = _pcts(g.loc[~g["is_hourly"], "budget"])
        hourly = _pcts(g.loc[g["is_hourly"], "hourly_mid"])
        stats["by_domain"][dom] = {"fixed": fixed, "hourly": hourly, "fixed_median": fixed.get("p50"),
                                   "hourly_median": hourly.get("p50"), "share_hourly": round(float(g["is_hourly"].mean()), 3)}
    for cat, g in df[df["category"].notna()].groupby("category"):
        stats["by_category"][cat] = {"fixed": _pcts(g.loc[~g["is_hourly"], "budget"]),
                                     "hourly": _pcts(g.loc[g["is_hourly"], "hourly_mid"])}
    # realised prices from contracts
    fc = RAW / "freelance_contracts_1_3m" / "contracts.csv"
    if fc.exists():
        c = pd.read_csv(fc, usecols=["job_title", "total_paid", "hourly_rate"], low_memory=False)
        c["total_paid"] = pd.to_numeric(c["total_paid"], errors="coerce")
        c["hourly_rate"] = pd.to_numeric(c["hourly_rate"], errors="coerce")
        cls = [classify(str(t)) for t in c["job_title"]]
        c["domain"] = [x[0] if x else None for x in cls]
        stats["sources"]["contracts_rows"] = int(len(c))
        stats["realised_contracts"] = {d: {"total_paid": _pcts(g["total_paid"]), "hourly_rate": _pcts(g["hourly_rate"])}
                                       for d, g in c[c["domain"].notna()].groupby("domain")}
    # competition from the 60k set
    f60 = RAW / "upwork_freelance_jobs_60k" / "Final_Upwork_Dataset.csv"
    if f60.exists():
        j = pd.read_csv(f60, low_memory=False, usecols=["Job Title", "Applicants_Num", "Payment_Situation", "EX_level_demand"])
        apps = pd.to_numeric(j["Applicants_Num"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
        stats["competition"] = {"applicants": _pcts(apps),
                                "payment_verified_share": round(float(j["Payment_Situation"].astype(str).str.contains(
                                    "verified", case=False).mean()), 3),
                                "experience_levels": j["EX_level_demand"].value_counts().head(5).to_dict()}
        stats["sources"]["jobs60k_rows"] = int(len(j))
    # freelancer rates
    ffs = RAW / "freelancer_success_churn" / "freelancer_gig_success_dataset.csv"
    if ffs.exists():
        f = pd.read_csv(ffs)
        stats["freelancer_rates"] = {str(k): _pcts(g["hourly_rate_usd"]) for k, g in f.groupby("primary_skill")}
        stats["sources"]["freelancers_rows"] = int(len(f))
    (OUT / "market_stats.json").write_text(json.dumps(stats, indent=1, default=float), encoding="utf-8")

    # real job posts (need descriptions and a usable price) -> GigSim history + stream
    real = df[(df["description"].str.len() > 200) & df["domain"].notna()].copy()
    real = real[(real["is_hourly"] & real["hourly_mid"].between(5, 300)) | (~real["is_hourly"] & real["budget"].between(20, 50000))]
    real = real.sample(n=min(1650, len(real)), random_state=seed)
    jobs = []
    for i, r in enumerate(real.itertuples()):
        hourly = bool(r.is_hourly)
        price = float(r.hourly_mid if hourly else r.budget)
        jobs.append({
            "job_id": f"kg-{i:05d}", "title": mask_pii(r.title)[:200], "description": mask_pii(r.description)[:3000],
            "category": r.category, "domain": r.domain, "skills_tags": [],
            "budget": {"type": "hourly" if hourly else "fixed",
                       "min": float(r.hourly_low) if hourly and not np.isnan(r.hourly_low) else round(price * 0.6, 1),
                       "max": float(r.hourly_high) if hourly and not np.isnan(r.hourly_high) else price, "currency": "USD"},
            "duration": "", "experience_level": "", "client_id": None, "industry": None,
            "posted_at": str(r.published_date), "connects_cost": 4 + 2 * min(4, int(price // (20 if hourly else 500))),
            "screening_questions": [], "proposals_count": rng.randint(5, 50), "final_price_usd": round(price, 1),
            "status": "closed", "source": r.src, "country": None if pd.isna(r.country) else str(r.country)})
    (OUT / "kaggle_history_jobs.json").write_text(json.dumps(jobs[:1500], indent=0), encoding="utf-8")
    (OUT / "kaggle_stream_jobs.json").write_text(json.dumps(jobs[1500:], indent=0), encoding="utf-8")

    # scam validation (trial_1: labelled fake job postings)
    ft = RAW / "trial_1" / "processed_labeled_dataset_without_encoding.xlsx"
    if ft.exists():
        t = pd.read_excel(ft)
        stats["sources"]["trial1_rows"] = int(len(t))
        stats["sources"]["trial1_fraud_share"] = round(float(t["fraudulent"].mean()), 3)
        pos, neg = t[t["fraudulent"] == 1], t[t["fraudulent"] == 0]
        n = min(200, len(pos), len(neg)) if len(neg) else min(200, len(pos))
        sample = pd.concat([pos.sample(n, random_state=seed)] + ([neg.sample(n, random_state=seed)] if len(neg) else []))
        with open(OUT / "scam_validation.jsonl", "w", encoding="utf-8") as fo:
            for r in sample.itertuples():
                fo.write(json.dumps({"title": str(r.job_title), "description": f"{r.company_profile}. {r.job_desc} {r.skills_desc}",
                                     "fraudulent": int(r.fraudulent), "source": "kaggle:trial-1"}) + "\n")
        (OUT / "market_stats.json").write_text(json.dumps(stats, indent=1, default=float), encoding="utf-8")
    summary = {"sources": stats["sources"], "by_domain": {d: {"fixed_median": v["fixed_median"], "hourly_median": v["hourly_median"]}
                                                          for d, v in stats["by_domain"].items()},
               "history_jobs": min(1500, len(jobs)), "stream_jobs": max(0, len(jobs) - 1500)}
    print(json.dumps(summary, indent=1, default=float))
    return summary


if __name__ == "__main__":
    main()
