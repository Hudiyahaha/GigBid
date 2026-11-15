---
id: cs-fullstack-p16
persona: fullstack
type: case_study
project: fullstack-p16
title: Logistics tracking API for a logistics client
date: 2026-01-05
client_industry: logistics
skills_listed: [NestJS, Redis, WebSockets]
source: synthetic
---

# Logistics tracking API for a logistics client

**Client:** Lumenbridge Health (synthetic) (logistics) | **Duration:** 4 weeks | **Year:** 2026

## The problem
The client came to me because dispatchers could not see where trucks were in real time.

## What I did
- Structured the backend in modules with dependency injection, using NestJS.
- Cached hot reads in an in-memory key-value store, using Redis.
- Used WebSockets for the core of the solution.
- Designed resource-oriented HTTP endpoints with pagination.
- Generated a type-safe ORM client from a schema file.

## Result
The project served 2500 requests per second at p95 under 120 ms within the first months after launch.

## What I would do differently
Involve end users in week one.
