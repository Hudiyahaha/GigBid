# Better retrieval didn't win a single extra reply

*What building a multi-agent freelancer copilot taught me about measuring the right thing.*

For a university R&D project I built GigBid, a system of LangGraph agents that does the tedious half of freelancing.
It reads job posts, flags scams, decides whether a job is worth paying to bid on, and drafts a proposal in which every
claim cites the freelancer's real portfolio. A human approves anything before it is sent. The brief asked for a lot
of engineering: MCP servers, ten retrieval variants, a critique loop, human-in-the-loop interrupts, durable
checkpoints. It also asked for measurements, and the measurements are the interesting part.

I went in with a confident hypothesis, written down before running anything: *"Requirement decomposition plus hybrid
retrieval will raise evidence Recall@5 by 15 points over naive dense retrieval on jobs with four or more
requirements."* Every RAG tutorial pushes some version of this. Split the query, add BM25 for exact tool names,
rerank with a cross-encoder, and watch the numbers climb.

Here is what actually happened.

## The setup, briefly

There was no real marketplace to test against, so I built one. GigSim is a small simulator with job posts, clients
who have *hidden* preferences, Connects (the paid tokens freelancers spend to bid), rate limits and random 5xx errors.
Each simulated client has must-have skills, a budget ceiling, and opinions about generic openings. It decides whether
to reply with a transparent logistic model.

Three synthetic freelancers (an AI/ML engineer, a full-stack developer, a data analyst) got portfolios built to defeat
naive retrieval. Some skills appear only in code imports, and some are described without being named, using
*different wording* in job posts than in the portfolio. That last detail matters. My first version of the generator
reused identical phrases on both sides, and every retriever looked brilliant until I caught it. Market prices were
calibrated on about 733,000 real Upwork postings and 1.3 million freelance contracts from public Kaggle datasets.

The dev set had 600 jobs with gold labels: should you bid, is it a scam, which portfolio items prove fit, and what a
fair price band looks like. A separate held-out set from a different random seed was used exactly once.

## Surprise one: the reranker made things worse

The standard recipe says a cross-encoder reranker improves precision at small k. On this corpus, the off-the-shelf
MS-MARCO MiniLM reranker *lowered* Recall@5 from 0.556 to about 0.43. It was also the slowest component in the
pipeline by two orders of magnitude.

In hindsight the reason is obvious. MS-MARCO is web search: short questions matched to answer passages. "Must have
hands-on experience with Celery" matched against a case study bullet about "background task queues with retries" is
not that task. A reranker brings its training distribution with it.

Requirement decomposition did worse still (0.403). Splitting a post into sentences produces sub-queries like
"Deliverables: working app; short documentation", and reciprocal rank fusion dutifully gives them equal votes. My
hypothesis was refuted on both of its legs.

What won was the least fashionable option: a small **skill graph** of skills, projects, industries and outcomes,
fused with dense retrieval. It reached Recall@5 0.686, MRR 0.836 and nDCG@10 0.739. But a per-job-type breakdown
showed its weakness. On *vague* posts that never name a tool, the graph scored 0.395, worse than naive dense retrieval
at 0.443, because a graph cannot match a skill nobody named. I shipped it anyway, because most real posts name their
tools, and documented the trade-off. There is also an honest caveat: my gold labels are defined by skill overlap, so
part of the graph's advantage is built in. The vague-post result is the counterweight that keeps me honest.

## Surprise two: none of it changed the reply rate

This was the result I didn't expect. I ran the full pipeline on the same 24 jobs twice: once with the shipped skill
graph and once with naive dense retrieval. GigSim's simulated clients then read every final proposal under ten random
seeds each.

- Skill graph: **38.3%** reply rate
- Naive dense: **37.9%** reply rate
- A generic "Dear Sir/Madam, I am passionate…" template: **6.3%**

A 13-point gain in Recall@5 bought 0.4 points of replies, which is noise.

The explanation is about what a client actually reads. A proposal cites two, maybe three, past projects. Once
*any* relevant project with a concrete number makes it into the letter, the client's checklist is satisfied: their
must-have skill is mentioned, a measured result appears, and the opening isn't generic. Retrieval quality beyond the
top two items is invisible to the reader. All the metrics I had optimised (Recall@5, nDCG@10) describe the shape of a
ranked list that nobody downstream ever sees.

The gap that mattered was the one between *any* grounded, specific proposal and a template, which is a sixfold
difference. The gap between good retrieval and better retrieval was zero.

## What did move things

**Writing strategy.** An A/B test of two proposal styles (open with the client's problem and two cited projects, or
open with a clarifying question) gave 38.3% against 31.3% replies. The difference is consistent, but with p = 0.10 it
is not significant at this sample size. That result is reported as a lean, not a win.

**Decision thresholds, not retrieval.** The biggest real-world lever was whether the system bid at all. My Fit
Matcher was too conservative: precision 0.94, but recall 0.45, so it skipped more than half the jobs it should have bid
on. Recalibrating one threshold raised bid/skip F1 from 0.61 to 0.82 on the dev set and 0.74 on the held-out set. The
held-out number is lower, which is exactly why you keep a held-out set. A missed bid costs far more replies than a
slightly worse evidence ranking.

**Grounding is a different axis.** I also compared three architectures on the same open model: a single ReAct agent
holding every tool, a prebuilt LangGraph supervisor, and my hand-built graph. The supervisor made the best bid/skip
calls (0.83 against 0.67). It also produced proposals with one unsupported claim each, while mine had none, because a
dedicated verifier checks every claim against the cited evidence before a critic ever sees the draft. If you only
measure reply rate, invented experience looks free. In a simulator it is. On a real marketplace it gets you banned.

## The lesson I'm keeping

Optimise the metric your *end user* experiences, and measure how far your proxy metrics actually reach. Retrieval
metrics are easy to compute, beautifully sensitive and endlessly tunable, so it is tempting to spend a week moving
nDCG. But they sit three steps away from the outcome. Retrieval feeds a writer, the writer feeds a critic, and the
critic feeds a human who reads two paragraphs. Each step compresses the signal.

Two more small lessons from the same project:

- **Calibrate your judge before trusting it.** My LLM judge agreed with my own labels at Cohen's kappa 0.40
  (moderate), and only 0.18 on pass/fail. It was systematically harsher than me, and when I looked at the
  disagreements, it was often right: it penalised proposals that skipped a must-have requirement I had glossed over.
- **Keep rules in configuration.** Halfway through, the simulated platform changed its policy: a Connects surcharge
  for unverified clients, a daily submission cap, and shorter cover letters. Absorbing it took about 22 changed lines in
  four files, none of them prompts or graph code.

Negative results are less fun to present than leaderboards. "The reranker made it worse" and "better retrieval
didn't change outcomes" were the two most useful things this project told me, and I would not have found either if I
had stopped measuring at nDCG.

*Code, data card and every number above: github.com/Hudiyahaha/GigBid (each figure traces to a file in
`evals/results/`).*
