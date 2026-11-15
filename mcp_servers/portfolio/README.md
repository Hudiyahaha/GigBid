# GigBid Portfolio MCP server

Read-only MCP server that lets any MCP host (Claude Desktop, Cursor, ...) search a freelancer's portfolio for
**evidence**: case studies, repos (README and code), client reviews, CV and past proposals with outcomes.

* Tools: `search_evidence(requirement, k, filters)`, `get_case_study(id)`, `get_item(id)`, `list_skills()`,
  `similar_proposals(query, k)`
* Resources: `portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://repo/{id}`, `portfolio://cv`
* Prompts: *Answer a screening question from my portfolio*, *Show my fit for a job post*, *Write a two-line case-study blurb*

Retrieval is hybrid BM25 + dense with outcome-aware ranking (chosen by evaluation, see the main README).

## Install
```
uvx --from git+https://github.com/<you>/gigbid gigbid-portfolio-mcp
```
or with Docker: `docker run -i --rm -e PORTFOLIO_PERSONA=ai_ml gigbid:latest python -m mcp_servers.portfolio.server stdio`

Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"portfolio": {"command": "uvx",
  "args": ["--from", "git+https://github.com/<you>/gigbid", "gigbid-portfolio-mcp"],
  "env": {"PORTFOLIO_PERSONA": "ai_ml"}}}}
```
Your own portfolio: put Markdown case studies in `data/personas/<name>/case_studies/` (front matter: id, title, project,
date, client_industry) and set `PORTFOLIO_PERSONA=<name>`.
