# Submission kit

## Résumé bullet (two lines, numbers from evals/results/)
- Built GigBid, a LangGraph multi-agent freelancer copilot with 3 MCP servers and human-in-the-loop approval; it
  detects scams with 1.00 precision/recall and reached 0.74 bid/skip F1 on a held-out set, with zero unsupported claims after verification.
- Evaluated 10 RAG variants on 600 labelled jobs: shipped a skill-graph retriever (+13 pts Recall@5, 0.686 vs 0.556)
  and showed with a simulated-client A/B test that the gain did not change reply rate (38.3% vs 37.9%).

## 3-minute demo video script (screen recording of https://gigbid-t0az.onrender.com)
1. **0:00-0:20** Sign in as the reviewer. The inbox shows ranked jobs with fit, risk badge, price and Connects.
2. **0:20-1:10 One job, inbox to approved proposal.** Click *Scout now*, open a job marked awaiting approval, and
   show the requirement-to-evidence matrix. In the Proposal studio, hover a sentence to show its evidence, point at
   the Critic and Compliance notes and the dry-run cost, then click *Approve and send* and watch the timeline reach
   `executor`. Open *Pipeline*: the card is under "submitted".
3. **1:10-1:40 A scam caught.** Filter the inbox by *skipped*, open a job with the red "scam" badge, and show the risk
   flags (for example upfront fee or off-platform payment) and the skip reason.
4. **1:40-2:10 An injected instruction ignored.** Open a job whose post contains "ignore all previous instructions…",
   expand *Original post*, and show the "Ignored injected instructions" banner and a draft that obeys none of them.
5. **2:10-2:50 A client reply handled.** In *Messages*, open a thread, click *Suggest a reply*, show the intent and
   the interview slots, then approve.
6. **2:50-3:00** Degraded mode: show the red "Marketplace unavailable" banner (on the dev stack:
   `POST /api/dev/marketplace/down`).

To get client replies on the live app, the GigSim clock must advance after submitting: run
`curl -X POST -H "Authorization: Bearer gigsim-admin" http://127.0.0.1:8081/admin/tick?n=2` on the dev stack locally,
or record that segment on the local dev stack.

Demo GIF (30 s): record segment 2 with ScreenToGif (free) and save it as `docs/images/demo.gif`.

## MCP Inspector screenshots (Part A)
```
cd D:\GigBid
set PORTFOLIO_PERSONA=ai_ml
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe -m mcp_servers.portfolio.server stdio
```
In the Inspector: *Connect*, *Tools*, run `search_evidence` with `{"requirement": "Celery background jobs"}`, then
screenshot it. Do the same for *Resources* and *Prompts*. Repeat with `mcp_servers.workspace.server`. Save the
screenshots in `docs/images/inspector-*.png`.

## Classroom checklist
- [ ] Deployed link: https://gigbid-t0az.onrender.com (open it once before grading: the free tier sleeps)
- [ ] Private comment: `reviewer@gigbid.test / <REVIEWER_PASSWORD>`
- [ ] Repo: https://github.com/Hudiyahaha/GigBid (final commit before the deadline)
- [ ] R&D report PDF: `docs/report/REPORT.pdf`
- [ ] Demo video link (YouTube unlisted or Drive)
- [ ] Portfolio MCP server: `mcp_servers/portfolio/README.md` (uvx command) and technical write-up link
      (publish `docs/WRITEUP.md` on Medium or LinkedIn)
