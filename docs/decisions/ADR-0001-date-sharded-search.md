---
status: accepted
date: 2026-02-11
deciders: Nikita Kizevich
consulted: Architecture Review
informed: Core Engineering
---

# ADR-0001: Date-Range Sharding for GitHub Search API

## Context and Problem Statement

The GitHub REST Search API (`/search/repositories`) enforces a hard limit of 1,000 results per query. For broad OSINT, dataset harvesting, or research queries (e.g., "machine learning", "osint tools"), matching repositories often number in the tens of thousands. How can the application harvest comprehensive datasets beyond the 1,000-result cap while respecting official GitHub API rate limits?

## Decision Drivers

- Need to harvest >1,000 repositories without data loss.
- Compliance with official GitHub API pagination and rate limits.
- Resilient recovery in case of secondary rate limits or network failures.

## Considered Options

1. **Date-Range Sharding (Recursive Bisection)**: Automatically partition search intervals (`created:YYYY-MM-DD..YYYY-MM-DD`) into smaller sub-ranges whenever count exceeds 1,000.
2. **Fixed Pagination Only**: Rely only on standard `page=1..10` and truncate at 1,000 results.
3. **GraphQL Search Migration**: Use GitHub GraphQL search queries.

## Decision Outcome

Chosen option: **Date-Range Sharding (Recursive Bisection)**.

### Positive Consequences
- Guarantees complete repository discovery across wide historical windows.
- Automatically narrows date windows down to individual days for high-density query periods.
- Compatible with unauthenticated and authenticated REST calls.

### Negative Consequences
- Increases the number of metadata API requests, placing higher demand on rate-limit budget management.
