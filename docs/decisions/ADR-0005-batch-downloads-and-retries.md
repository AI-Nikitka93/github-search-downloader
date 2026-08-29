---
status: accepted
date: 2026-02-14
deciders: Nikita Kizevich
consulted: Reliability Engineering
informed: Core Engineering
---

# ADR-0005: Batch Downloads and Transient Clone Failure Retries

## Context and Problem Statement

Bulk harvesting operations involve downloading hundreds or thousands of Git repositories in a single run. Transient network drops, temporary rate-limiting, or server-side throttling by GitHub can cause isolated clone failures. In monolithic execution, a few failing clones can stall progress or require restarting the entire operation. How should high-volume downloads be scheduled and made resilient?

## Decision Drivers

- Resilient execution over unreliable network connections.
- Controlled memory footprint and bounded concurrent thread exhaustion.
- Automatic recovery for transient Git network glitches.

## Considered Options

1. **Configurable Batching with Delayed Retry Queue**: Partition the repository queue into fixed-size batches (e.g. 50 repos) and execute dedicated retry passes with exponential delay for transient failures.
2. **Monolithic Single-Pass Execution**: Clone all repositories sequentially or concurrently without batch boundaries or retry mechanisms.
3. **Infinite Retry Loop**: Continuously retry failed repositories until success.

## Decision Outcome

Chosen option: **Configurable Batching with Delayed Retry Queue**.

### Positive Consequences
- Significantly increases final harvest completion rate without requiring manual intervention.
- Isolates failures to discrete batch checkpoints, facilitating periodic metadata persistence.
- Provides smooth progress reporting and predictable memory usage.

### Negative Consequences
- Slightly increases orchestrator scheduling complexity to manage retry passes and status transitions.
