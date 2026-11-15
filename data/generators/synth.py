"""Deterministic SYNTHETIC data generator for GigBid.

Generates (all labelled `source: synthetic`):
  data/personas/<pid>/          CV (md+pdf), case studies, repos (README+code), reviews, past proposals
  gigsim/seed/                  clients, historical jobs, live job stream, dev jobs, hidden client prefs, accounts
  evals/datasets/               dev sets with gold labels (bid/skip, scam, evidence, fair price band)
  data/holdout/                 a held-out "hidden test" set (different seed, git-ignored)

If data/processed/market_stats.json exists (built from Kaggle by kaggle_stats.py), prices are
calibrated to the real distributions; otherwise built-in defaults are used.

Usage:  python -m data.generators.synth --seed 42
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from data.generators.ontology import (
    CATEGORIES, DOMAIN_SKILLS, GENERIC_OPENINGS, INDUSTRIES, INJECTIONS, JOB_PHRASES, PROJECT_ARCHETYPES, SCAM_PATTERNS,
    SKILLS,
)
from gigsim.sim_client import HiddenPrefs, decide

ROOT = Path(__file__).resolve().parents[2]
ALL_SKILLS = list(SKILLS.keys())

PERSONAS = {
    "ai_ml": dict(name="Ayesha Rahman", headline="AI/ML Engineer - LLM apps, RAG and production ML",
                  hourly_floor=45, min_project=400, years=6, location="Lahore, Pakistan (remote)"),
    "fullstack": dict(name="Daniel Okafor", headline="Full-Stack Web Developer - React, Next.js, Node",
                      hourly_floor=40, min_project=350, years=7, location="Lagos, Nigeria (remote)"),
    "data": dict(name="Mei Lin", headline="Data Analyst - SQL, BI dashboards and experimentation",
                 hourly_floor=30, min_project=200, years=5, location="Kuala Lumpur, Malaysia (remote)"),
}

# default market priors per domain (fixed-price median USD, hourly median USD); overridden by Kaggle stats
DEFAULT_MARKET = {"ai_ml": (1400, 55), "fullstack": (1200, 45), "data": (700, 35), "other": (600, 30)}

COMPANY_A = ["Blue", "North", "Bright", "Clear", "Swift", "Iron", "Silver", "Green", "Nova", "Peak", "Delta",
             "Harbor", "Maple", "Orbit", "Quartz", "Summit", "Atlas", "Cobalt", "Ember", "Lumen"]
COMPANY_B = ["fin", "path", "leaf", "stone", "wave", "line", "bridge", "field", "point", "forge", "nest", "gate"]
COMPANY_C = ["Analytics", "Labs", "Health", "Logistics", "Retail", "Legal", "Studio", "Systems", "Group",
             "Ventures", "Learning", "Foods", "Travel", "Media", "Capital"]
COUNTRIES = ["United States", "United Kingdom", "Canada", "Germany", "Australia", "UAE", "Netherlands",
             "Singapore", "India", "France", "Sweden", "Ireland"]


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _wj(path: Path, obj) -> None:
    _w(path, json.dumps(obj, indent=2, ensure_ascii=False))


def _fill(tpl: str, rng: random.Random) -> str:
    return tpl.format(pct=rng.randint(18, 64), n1=rng.randint(2, 6), n2=rng.randint(12, 94),
                      n3=rng.choice([350, 800, 1200, 2500, 4000, 12000]))


def load_market() -> dict:
    p = ROOT / "data" / "processed" / "market_stats.json"
    m = {d: {"fixed_median": v[0], "hourly_median": v[1], "source": "default prior"} for d, v in DEFAULT_MARKET.items()}
    if p.exists():
        stats = json.loads(p.read_text(encoding="utf-8"))
        for d, s in stats.get("by_domain", {}).items():
            if d in m:
                m[d].update({k: s[k] for k in ("fixed_median", "hourly_median") if s.get(k)})
                m[d]["source"] = "kaggle"
    return m


def calibrate_personas(market: dict) -> None:
    """Persona floors follow the real market when Kaggle stats exist: an experienced freelancer asks a little
    above the median hourly rate and takes fixed projects from ~80% of the median budget."""
    for pid, meta in PERSONAS.items():
        mk = market[pid]
        if mk["source"] == "kaggle":
            meta["hourly_floor"] = int(round(mk["hourly_median"] * 1.1))
            meta["min_project"] = int(round(mk["fixed_median"] * 0.8, -1))


def kaggle_jobs(name: str) -> list[dict]:
    p = ROOT / "data" / "processed" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def hidden_for_real_job(job: dict, rng: random.Random) -> dict:
    """Real Kaggle jobs have no hidden client preferences; synthesise them (labelled synthetic) so GigSim's
    simulated client can react if a proposal is sent."""
    from rag.ingest.skills import detect_skills
    reqs = detect_skills(job["title"] + " " + job["description"]) or [job["category"]]
    tv = float(job["budget"]["max"] or 1)
    return dict(job_id=job["job_id"], requirements=reqs, scam=False, scam_type=None, injection_id=None, vague=False,
                true_value=tv, real=True,
                prefs=dict(must_have=reqs[:1], ceiling=round(tv * rng.uniform(1.0, 1.2), 1),
                           dislikes_generic=rng.random() < 0.6, prefers_concise=rng.random() < 0.5, true_value=tv,
                           pay_type=job["budget"]["type"]))


# ------------------------------------------------------------------ personas
def build_projects(pid: str, rng: random.Random) -> list[dict]:
    projects = []
    archetypes = list(PROJECT_ARCHETYPES[pid])
    # each persona never did 3 of the 10 archetypes -> real skill gaps (partial / no-fit jobs)
    for _ in range(3):
        archetypes.pop(rng.randrange(len(archetypes)))
    pool = sorted({s for a in archetypes for s in a[2]})
    k = 0
    for rep in range(3):
        for title, problem, core, outcome in (archetypes if rep < 2 else archetypes[:6]):
            skills = list(core)
            if rep >= 1:  # perturb: drop one, add one other skill the persona already has
                skills.pop(rng.randrange(len(skills)))
                extra = [s for s in pool if s not in skills]
                if extra:
                    skills.append(rng.choice(extra))
            industry = rng.choice(INDUSTRIES)
            year = rng.randint(2021, 2026)
            k += 1
            projects.append(dict(
                project_id=f"{pid}-p{k:02d}",
                title=(title if rep == 0 else f"{title} v2 ({industry})" if rep == 1 else f"{title} for a {industry} client"),
                problem=problem, skills=skills, industry=industry,
                date=f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                outcome=_fill(outcome, rng), client=_company(rng), has_repo=rng.random() < 0.65,
                has_review=rng.random() < 0.7, duration_weeks=rng.randint(3, 16)))
    # persona never uses a few in-domain skills (creates partial-fit jobs)
    return projects


def _company(rng: random.Random) -> str:
    return f"{rng.choice(COMPANY_A)}{rng.choice(COMPANY_B)} {rng.choice(COMPANY_C)} (synthetic)"


def persona_skillset(projects: list[dict]) -> set[str]:
    s: set[str] = set()
    for p in projects:
        s.update(p["skills"])
    return s


def case_study_md(p: dict, pid: str, rng: random.Random) -> tuple[str, list[str]]:
    explicit, implied = [], []
    for s in p["skills"]:
        (explicit if rng.random() < 0.5 else implied).append(s)
    if not explicit:
        explicit.append(implied.pop())
    lines = [
        "---", f"id: cs-{p['project_id']}", f"persona: {pid}", "type: case_study", f"project: {p['project_id']}",
        f"title: {p['title']}", f"date: {p['date']}", f"client_industry: {p['industry']}",
        f"skills_listed: [{', '.join(explicit)}]", "source: synthetic", "---", "",
        f"# {p['title']}", "",
        f"**Client:** {p['client']} ({p['industry']}) | **Duration:** {p['duration_weeks']} weeks | **Year:** {p['date'][:4]}",
        "", "## The problem", f"The client came to me because {p['problem']}.", "", "## What I did",
    ]
    for s in explicit:
        imp = SKILLS[s][1]
        lines.append(f"- {imp[0].upper() + imp[1:]}, using {s}." if rng.random() < 0.6 else f"- Used {s} for the core of the solution.")
    for s in implied:
        lines.append(f"- {SKILLS[s][1][0].upper() + SKILLS[s][1][1:]}.")
    lines += ["", "## Result", f"The project {p['outcome']} within the first months after launch.", "",
              "## What I would do differently",
              rng.choice(["Add monitoring from day one.", "Agree on evaluation metrics before building.",
                          "Write the runbook earlier.", "Involve end users in week one."]), ""]
    return "\n".join(lines), explicit


def repo_files(p: dict, pid: str, rng: random.Random) -> dict[str, str]:
    slug = re.sub(r"[^a-z0-9]+", "-", p["title"].lower()).strip("-")[:40]
    named = rng.choice(p["skills"])
    readme = (
        f"# {slug}\n\n> source: synthetic | persona: {pid} | project: {p['project_id']}\n\n"
        f"Built for a {p['industry']} client. The problem: {p['problem']}.\n\n"
        f"## Features\n- {SKILLS[rng.choice(p['skills'])][1].capitalize()}\n- Configuration through environment variables\n"
        f"- Unit tests and a small demo dataset\n\n## Stack\nMostly {named}, plus the usual supporting libraries.\n\n"
        f"## Results\nIn production this {p['outcome']}.\n"
    )
    files = {"README.md": readme}
    by_ext: dict[str, list[str]] = {}
    for s in p["skills"]:
        dom, _imp, code, ext = SKILLS[s]
        if code:
            by_ext.setdefault(ext, []).append(code)
    names = {"py": "src/main.py", "ts": "src/index.ts", "tsx": "src/App.tsx", "js": "src/server.js",
             "sql": "models/core.sql", "Dockerfile": "Dockerfile", "yml": ".github/workflows/ci.yml"}
    for ext, codes in by_ext.items():
        fname = names.get(ext, f"src/extra.{ext}")
        body = "\n".join(codes)
        if ext == "py":
            body += ("\n\n\ndef run(config: dict) -> dict:\n    \"\"\"Entry point used by the scheduler.\"\"\"\n"
                     "    results = {}\n    # load, transform, score, persist\n    return results\n")
        files[fname] = body + "\n"
    pkgs = []
    for s in p["skills"]:
        if SKILLS[s][3] == "py":
            m = re.match(r"(?:from|import)\s+([A-Za-z_]\w*)", SKILLS[s][2])
            if m and m.group(1) not in ("sys", "re", "os") and m.group(1) not in pkgs:
                pkgs.append(m.group(1))
    if pkgs:
        files["requirements.txt"] = "\n".join(pkgs) + "\n"
    return files


def review_for(p: dict, pid: str, rng: random.Random) -> dict:
    stars = rng.choices([5, 4, 3], weights=[0.7, 0.24, 0.06])[0]
    praise = rng.choice(["clear communication", "delivered ahead of schedule", "thoughtful about edge cases",
                         "great documentation", "proactive with suggestions"])
    text = (f"{'Excellent' if stars == 5 else 'Good' if stars == 4 else 'Okay'} work on our {p['title'].lower()}. "
            f"{p['outcome'].capitalize()}. {praise.capitalize()}."
            + (" Some delays in the second milestone." if stars == 3 else ""))
    return dict(id=f"rev-{p['project_id']}", persona=pid, type="review", project=p["project_id"],
                client=p["client"], client_industry=p["industry"], stars=stars, date=p["date"], text=text,
                source="synthetic")


def cv_md(pid: str, meta: dict, projects: list[dict], rng: random.Random) -> str:
    skills = sorted(persona_skillset(projects))
    listed = [s for s in skills if rng.random() < 0.7]
    roles = []
    year = 2026
    for i in range(3):
        start = year - rng.randint(1, 3)
        roles.append(f"### {rng.choice(['Senior ', '', 'Lead ']) if i == 0 else ''}{meta['headline'].split(' - ')[0]} - "
                     f"{_company(rng)}  ({start}-{year if i else 'present'})\n"
                     f"- Worked on {projects[i * 3]['title'].lower()} and {projects[i * 3 + 1]['title'].lower()}.\n"
                     f"- {projects[i * 3]['outcome'].capitalize()}.\n")
        year = start
    return (f"---\nid: cv-{pid}\npersona: {pid}\ntype: cv\nsource: synthetic\n---\n\n# {meta['name']} (synthetic persona)\n\n"
            f"**{meta['headline']}** | {meta['location']} | {meta['years']} years of experience\n\n"
            f"## Summary\nFreelance {meta['headline'].split(' - ')[0].lower()} who ships measurable results for small and "
            f"mid-size clients. Prefers clear scopes, weekly demos and written hand-overs.\n\n"
            f"## Skills\n{', '.join(listed)}\n\n## Experience\n" + "\n".join(roles) +
            "\n## Education\nBS Computer Science (synthetic institution), 2019\n")


def cv_pdf(md: str, path: Path) -> None:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in md.splitlines():
        if line.strip() in ("---",) or re.match(r"^(id|persona|type|source):", line):
            continue
        txt = line.replace("**", "").replace("#", "").encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 5, txt or " ", new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


# ------------------------------------------------------------------ clients
def build_clients(n: int, rng: random.Random) -> list[dict]:
    clients = []
    for i in range(n):
        shady = rng.random() < 0.12
        posted = rng.randint(0, 3) if shady else rng.randint(1, 80)
        hires = 0 if shady else rng.randint(0, posted)
        spent = 0 if shady else round(rng.lognormvariate(8.5, 1.3), 0)
        rating = None if hires == 0 else round(rng.uniform(3.0 if rng.random() < 0.15 else 4.2, 5.0), 2)
        clients.append(dict(
            client_id=f"cl-{i:04d}", name=_company(rng), industry=rng.choice(INDUSTRIES),
            country=rng.choice(COUNTRIES), payment_verified=(not shady and rng.random() < 0.9) or rng.random() < 0.15,
            jobs_posted=posted, hires=hires, hire_rate=round(hires / posted, 2) if posted else 0.0,
            total_spent_usd=spent, avg_rating_given=rating,
            member_since=f"{rng.randint(2012, 2026)}-{rng.randint(1, 12):02d}-01",
            reviews_from_freelancers=[rng.choice(["Clear requirements, paid on time.", "Responsive and fair.",
                                                  "Scope changed a lot mid-project.", "Great to work with."])
                                      for _ in range(min(hires, 3))],
            _shady=shady, source="synthetic"))
    return clients


# ------------------------------------------------------------------ jobs
REQ_EXPLICIT = ["Must have hands-on experience with {s}.", "Strong {s} skills required.",
                "You will be working mainly in {s}.", "Experience with {s} is a must.", "{s} knowledge is important."]
REQ_IMPLIED = ["We need someone who {i}.", "Ideally you are someone who {i}.", "Looking for a person who {i}.",
               "Bonus if you're someone who {i}."]
INTROS = ["We are a {ind} company looking for help with this project:", "Our small {ind} startup needs a freelancer for:",
          "I run a {ind} business and want to hire someone for:", "Our {ind} team needs an experienced specialist for:"]
NEEDS = ["{t}.", "{t}.", "{t} (details below).", "{t} - see requirements."]
VAGUE = ["I need someone to make sense of this mess and make it work better for our customers.",
         "Our current setup is slow and confusing. Looking for an expert to fix it properly.",
         "We have the data and the idea; we need someone who knows what they are doing to make it real."]
QUESTIONS = ["Describe a recent project where you used {s}.", "How would you approach the first two weeks?",
             "What is your availability per week?", "How do you measure success for this kind of project?",
             "Which part of this project do you see as the biggest risk?"]
TITLE_T = {"LLM apps & RAG": ["Build a RAG chatbot over our documents", "LLM assistant for internal knowledge base",
                              "AI agent to automate {ind} workflows"],
           "ML modelling": ["Predictive model for customer churn", "Build a lead-scoring ML model", "Fraud detection model"],
           "Computer vision": ["Object detection for {ind} images", "Computer vision quality inspection"],
           "NLP": ["Text classification for support tickets", "Named entity extraction from documents"],
           "MLOps": ["Deploy our ML models to production", "Set up model monitoring and CI/CD for ML"],
           "Forecasting": ["Sales forecasting model", "Demand forecast for {ind} inventory"],
           "Web app": ["Build a booking web app", "SaaS dashboard MVP in Next.js", "Customer portal for {ind}"],
           "E-commerce": ["Shopify store with subscriptions", "Add Stripe checkout to our store"],
           "API backend": ["REST API for mobile app backend", "Scale our Node.js backend", "GraphQL API for {ind} platform"],
           "Frontend UI": ["Convert Figma designs to React", "Responsive frontend for {ind} site"],
           "Realtime & serverless": ["Realtime notifications service", "Serverless backend migration"],
           "Testing & DevOps": ["Add end-to-end tests and CI", "Set up GitHub Actions pipeline"],
           "Dashboards & BI": ["Power BI sales dashboard", "Tableau dashboard for {ind} KPIs", "Build management dashboards"],
           "Data engineering": ["dbt models on Snowflake", "Build an ETL pipeline into BigQuery"],
           "Analytics & statistics": ["Analyse our A/B test results", "Statistical analysis of survey data"],
           "Spreadsheet automation": ["Automate Excel reports", "Google Sheets automation with Apps Script"],
           "Marketing analytics": ["GA4 setup and marketing dashboard", "Attribution analysis for ad spend"],
           "Mobile apps": ["iOS and Android app for {ind}", "Native mobile app MVP"], "Games": ["Unity 3D mini game"],
           "Blockchain": ["NFT smart contract development"], "CRM": ["Salesforce customisation"],
           "Content & design": ["Logo and brand kit", "YouTube video editor needed", "SEO blog writer"],
           "CMS": ["WordPress site fixes"], "Embedded & systems": ["Firmware for IoT sensor", "Rust microservice"],
           "Finance": ["Bookkeeping for small business"]}


def make_job(job_id: str, domain: str, category: str, rng: random.Random, clients: list[dict], market: dict,
             posted: datetime, kind: str = "normal", force_skills: list[str] | None = None) -> tuple[dict, dict]:
    """Return (public job, hidden info incl. gold-relevant fields)."""
    cat_skills = CATEGORIES[domain][category]
    n_req = rng.choices([2, 3, 4, 5, 6], weights=[0.15, 0.3, 0.28, 0.17, 0.10])[0]
    reqs = force_skills or rng.sample(cat_skills, min(n_req, len(cat_skills)))
    if len(reqs) < n_req and domain != "other":  # add adjacent in-domain skills
        extra = [s for s in DOMAIN_SKILLS[domain] if s not in reqs]
        reqs += rng.sample(extra, min(n_req - len(reqs), len(extra)))
    if kind == "partial" or (domain != "other" and rng.random() < 0.12):
        reqs.append(rng.choice(DOMAIN_SKILLS["other"]))
    ind = rng.choice(INDUSTRIES)
    client = rng.choice([c for c in clients if (c["_shady"] if kind == "scam" else not c["_shady"])])
    title = rng.choice(TITLE_T.get(category, ["Freelance project"])).format(ind=ind)
    vague = kind == "vague"
    parts = [rng.choice(INTROS).format(ind=ind) + " " + rng.choice(NEEDS).format(t=title)]
    if vague:
        parts.append(rng.choice(VAGUE))
    explicit_tags = []
    for s in reqs:
        if vague or (rng.random() < 0.35 and s not in ("Python", "SQL")):
            parts.append(rng.choice(REQ_IMPLIED).format(i=JOB_PHRASES.get(s, SKILLS[s][1])))
        else:
            parts.append(rng.choice(REQ_EXPLICIT).format(s=s))
            explicit_tags.append(s)
    deliverables = [f"Working {title.lower()}", "Short documentation and a hand-over call"]
    parts.append("Deliverables: " + "; ".join(deliverables) + ".")
    # price
    med_fixed = market[domain]["fixed_median"]
    med_hourly = market[domain]["hourly_median"]
    pay_type = "hourly" if rng.random() < 0.35 else "fixed"
    complexity = 0.6 + 0.18 * len(reqs)
    if pay_type == "fixed":
        true_value = round(med_fixed * complexity * rng.lognormvariate(0, 0.35), -1)
        bmax = round(true_value * rng.uniform(0.7, 1.4), -1)
        budget = {"type": "fixed", "min": round(bmax * 0.6, -1), "max": bmax, "currency": "USD"}
    else:
        true_value = round(med_hourly * (0.8 + 0.08 * len(reqs)) * rng.lognormvariate(0, 0.25), 0)
        bmax = round(true_value * rng.uniform(0.75, 1.3), 0)
        budget = {"type": "hourly", "min": round(bmax * 0.6, 0), "max": bmax, "currency": "USD"}
    scam_type = None
    if kind == "scam":
        scam_type = rng.choice(list(SCAM_PATTERNS))
        parts.append(rng.choice(SCAM_PATTERNS[scam_type]))
        if scam_type == "free_work":
            budget["max"] = budget["min"] = 0
    injection_id = None
    if kind == "injection":
        injection_id = rng.randrange(len(INJECTIONS))
        parts.insert(rng.randint(1, len(parts)), INJECTIONS[injection_id])
    duration = rng.choice(["Less than 1 month", "1 to 3 months", "3 to 6 months"])
    qs = rng.sample(QUESTIONS, rng.randint(0, 3))
    qs = [q.format(s=rng.choice(reqs)) for q in qs]
    connects = 4 + 2 * min(4, int(budget["max"] // 500)) if pay_type == "fixed" else 4 + 2 * min(4, int(budget["max"] // 20))
    job = dict(job_id=job_id, title=title, description=" ".join(parts), category=category, domain=domain,
               skills_tags=explicit_tags[: rng.randint(1, max(1, len(explicit_tags)))] if explicit_tags else [],
               budget=budget, duration=duration, experience_level=rng.choice(["Entry", "Intermediate", "Expert"]),
               client_id=client["client_id"], industry=ind, posted_at=posted.isoformat() + "Z",
               connects_cost=int(connects), screening_questions=qs, proposals_count=rng.randint(0, 60),
               source="synthetic")
    must = rng.sample(reqs, min(len(reqs), rng.choice([1, 2])))
    hidden = dict(job_id=job_id, requirements=reqs, scam=kind == "scam", scam_type=scam_type,
                  injection_id=injection_id, vague=vague, true_value=true_value,
                  prefs=dict(must_have=must, ceiling=round(max(budget["max"], true_value) * rng.uniform(1.0, 1.25), 1),
                             dislikes_generic=rng.random() < 0.6, prefers_concise=rng.random() < 0.5,
                             true_value=true_value, pay_type=pay_type))
    return job, hidden


def gold_evidence(reqs: list[str], items: list[dict]) -> dict[str, int]:
    gold = {}
    rs = set(reqs)
    for it in items:
        ov = len(rs & set(it["_skills"]))
        if ov:
            gold[it["id"]] = ov if it["type"] != "review" else 1
    return gold


def gold_label(job: dict, hidden: dict, persona_pid: str, skills: set[str], clients_by_id: dict) -> dict:
    reqs = hidden["requirements"]
    coverage = sum(1 for r in reqs if r in skills) / len(reqs)
    meta = PERSONAS[persona_pid]
    c = clients_by_id[job["client_id"]]
    bad_client = (not c["payment_verified"] and c["hires"] == 0) or (c["avg_rating_given"] or 5) < 3.5
    b = job["budget"]
    price_ok = (b["max"] >= meta["min_project"] * 0.8) if b["type"] == "fixed" else (b["max"] >= meta["hourly_floor"] * 0.75)
    bid = (not hidden["scam"]) and coverage >= 0.6 and not bad_client and price_ok
    reasons = []
    if hidden["scam"]:
        reasons.append(f"scam:{hidden['scam_type']}")
    if coverage < 0.6:
        reasons.append(f"low coverage {coverage:.2f}")
    if bad_client:
        reasons.append("risky client history")
    if not price_ok:
        reasons.append("budget below floor")
    tv = hidden["true_value"]
    return dict(bid=bid, coverage=round(coverage, 2), skip_reasons=reasons, fair_band=[round(tv * 0.8, 1), round(tv * 1.2, 1)])


# ------------------------------------------------------------------ past proposals
def past_proposals(pid: str, projects: list[dict], skills: set[str], rng: random.Random, market: dict,
                   clients: list[dict], n: int = 150) -> list[dict]:
    out = []
    cats = list(CATEGORIES[pid])
    for i in range(n):
        cat = rng.choice(cats)
        posted = datetime(2023, 1, 1) + timedelta(days=rng.randint(0, 1000))
        job, hidden = make_job(f"hist-{pid}-{i:03d}", pid, cat, rng, clients, market, posted)
        style = rng.random()
        rel = sorted(projects, key=lambda p: -len(set(p["skills"]) & set(hidden["requirements"])))[:2]
        if style < 0.3:  # generic
            text = (f"{rng.choice(GENERIC_OPENINGS)} I have {PERSONAS[pid]['years']} years of experience and I can "
                    f"deliver high quality work on time. Please message me to discuss. Thank you.")
            cited = []
        else:
            p0 = rel[0]
            mh = hidden["prefs"]["must_have"]
            lead = (f"Your {job['title'].lower()} sounds close to the {p0['title']} I built for a {p0['industry']} client, "
                    f"where I {SKILLS[p0['skills'][0]][1]}.") if style > 0.55 else \
                (f"Hi, I read your post about {job['title'].lower()}.")
            body = f" On that project I used {', '.join(s for s in p0['skills'][:3])}, and it {p0['outcome']}."
            if style > 0.7 and len(rel) > 1:
                body += f" I also delivered {rel[1]['title'].lower()}, which {rel[1]['outcome']}."
            if style > 0.8:
                body += f" For you I'd start with {mh[0]}, then agree milestones in week one."
            text = lead + body + " Happy to share code samples."
            cited = [p["project_id"] for p in (rel if style > 0.7 else rel[:1])]
        tv = hidden["true_value"]
        bid = round(tv * rng.uniform(0.8, 1.3), -1 if job["budget"]["type"] == "fixed" else 0)
        answers = [f"In my {rel[0]['title']} project I handled this directly and documented the outcome."
                   for _ in job["screening_questions"]] if style > 0.5 else []
        d = decide(text, job, bid, HiddenPrefs(**hidden["prefs"]), skills, answers, run_seed="history",
                   all_skill_names=ALL_SKILLS)
        outcome = "won" if d.hire or (d.interview and rng.random() < 0.5) else ("replied" if d.reply else "ignored")
        out.append(dict(id=f"prop-{pid}-{i:03d}", persona=pid, type="proposal", job_title=job["title"],
                        job_category=cat, job_excerpt=job["description"][:240], date=posted.date().isoformat(),
                        bid_usd=bid, pay_type=job["budget"]["type"], text=text, screening_answers=answers,
                        projects_cited=cited, outcome=outcome, source="synthetic"))
    return out


# ------------------------------------------------------------------ main
def generate(seed: int = 42, out_root: Path = ROOT, holdout_seed: int = 9001) -> dict:
    rng = random.Random(seed)
    market = load_market()
    calibrate_personas(market)
    personas_dir = out_root / "data" / "personas"
    seed_dir = out_root / "gigsim" / "seed"
    ds_dir = out_root / "evals" / "datasets"
    for d in (personas_dir, seed_dir, ds_dir):
        if d.exists():
            shutil.rmtree(d)
    clients = build_clients(420, rng)
    clients_by_id = {c["client_id"]: c for c in clients}
    summary = {"seed": seed, "market_source": {d: m["source"] for d, m in market.items()}, "personas": {}}
    persona_skills: dict[str, list[str]] = {}
    persona_items: dict[str, list[dict]] = {}
    accounts = []
    for pid, meta in PERSONAS.items():
        prng = random.Random(f"{seed}-{pid}")
        projects = build_projects(pid, prng)
        skills = persona_skillset(projects)
        persona_skills[pid] = sorted(skills)
        base = personas_dir / pid
        items: list[dict] = []
        for p in projects:
            md, _explicit = case_study_md(p, pid, prng)
            _w(base / "case_studies" / f"cs-{p['project_id']}.md", md)
            items.append({"id": f"cs-{p['project_id']}", "type": "case_study", "_skills": p["skills"], "project": p["project_id"]})
            if p["has_repo"]:
                files = repo_files(p, pid, prng)
                rdir = base / "repos" / f"repo-{p['project_id']}"
                for fn, body in files.items():
                    _w(rdir / fn, body)
                items.append({"id": f"repo-{p['project_id']}", "type": "repo", "_skills": p["skills"], "project": p["project_id"]})
            if p["has_review"]:
                items.append({**review_for(p, pid, prng), "_skills": p["skills"]})
        reviews = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items if it["type"] == "review"]
        _wj(base / "reviews.json", reviews)
        cv = cv_md(pid, meta, projects, prng)
        _w(base / "cv.md", cv)
        cv_pdf(cv, base / "cv.pdf")
        props = past_proposals(pid, projects, skills, prng, market, clients)
        _wj(base / "proposals.json", props)
        _wj(base / "profile.json", dict(persona_id=pid, display_name=f"{meta['name']} (synthetic)", headline=meta["headline"],
                                        hourly_floor_usd=meta["hourly_floor"], min_project_usd=meta["min_project"],
                                        years_experience=meta["years"], location=meta["location"],
                                        weekly_connects_budget=80, source="synthetic"))
        persona_items[pid] = items
        accounts.append(dict(account_id=f"acct-{pid}", persona=pid, token=f"gigsim-dev-token-{pid}", connects=120))
        outcomes = {o: sum(1 for x in props if x["outcome"] == o) for o in ("won", "replied", "ignored")}
        summary["personas"][pid] = dict(projects=len(projects), items=len(items), skills=len(skills),
                                        proposals=len(props), proposal_outcomes=outcomes)
    # gold project-skill map (for evaluation only; never read by retrievers)
    _wj(ds_dir / "gold_items.json", {pid: [{"id": i["id"], "type": i["type"], "project": i.get("project"),
                                           "skills": i["_skills"]} for i in its] for pid, its in persona_items.items()})
    _wj(ds_dir / "persona_skills.json", persona_skills)

    start = datetime(2026, 10, 27)
    # historical jobs (pricing statistics)
    history = []
    hrng = random.Random(f"{seed}-hist")
    for i in range(1500):
        dom = hrng.choices(["ai_ml", "fullstack", "data", "other"], weights=[0.27, 0.3, 0.28, 0.15])[0]
        cat = hrng.choice(list(CATEGORIES[dom]))
        j, h = make_job(f"h-{i:05d}", dom, cat, hrng, clients, market, start - timedelta(days=hrng.randint(30, 900)))
        j["final_price_usd"] = round(h["true_value"] * hrng.uniform(0.85, 1.1), 1)
        j["status"] = "closed"
        history.append(j)
    real_hist = kaggle_jobs("kaggle_history_jobs.json")
    for j in real_hist:  # real jobs carry no client; attach a synthetic client id so client history stays populated
        j["client_id"] = hrng.choice(clients)["client_id"]
    history += real_hist
    _wj(seed_dir / "jobs_history.json", history)

    # dev sets (200 per persona) + matching jobs in GigSim
    all_jobs, hidden_all = [], {}

    def build_set(tag: str, s: int, n_per: int) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        r = random.Random(s)
        for pid in PERSONAS:
            rows = []
            for k in range(n_per):
                roll = r.random()
                if roll < 0.12:
                    kind, dom = "scam", r.choice([pid, pid, "other"])
                elif roll < 0.18:
                    kind, dom = "injection", pid
                elif roll < 0.30:
                    kind, dom = "vague", pid
                elif roll < 0.45:
                    kind, dom = "partial", pid
                elif roll < 0.60:
                    kind, dom = "normal", r.choice([d for d in PERSONAS if d != pid] + ["other"])
                else:
                    kind, dom = "normal", pid
                cat = r.choice(list(CATEGORIES[dom]))
                jid = f"{tag}-{pid}-{k:03d}"
                job, hidden = make_job(jid, dom, cat, r, clients, market, start + timedelta(hours=k * 3), kind)
                g = gold_label(job, hidden, pid, set(persona_skills[pid]), clients_by_id)
                ge = gold_evidence(hidden["requirements"], persona_items[pid]) if g["coverage"] > 0 else {}
                rows.append(dict(job_id=jid, persona=pid, kind=kind, category=cat, domain=dom,
                                 n_requirements=len(hidden["requirements"]), requirements=hidden["requirements"],
                                 gold_bid=g["bid"], gold_scam=hidden["scam"], scam_type=hidden["scam_type"],
                                 injection_id=hidden["injection_id"], gold_coverage=g["coverage"],
                                 gold_skip_reasons=g["skip_reasons"], fair_band=g["fair_band"],
                                 pay_type=job["budget"]["type"], gold_evidence=ge))
                all_jobs.append(job)
                hidden_all[jid] = hidden
            out[pid] = rows
        return out

    dev = build_set("dev", seed + 1, 200)
    for pid, rows in dev.items():
        _w(ds_dir / f"dev_{pid}.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    # live stream: new jobs released over time, with duplicates, scams and injections
    srng = random.Random(f"{seed}-stream")
    stream = []
    for i in range(360):
        dom = srng.choice(list(PERSONAS) + ["other"])
        kind = srng.choices(["normal", "scam", "injection", "vague", "partial"], weights=[0.6, 0.12, 0.08, 0.1, 0.1])[0]
        if dom == "other" and kind in ("injection", "vague", "partial"):
            kind = "normal"
        cat = srng.choice(list(CATEGORIES[dom]))
        job, hidden = make_job(f"live-{i:04d}", dom, cat, srng, clients, market, start + timedelta(hours=i * 2), kind)
        job["release_tick"] = i // 12
        stream.append(job)
        hidden_all[job["job_id"]] = hidden
        if i > 10 and srng.random() < 0.08:  # duplicate repost
            src = srng.choice(stream[:-1])
            dup = dict(src, job_id=f"live-{i:04d}-r", title=src["title"] + (" (reposted)" if srng.random() < 0.5 else ""),
                       release_tick=i // 12, duplicate_of=src["job_id"])
            stream.append(dup)
            hidden_all[dup["job_id"]] = dict(hidden_all[src["job_id"]], job_id=dup["job_id"])
    good_clients = [c for c in clients if not c["_shady"]]
    for i, j in enumerate(kaggle_jobs("kaggle_stream_jobs.json")):  # real posts in the live stream (unlabelled)
        j = dict(j, job_id=f"live-kg-{i:04d}", release_tick=srng.randint(0, 29), client_id=srng.choice(good_clients)["client_id"],
                 posted_at=(start + timedelta(hours=srng.randint(0, 720))).isoformat() + "Z", status="open")
        j.pop("final_price_usd", None)
        stream.append(j)
        hidden_all[j["job_id"]] = hidden_for_real_job(j, srng)
    _wj(seed_dir / "jobs_stream.json", stream)
    _wj(seed_dir / "jobs_dev.json", all_jobs)
    _wj(seed_dir / "hidden_prefs.json", hidden_all)
    _wj(seed_dir / "clients.json", [{k: v for k, v in c.items() if not k.startswith("_")} for c in clients])
    _wj(seed_dir / "clients_hidden.json", {c["client_id"]: {"shady": c["_shady"]} for c in clients})
    _wj(seed_dir / "accounts.json", accounts)
    summary["dev"] = {pid: dict(n=len(r), bid=sum(x["gold_bid"] for x in r), scam=sum(x["gold_scam"] for x in r),
                                injection=sum(x["injection_id"] is not None for x in r)) for pid, r in dev.items()}
    summary["history_jobs"] = {"total": len(history), "real_kaggle": len(real_hist)}
    summary["stream_jobs"] = {"total": len(stream), "real_kaggle": sum(1 for j in stream if str(j.get("source", "")).startswith("kaggle"))}
    summary["persona_floors"] = {p: {"hourly_floor": m["hourly_floor"], "min_project": m["min_project"]} for p, m in PERSONAS.items()}

    # held-out "hidden test" set: different seed, written outside the committed tree
    all_jobs.clear()
    hidden_before = dict(hidden_all)
    hold = build_set("hold", holdout_seed, 60)
    hdir = out_root / "data" / "holdout"
    hdir.mkdir(parents=True, exist_ok=True)
    for pid, rows in hold.items():
        _w(hdir / f"holdout_{pid}.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    _wj(hdir / "jobs_holdout.json", all_jobs)
    _wj(hdir / "hidden_prefs_holdout.json", {k: v for k, v in hidden_all.items() if k not in hidden_before})
    _wj(out_root / "data" / "processed" / "synth_summary.json", summary)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    print(json.dumps(generate(args.seed), indent=2))
