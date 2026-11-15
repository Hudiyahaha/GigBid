# AI usage

**Tool:** Claude Code (Anthropic), used as a pair-programmer for the whole repository: data generators, GigSim, MCP
servers, RAG pipeline, LangGraph nodes and graphs, API, React UI, tests, evals and docs. Every change was run and
tested locally, and the author is accountable for every line.

**Things the AI got wrong that were caught:**
1. **The node wrapper swallowed `interrupt()`.** The generic `except Exception` in `agent/nodes/base.py` would have
   turned LangGraph's interrupt signal into a dead letter. Caught in review; it now re-raises `GraphBubbleUp`.
2. **Sync FastAPI endpoints started background tasks.** `decide` and `analyze` were `def`, so they ran in a thread
   with no event loop ("no running event loop"). Caught by the Playwright approval tests; now `async def`.
3. **It defaulted the RAG variant to cross-encoder reranking.** The full dev-set evaluation showed reranking *lowered*
   Recall@5 from 0.556 to 0.398. The shipped variant is now chosen by measurement (V9 skill graph, R@5 0.686), with
   its weakness on vague posts documented in `docs/adr/0002`.
4. **Leaked phrasing in the synthetic data.** The generator first reused identical "implied skill" phrases in job posts
   and portfolios, which inflated retrieval scores. Fixed with separate client-side paraphrases (`JOB_PHRASES`).
5. **It left an orphaned eval process running.** It starved the CPU and made concurrent graph runs look deadlocked.
   Found with a `faulthandler` thread dump.
