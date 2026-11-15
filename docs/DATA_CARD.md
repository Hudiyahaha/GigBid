# Data card

The instructor's GigSim simulator, persona corpora and dev set were **not in the starter kit**, so this project builds
its own, combining **real Kaggle data** (market statistics, real job posts, fraud labels) with **clearly labelled
synthetic data** (personas, clients' hidden preferences, gold labels). Every record carries a `source` field:
`synthetic`, or `kaggle:<dataset>`.

## Real data (Kaggle)
| Dataset (Kaggle) | Rows used | Used for | Processing |
|---|---|---|---|
| asaniczka/upwork-job-postings-dataset-2024-50k-records | 53,058 | real job texts + budgets (GigSim history and live stream), price stats | dedup by title+date; keyword domain/category classifier; emails/phones masked; links dropped |
| asaniczka/all-jobs-on-upwork-200k-plus | 826,328 (3 files) | price statistics (budgets, hourly ranges) | same classifier; outliers > p99.5 removed |
| ahmedmyalo/upwork-freelance-jobs-60k | 63,950 | competition (applicant counts), payment-verified share | applicants parsed from text |
| asaniczka/freelance-contracts-dataset-1-3-million-entries | 1,292,791 | realised prices (total paid, hourly rate) | classified by title |
| sarveshchhetri/freelancer-success-earnings-and-churn-prediction | 12,000 | freelancer hourly rates by primary skill | percentiles |
| adityammantri/trial-1 | 54,391 (28.4% fraudulent) | external validation of the scam detector | 200 fraud + 200 genuine sample |

Pipeline: `python -m data.generators.kaggle_stats` -> `data/processed/market_stats.json`, `kaggle_history_jobs.json`,
`kaggle_stream_jobs.json`, `scam_validation.jsonl`. Raw files live in `data/raw/kaggle/` (git-ignored, not redistributed).

**Licences / attribution.** Each dataset's licence is stated on its Kaggle page; the asaniczka datasets are published
under an attribution licence. Only derived statistics and short masked excerpts are used; raw files are not committed.
Verify each licence on Kaggle before redistributing anything. **Limitations:** posted budgets are not final prices
(contracts give realised prices but from a different platform mix); keyword classification covers 36% of postings;
the trial-1 postings appear machine-generated, so scam-detector accuracy on it is an optimistic external check.

## Synthetic data
`python -m data.generators.synth --seed 42` (deterministic). Personas: AI/ML engineer, full-stack developer, data
analyst; each has 20 projects (3 of 10 archetypes deliberately missing, which creates real skill gaps), a CV (PDF and
Markdown), case studies, repos (README and code), reviews and 150 past proposals labelled won/replied/ignored by the
same simulated-client model GigSim uses.

**Built to defeat naive RAG:** skills appear explicitly, only implicitly (an *implied phrase*), or only in code imports;
job posts describe implied skills with *different* client-side wording (`JOB_PHRASES`) than the portfolio; the same
project is described up to three ways (case study, repo, proposal); vague posts name no tools.

**Gold labels** (`evals/datasets/dev_<persona>.jsonl`, 200 jobs per persona): `gold_bid` (no scam, >= 60% of
requirements covered by the persona, client not risky, budget >= 80% of the persona floor), `gold_scam`, `injection_id`,
`fair_band` (+/-20% around the job's true value), and graded `gold_evidence` (shared requirement skills per item).
Recall@5 and MRR use *strong* evidence (relevance >= 2 when any exists); nDCG@10 uses the graded labels.
Persona floors are calibrated to the real market medians (Kaggle).

**Held-out "hidden" set:** 60 jobs per persona from a different seed (`data/holdout/`, git-ignored), used once.

**Limitations:** gold labels come from the same generator that wrote the text, so absolute numbers are optimistic.
Relative comparisons between variants and designs are the meaningful output. Simulated clients follow a transparent
logistic model (`gigsim/sim_client.py`), not real people.
