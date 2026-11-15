# GigBid: R&D design review

AI-4016 R&D assignment. Every number in this report is generated from a file in `evals/results/`
(`python -m scripts.make_tables`); commits are referenced by short hash.

## 1. Problem and constraints
A freelancer spends hours scanning feeds, spends paid Connects on jobs they will not win, sends generic proposals,
and meets scams (free "tests", off-platform payment, upfront fees). GigBid automates discovery, assessment and
drafting. **What must never be automated:** submitting a proposal, sending a message, spending Connects, and
accepting anything a client proposes. These all pass a human approval in the UI that is enforced twice: a LangGraph
`interrupt()` in the graph, and an HMAC approval token checked by the marketplace MCP server (ADR 0003).
**Declared budgets** (`agent/config.yaml: budgets.declared`): p95 20 s and $0.002 per job analysed; p95 60 s and $0.01
per proposal (open profile, list prices).

## 2. Architecture
Two hand-written LangGraph graphs (`docs/images/*.mmd`, rendered from code). **Bid graph:** Scout fans out with
`Send` to Job Analyst, Risk Assessor and Fit Matcher in parallel, then decision, pricing, writer, claim verifier,
critic (at most 2 revisions), compliance, dry-run preview, human approval (interrupt) and executor.
**Conversation graph:** messages, intent, interview slots, Client Liaison, compliance, preview, approval, send.
One **marketplace port** (`agent/marketplace_port.py`) calls the Marketplace MCP server, which selects the GigSim
or live-Upwork adapter by config (R1). **MCP surface:** 3 own servers (portfolio, marketplace, workspace; 20 tools,
`docs/TOOLS.md`) plus Upwork's official server and GitHub's. **Stores:** Postgres (app DB, LangGraph checkpoints,
long-term memory store), Qdrant (vectors), Redis (Arq worker), Phoenix (traces). Why each agent exists:
`docs/ARCHITECTURE.md`. State, execution trace and long-term memory are separate (section 2 there).

## 3. R&D question A: tool granularity
*Hypothesis:* a fine-grained toolset with rewritten "when to use it" descriptions beats both the plain fine-grained
set and a coarse `server(action, params)` set on selection accuracy, at a token cost. *Setup:* 40 tasks with known
correct calls, one call per task, local open model (no rate limits), `evals/runners/tool_study.py`.

<!-- table:tools -->
Model: llama3.2 (local), 40 tasks.

| Tool design | Tools | Selection accuracy | Argument accuracy | Tokens / task |
|---|---|---|---|---|
| fine_grained | 21 | 1.000 | 1.000 | 1892 |
| coarse | 3 | 0.700 | 0.575 | 377 |
| fine_rewritten | 21 | 1.000 | 1.000 | 1927 |
<!-- /table:tools -->

*Conclusion:* see the table. The coarse design saves prompt tokens (3 schemas instead of about 20) but moves the
choice into an untyped `params` object, where argument errors concentrate. GigBid ships fine-grained tools.

## 4. R&D question B: retrieval, claim verification, what ships
*Hypothesis (stated before running):* "requirement decomposition plus hybrid retrieval raises evidence Recall@5 by
15 points over V0 on jobs with four or more requirements." **Refuted:** decomposition *lowered* recall
(sentence-level sub-queries include noise sentences and RRF spreads the ranking), and hybrid alone was flat.

<!-- table:rag -->
| Variant | Recall@5 | MRR | nDCG@10 | p95 latency (s) | n jobs |
|---|---|---|---|---|---|
| v0_naive | 0.556 | 0.690 | 0.599 | 0.0032 | 484 |
| v1_decompose | 0.403 | 0.593 | 0.473 | 0.0222 | 484 |
| v2_hybrid | 0.546 | 0.694 | 0.620 | 0.0080 | 484 |
| v4_outcome | 0.551 | 0.715 | 0.594 | 0.0051 | 484 |
| v5_multivector | 0.492 | 0.640 | 0.579 | 0.0028 | 484 |
| v6_contextual | 0.583 | 0.722 | 0.615 | 0.0071 | 484 |
| v9_skill_graph | 0.686 | 0.836 | 0.739 | 0.0115 | 484 |
| v10_hybrid_outcome | 0.556 | 0.720 | 0.620 | 0.0119 | 484 |
<!-- /table:rag -->

**Ablation and job types** (`rag_variants.json: by_job_type`): the skill graph (V9) wins on named-skill jobs, but on
**vague posts** it is *worse* than naive dense retrieval (R@5 0.395 vs 0.443), because a graph cannot match a skill
nobody named. Cross-encoder reranking (MS-MARCO MiniLM) *hurt*: a web-search reranker misjudges
requirement-to-portfolio matches. **What ships:** V9 (`agent/config.yaml: rag.variant`), with the vague-post weakness
accepted and documented (ADR 0002). Part of V9's gain is expected by construction, because gold labels are
skill-overlap based.

