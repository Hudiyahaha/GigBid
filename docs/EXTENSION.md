# Signature extension: X2 proposal experiments

Two proposal strategies, configured in `agent/config.yaml: writer.strategies`:
* **evidence_first**: open with the client's problem, prove fit with the two strongest cited projects, answer the
  questions, end with one next step.
* **question_first**: open with one sharp clarifying question, a three-step plan, one cited project as proof, under
  150 words.

**Design.** `evals/runners/gigsim_outcomes.py` runs the full bid graph to the approval interrupt for each job, then
drafts the second strategy from the *same* analyses and evidence, so only the writing differs. Both letters (and a
generic template as a floor) are scored by GigSim's simulated client, which has hidden preferences, under 10 seeds
per job. Significance comes from a two-proportion z-test on reply counts.

**In the product.** Each user picks a strategy in Settings; outcomes are recorded per strategy (`Outcome.strategy`),
and the outcome-memory promotion rule promotes "in category X, strategy A beats B by >= 10 points" once there are 5+
outcomes.

**Results:** `evals/results/gigsim_outcomes.json` (`x2_ab_test`).
