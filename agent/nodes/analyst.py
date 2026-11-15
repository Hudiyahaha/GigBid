"""Job Analyst (no MCP access): structured JobSpec from the (sanitised, delimited) job post."""

from __future__ import annotations

from agent import llm
from agent.guardrails import delimit
from agent.handoffs import JobSpec, Requirement
from agent.nodes.base import node
from rag.ingest.skills import canonical, detect_skills
from rag.query import decompose


def heuristic_spec(job: dict) -> dict:
    text = job.get("clean_description") or job.get("description", "")
    reqs: list[Requirement] = []
    seen = set()
    for sent in decompose(text):
        skills = detect_skills(sent)
        if skills:
            for s in skills:
                if s in seen or (s == "Python" and "python" not in sent.lower()):
                    continue
                seen.add(s)
                reqs.append(Requirement(skill=s, importance="nice" if "bonus" in sent.lower() else "must", query=sent))
        else:
            reqs.append(Requirement(skill=sent[:80], importance="nice" if "bonus" in sent.lower() else "must", query=sent))
    b = job.get("budget") or {}
    return JobSpec(job_id=job["job_id"], title=job.get("title", ""), category=job.get("category", ""),
                   deliverables=[d.strip() for d in (text.split("Deliverables:")[-1].split(";") if "Deliverables:" in text else [])][:5],
                   requirements=reqs[:10], budget_type=b.get("type", "unknown"), budget_min=b.get("min"),
                   budget_max=b.get("max"), timeline=job.get("duration", ""),
                   screening_questions=job.get("screening_questions", []), vague=not detect_skills(text)).model_dump()


@node("job_analyst")
async def job_analyst(state: dict) -> dict:
    job = state["job"]
    variables = {"job_id": job["job_id"], "title": job.get("title", ""), "budget": job.get("budget"),
                 "questions": job.get("screening_questions", []),
                 "job": delimit("job_post", job.get("clean_description") or job.get("description", ""))}
    spec, meta = await llm.call_json("job_analyst", "job_analyst", variables, JobSpec, heuristic=lambda: heuristic_spec(job))
    # authoritative fields come from the marketplace record, not from the model
    b = job.get("budget") or {}
    spec.job_id, spec.title = job["job_id"], job.get("title", spec.title)
    spec.category = job.get("category") or spec.category
    spec.budget_type, spec.budget_min, spec.budget_max = b.get("type", spec.budget_type), b.get("min"), b.get("max")
    spec.screening_questions = job.get("screening_questions", []) or spec.screening_questions
    for r in spec.requirements:
        r.skill = canonical(r.skill)
        r.query = r.query or r.skill
    return {"job_spec": spec.model_dump(), "trace": [{"type": "llm", "node": "job_analyst", **meta}]}
