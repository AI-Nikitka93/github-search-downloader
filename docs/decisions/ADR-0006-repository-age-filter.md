---
status: accepted
date: 2026-02-18
deciders: Nikita Kizevich
consulted: Product & Search Architecture
informed: Core Engineering
---

# ADR-0006: Repository Age Filter for Targeted Temporal Relevance

## Context and Problem Statement

When querying broad topics on GitHub, queries often return obsolete, abandoned, or unmaintained repositories created many years ago. While explicit date range qualifiers (`created:YYYY-MM-DD..YYYY-MM-DD`) allow precision tuning, requiring users to manually compute calendar boundaries for every run adds friction. How can users intuitively constrain repository recency?

## Decision Drivers

- Intuitive user experience for filtering out legacy codebases.
- Seamless compatibility with both explicit date ranges and dynamic sharding.
- Fast client-side and server-side filtering.

## Considered Options

1. **`max_age_years` Recency Filter**: Provide a dynamic age threshold (in years) computed at runtime relative to the current timestamp and applied to repository `created_at` metadata.
2. **Mandatory Explicit Date Range Inputs Only**: Require users to specify absolute `created_after` and `created_before` dates for all runs.
3. **Post-Download Disk Filtering**: Clone everything and prune older repositories from disk afterwards.

## Decision Outcome

Chosen option: **`max_age_years` Recency Filter**.

### Positive Consequences
- Users can quickly restrict searches to modern repositories (e.g. `<= 2` years) with a single slider or CLI parameter.
- Prevents wasting bandwidth, API quota, and disk space on legacy projects.
- Works cohesively with explicit date range bounds when specified.

### Negative Consequences
- May exclude historically important foundational repositories unless explicitly disabled or expanded.
