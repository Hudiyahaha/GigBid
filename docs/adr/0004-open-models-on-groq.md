# ADR 0004: Open models via Groq, heuristics as fallback
**Decision:** open profile = gpt-oss-20b (cheap, frequent nodes) and gpt-oss-120b (writer, critic, liaison, judge) on
Groq's free tier; every node also has a deterministic heuristic used when the provider fails or for large offline evals
(`GIGBID_FAKE_LLM=1`). **Why:** no GPU, and the free tier rate-limits (about 25 s and 10k tokens per proposal). Large
evals run on the heuristic profile; LLM-profile numbers use small, stated samples.
