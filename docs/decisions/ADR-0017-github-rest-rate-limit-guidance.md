---
status: accepted
date: 2026-03-16
deciders: Nikita Kizevich
consulted: API Architecture & Compliance
informed: Core Engineering
---

# ADR-0017: GitHub REST Rate-Limit Guidance Compliance

## Context and Problem Statement

GitHub's REST API enforces both primary hourly rate limits (`X-RateLimit-*`) and secondary concurrency/abuse rate limits. Historical practices that treated any future `X-RateLimit-Reset` timestamp as the sleep duration caused clients to sleep for an entire hour when encountering secondary rate limits, even when primary `X-RateLimit-Remaining` was non-zero. How should the API client parse rate-limit headers according to official GitHub guidance?

## Decision Drivers

- Full compliance with GitHub REST API versioning and rate-limiting guidance (`2026-03-10`).
- Prevent excessive false 1-hour sleeps on secondary rate limits.
- Graceful exponential backoff with jitter on transient network throttling.

## Considered Options

1. **Targeted Header Evaluation with Exponential Fallback**: Send the `X-GitHub-Api-Version: 2026-03-10` header; prioritize `Retry-After` header when provided; evaluate `X-RateLimit-Reset` only when `X-RateLimit-Remaining == 0`; otherwise apply exponential backoff starting at 60s for secondary rate limits.
2. **Naive Timestamp Reset Sleep**: Always sleep until `X-RateLimit-Reset` on any HTTP 403/429 response.
3. **Fixed Interval Throttling**: Insert a static 1-second delay between every single API request regardless of response headers.

## Decision Outcome

Chosen option: **Targeted Header Evaluation with Exponential Fallback**.

### Positive Consequences
- Drastically reduces false idle wait times during mass harvesting runs.
- Aligns API client behavior with modern GitHub API standards.
- Ensures reliable automatic recovery from transient secondary rate limit conditions.

### Negative Consequences
- Requires comprehensive header parsing and state tracking in `github_api.py`.