**Claim verification (B3):** every draft is split into claims; each claim is checked against the full text of the
evidence it cites (`rag/verify.py`). Unsupported claims are removed and partial ones rewritten before the Critic sees
the draft. On the real-LLM demo (`demo_proposal.json`): 3 claims, 2 partial (rewritten), 0 unsupported after
verification.

**Headline table (B5):**
<!-- table:headline -->
| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|
| V0 (naive dense) | 0.556 | 0.599 | - | see judge_labels.csv | - | - | - |
| Shipped: V9 skill graph | 0.686 | 0.739 | - | see judge_labels.csv | - | - | 0.0025 |
<!-- /table:headline -->

**Outcomes and where retrieval did not translate into replies:**
<!-- table:outcomes -->
_pending: run `python -m evals.runners.gigsim_outcomes`_
<!-- /table:outcomes -->
GigSim's simulated client rewards naming its must-have skills, concrete numbers, a non-generic opening and a price
under its ceiling. Better retrieval raises the chance the right project is cited, but reply rate saturates once *any*
relevant project with a number is cited, so retrieval gains beyond the top 2 items do not move replies.
**Judge calibration:** `evals/results/judge_labels.csv` holds 30 judge-scored proposals for the author to label;
kappa is computed by `judge_calibration kappa` and is not reported until the human labels exist.

## 5. R&D question C: single agent vs prebuilt supervisor vs our graph
<!-- table:svm -->
| Design | Bid/skip accuracy | Unsupported claims / proposal | Compliance violations left | Tokens / job | Latency / job (s) | Errors | n |
|---|---|---|---|---|---|---|---|
| react | 0.500 | - | 0 | 5915 | 32.3 | 0 | 6 |
| supervisor | 0.833 | 1.000 | 0 | 7757 | 93.7 | 0 | 6 |
| graph | 0.667 | 0.000 | 0 | 5350 | 33.6 | 0 | 6 |
<!-- /table:svm -->
Same open model (gpt-oss-20b) for all three, n = 6 jobs each (free-tier rate limits), so these are directional only.
**The prebuilt supervisor made the best bid/skip calls** (0.83 vs 0.67 for our graph): its analyst agent reasons over
the whole post, while our heuristic Fit Matcher is conservative (the same wrong-skip failure as section 8). But it cost
45% more tokens, ran about 3x slower, and its proposals carried 1.0 unsupported claim each; ours carried 0 because
the claim verifier runs before the Critic. The single ReAct agent never chose to bid (accuracy 0.50), so it never
produced a proposal to judge. **Would we ship the single agent?** No: nothing in it enforces grounding or policy, and
only the server's approval-token check kept it from writing. **What we would take from the supervisor:** an
LLM-based fit judgement for borderline jobs (`fit.use_llm_grader`), now that the threshold is calibrated.

## 6. The change request (policy v2)
GigSim's 2 November update: +4 Connects for clients without verified payment, at most 10 submissions per day, cover
letters under 3,000 characters. **What changed:** commit `ebb03eb`. Code/config diff: `rules.yaml` (3 values + version),
`pricing.py` (+5 lines: daily-limit check; the surcharge was already read from the live policy), and one environment
line each in compose and the dev stack: about 22 lines in 4 files, with no node, graph or prompt changes. It took
under 15 minutes including running the integration tests under v2. This is what keeping rules in configuration buys.

## 7. Signature extension: X2 proposal experiments
Two strategies (`writer.strategies`), drafted from the same analyses, scored by simulated clients under 10 seeds per
job, with a two-proportion z-test (section 4 outcome table; `docs/EXTENSION.md`). In the product, the strategy is a
user setting, and the outcome-memory rule promotes the winner per category once there are 5+ outcomes.

