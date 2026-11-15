---
id: cs-fullstack-p09
persona: fullstack
type: case_study
project: fullstack-p09
title: Logistics tracking API v2 (gaming)
date: 2022-03-15
client_industry: gaming
skills_listed: [Redis, REST API, WebSockets]
source: synthetic
---

# Logistics tracking API v2 (gaming)

**Client:** Clearleaf Learning (synthetic) (gaming) | **Duration:** 15 weeks | **Year:** 2022

## The problem
The client came to me because dispatchers could not see where trucks were in real time.

## What I did
- Cached hot reads in an in-memory key-value store, using Redis.
- Designed resource-oriented HTTP endpoints with pagination, using REST API.
- Pushed live updates to the browser over a persistent connection, using WebSockets.
- Structured the backend in modules with dependency injection.
- Kept the whole codebase strictly typed.

## Result
The project served 350 requests per second at p95 under 120 ms within the first months after launch.

## What I would do differently
Write the runbook earlier.
