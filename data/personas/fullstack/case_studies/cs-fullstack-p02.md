---
id: cs-fullstack-p02
persona: fullstack
type: case_study
project: fullstack-p02
title: Logistics tracking API
date: 2021-03-17
client_industry: healthcare
skills_listed: [NestJS, PostgreSQL, Redis, REST API]
source: synthetic
---

# Logistics tracking API

**Client:** Northnest Capital (synthetic) (healthcare) | **Duration:** 10 weeks | **Year:** 2021

## The problem
The client came to me because dispatchers could not see where trucks were in real time.

## What I did
- Used NestJS for the core of the solution.
- Modelled the data in a relational database with migrations and indexes, using PostgreSQL.
- Cached hot reads in an in-memory key-value store, using Redis.
- Designed resource-oriented HTTP endpoints with pagination, using REST API.
- Pushed live updates to the browser over a persistent connection.

## Result
The project served 2500 requests per second at p95 under 120 ms within the first months after launch.

## What I would do differently
Agree on evaluation metrics before building.
