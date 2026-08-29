---
status: accepted
date: 2026-03-01
deciders: Nikita Kizevich
consulted: Systems & Search Architecture
informed: Core Engineering
---

# ADR-0010: Deterministic Ranking and Safe Degraded Mode

## Context and Problem Statement

Early truncation (`max_repositories` cutoffs within individual date shards) and inconsistent ordering caused result sets to vary wildly across runs. Furthermore, when local AI models or external networks failed mid-harvest, whole batches were dropped or corrupted. How can search ranking achieve strict reproducibility and fault tolerance under partial system outages?

## Decision Drivers

- Absolute repeatability of search results for identical queries and inputs.
- Safe degraded operation when AI models become unavailable mid-execution.
- Atomic filesystem persistence for critical metadata artifacts.

## Considered Options

1. **Global Deterministic Ranking with Composite Scoring & Atomic Persistence**: Aggregate candidates globally, apply composite scoring (text match + recency decay + log-star popularity), sort deterministically before trimming, fallback to heuristic degradation on AI error, and write metadata atomically via temporary files.
2. **Early Range Cutoff**: Truncate immediately as soon as per-shard counts hit `max_repositories`.
3. **Hard Fail on AI Error**: Terminate the entire harvest if an AI scoring request fails.

## Decision Outcome

Chosen option: **Global Deterministic Ranking with Composite Scoring & Atomic Persistence**.

### Positive Consequences
- Guarantees predictable, repeatable repository ranking across runs.
- Prevents partial metadata corruption via atomic rename semantics.
- Seamlessly falls back to heuristic ranking if LLMs experience outages.

### Negative Consequences
- Slightly higher memory retention during discovery phase before final truncation.
