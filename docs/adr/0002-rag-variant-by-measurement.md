# ADR 0002: Ship V10 (hybrid + outcome-aware), not reranking
**Context:** the default assumption was that cross-encoder reranking (V3) would win. **Decision:** measure all variants
on the 600-job dev set (`evals/results/rag_variants.json`, `rag_v10.json`). V3 lowered Recall@5 from 0.556 to 0.398;
hybrid (V2) gave the best nDCG@10 and outcome-aware (V4) the best MRR, and their combination V10 matched or beat both.
**Consequence:** faster retrieval (13 ms p95) and better ranking; the cross-encoder is kept only as a calibrated
relevance score for the Fit Matcher's thresholds.
