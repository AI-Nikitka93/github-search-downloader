---
status: accepted
date: 2026-02-23
deciders: Nikita Kizevich
consulted: AI Engineering
informed: Core Engineering
---

# ADR-0008: Superficial AI Relevance Pre-Filtering on Repository Metadata

## Context and Problem Statement

GitHub keyword searches frequently return false positives—repositories that match a keyword in a single tag or minor sentence but are fundamentally off-topic (e.g. awesome-lists, forks with no changes, or homework assignments). Downloading these repositories wastes disk space and bandwidth. Full-text deep analysis of repository source code prior to cloning is too slow and computationally expensive. How can candidate precision be improved prior to clone?

## Decision Drivers

- Reduce disk storage and network bandwidth wasted on off-topic repositories.
- Keep pre-download latency bounded and fast.
- Configurable relevance thresholds and evaluation budgets.

## Considered Options

1. **Superficial Metadata AI Review**: Send repository metadata (name, description, topics, star count) in structured batches to an LLM for numeric relevance scoring (0–100) before downloading.
2. **Keyword Heuristics Only**: Rely exclusively on substring inclusion/exclusion lists.
3. **Deep Code Inspection Pre-Clone**: Download Git archive blobs via REST API for every candidate before deciding.

## Decision Outcome

Chosen option: **Superficial Metadata AI Review**.

### Positive Consequences
- Significantly filters out off-topic repositories prior to Git clone.
- Fast evaluation using small token payloads per candidate.
- Configurable score thresholds and inspection limits.

### Negative Consequences
- Introduces moderate pre-clone latency when AI filtering is enabled.