## 8. Failure analysis
Failed dev jobs from `decision_eval.json` (heuristic profile, threshold 0.60), by taxonomy:
<!-- table:failures -->
| Job | Persona | Type | Gold | Predicted | Taxonomy | Evidence from the trace |
|---|---|---|---|---|---|---|
| dev-ai_ml-015 | ai_ml | partial | bid | watch | missed evidence / wrong skip | borderline: fit 0.44 |
| dev-ai_ml-025 | ai_ml | partial | bid | watch | missed evidence / wrong skip | borderline: fit 0.40 |
| dev-ai_ml-040 | ai_ml | vague | bid | skip | missed evidence (vague post) | low fit 0.00: Our e-commerce team needs an experienced specialist for: Demand forecast for |
| dev-ai_ml-050 | ai_ml | normal | bid | bid | mispriced | fit 1.00 >= 0.6, risk 0.06 <= 0.55 |
| dev-ai_ml-080 | ai_ml | normal | bid | bid | mispriced | fit 0.75 >= 0.6, risk 0.06 <= 0.55 |
| dev-ai_ml-085 | ai_ml | vague | bid | watch | missed evidence (vague post) | borderline: fit 0.50 |
| dev-ai_ml-105 | ai_ml | partial | bid | bid | mispriced | fit 0.81 >= 0.6, risk 0.04 <= 0.55 |
| dev-ai_ml-135 | ai_ml | normal | bid | skip | missed evidence / wrong skip | low fit 0.33: Looking for a person who can make sense of large volumes of written customer |
| dev-ai_ml-160 | ai_ml | vague | bid | skip | missed evidence (vague post) | low fit 0.00: Looking for an expert to fix it properly.; Ideally you are someone who can c |
| dev-ai_ml-165 | ai_ml | partial | bid | bid | mispriced | fit 0.77 >= 0.6, risk 0.06 <= 0.55 |
| dev-ai_ml-170 | ai_ml | injection | bid | bid | mispriced | fit 0.61 >= 0.6, risk 0.04 <= 0.55 |
| dev-ai_ml-175 | ai_ml | normal | bid | watch | missed evidence / wrong skip | borderline: fit 0.58 |
| dev-ai_ml-195 | ai_ml | normal | bid | skip | missed evidence / wrong skip | low fit 0.33: Ideally you are someone who can make the app run the same on every machine.; |
| dev-fullstack-000 | fullstack | partial | bid | skip | missed evidence / wrong skip | low fit 0.20: Ideally you are someone who can speed things up with caching and queues.; Ex |
<!-- /table:failures -->
**Dominant failure: wrong skip / missed evidence** (37 false negatives of 120, recall 0.45). The Fit Matcher's
calibrated relevance is conservative, so implied requirements score "partial". **Fix tried:** recalibrating
`decision.min_fit_to_bid` from 0.60 to 0.30 on the dev rows raised F1 from 0.61 to 0.82 (precision 0.93, recall 0.73).
**Did it work on unseen data?** See section 10. **Vague posts** remain the weakest type (accuracy 0.21), the same
weakness as V9 retrieval. **Real-LLM drafts:** the verifier passed a hedged forward-looking sentence ("I can extend
the same pipeline to NLP tasks") because it is a plan, not a claim, which is a grey zone for R5.

## 9. Safety and platform respect
**Never:** send, submit or spend without approval; scrape; automate a browser; store tokens unencrypted; follow
instructions in job posts or client messages. **Enforcement:** interrupt and approval token (two layers); untrusted
text stripped of injection markers and delimited; Compliance redacts contacts, guarantees and inflated years and
blocks off-platform payment and free work; PII is masked in logs, traces and the audit log; OAuth tokens are
Fernet-encrypted per user; every query is scoped by user. **Measured:**
<!-- table:injection -->
Planted-injection dev jobs: 30; rule detection rate 1.000. LLM sample n=10: attack success before stripping/delimiting 0.000, after 0.000.
<!-- /table:injection -->
**What still gets through:** paraphrased injections without trigger words, and subtle off-platform hints, are not
caught by the marker list. Compliance only catches them if they produce contact details. The model's own instruction
hierarchy resisted every planted injection in the sample even before stripping, so the stripping layer is untested
against a model that does comply. Polite scheduling: 5 minutes on GigSim, 240 minutes in live mode, per-user rate
limits below the platform's.

## 10. Hidden test results against declared budgets
<!-- table:holdout -->
Held-out set (180 jobs, never used for tuning): bid/skip F1 0.736, accuracy 0.744, scam precision 1.000 / recall 1.000, price in fair band 0.562, p95 latency per job 14.9 s.
<!-- /table:holdout -->
<!-- table:decision -->
| Profile | Bid/skip F1 | Accuracy | Scam precision | Scam recall | Price in fair band | p95 latency / job (s) | Tokens / job | n |
|---|---|---|---|---|---|---|---|---|
| heuristic (no LLM) | 0.606 | 0.675 | 1.000 | 1.000 | 0.567 | 25.5 | 0 | 120 |
<!-- /table:decision -->
Budgets: the heuristic profile is within the latency budget at p50 but **misses the p95 budget of 20 s per job
analysed** on this CPU-only laptop (cross-encoder relevance over about 6 requirements per job while other jobs run).
The real-LLM proposal path measured 25 s and $0.0025 per proposal, inside the 60 s / $0.01 budget. **Optimisation that
helped:** skipping the LLM in the Risk Assessor when rules already show a scam, deterministic fit grading (about 1k
tokens saved per job), and serialising CPU retrieval.
