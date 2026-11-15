# ADR 0002: Ship V9 (skill graph fused with dense), not reranking
**Context:** the default assumption was that cross-encoder reranking (V3) would win. **Measurement** (600 dev jobs,
`evals/results/rag_variants.json`): V0 R@5 0.556 / MRR 0.690 / nDCG@10 0.599; V3 reranking (40-job/persona subset,
`rag_variants_rerank_subset.json`) is *worse* than V0; V9 skill graph is best overall (R@5 0.686, MRR 0.836, nDCG@10 0.739).

**Decision:** ship V9. **Trade-off we accept:** V9 is *worse* on vague posts that never name a tool (R@5 0.395 vs 0.443
for V0) because a graph cannot match a skill nobody named; most real posts name their tools (Kaggle postings carry
skill tags), and the dense branch inside V9 still contributes. **Caveat:** gold labels are defined by skill overlap, so
part of V9's gain on named-skill jobs is expected by construction; the vague-post result is the honest counterweight.
The cross-encoder is kept only as a calibrated relevance score for the Fit Matcher thresholds.
