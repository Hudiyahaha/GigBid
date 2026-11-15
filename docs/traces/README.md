# Execution traces

Each file is one or more graph runs with the full execution trace: every node (latency, tokens, cost, status) and
every MCP tool call (tool, masked arguments, result summary, latency). Regenerate with
`GIGBID_FAKE_LLM=1 python -m scripts.export_traces` (heuristic profile, so the traces are deterministic). Live
runs are browsable in the app's **Agent runs** page; one trace id flows from the UI through the API, the graph, the
MCP servers and the audit log.

| Case | File | What to look for |
|---|---|---|
| Skipped scam | [skipped_scam.json](skipped_scam.json) | Risk Assessor rule flag `upfront_payment` at severity 0.95; LLM call skipped; decision `skip`; no Writer |
| Approved proposal | [approved_proposal.json](approved_proposal.json) | run 1 stops at `human_approval` (interrupt); run 2 (approval) runs `executor` once; Connects spent |
| Critic loop | [critic_loop.json](critic_loop.json) | `critiques` has 3 versions: two `passed=false` sending the draft back, bounded at 2 revisions |
| Crash and resume | [crash_and_resume.json](crash_and_resume.json) | the thread waits for approval, the persistence layer is closed and reopened, approval resumes the same thread; a second resume does not submit again (same `submission`, one Connects spend) |

The real-LLM end-to-end run (Groq gpt-oss models, 6 LLM calls, 9.8k tokens, 25 s, $0.0025 list price) is in
[`evals/results/demo_proposal.json`](../../evals/results/demo_proposal.json).
