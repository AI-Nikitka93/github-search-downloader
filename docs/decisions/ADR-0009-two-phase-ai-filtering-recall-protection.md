---
status: accepted
date: 2026-02-26
deciders: Nikita Kizevich
consulted: AI & Quality Engineering
informed: Core Engineering
---

# ADR-0009: Two-Phase Fast AI Filtering with Recall Protection

## Context and Problem Statement

Overly strict AI filtering can cause severe over-pruning (e.g. discarding 298 out of 300 candidates due to strict prompting or minor LLM hallucinations), leading to empty or near-empty download sets. Conversely, disabling AI filters floods the download queue with low-quality projects. How can the harvester achieve high precision without catastrophic recall loss?

## Decision Drivers

- Prevent "found 300 -> kept 1-2" catastrophic over-pruning failures.
- Protect search recall via mid-ranked candidate exploration sampling.
- Expose clear user profiles for Precision, Balance, and Recall.

## Considered Options

1. **Two-Phase Pipeline with Heuristic Floor**: Phase 1 gathers a broad recall pool (including random exploration from mid-tier rankings); Phase 2 performs bounded AI scoring with strict fallback guarantees ensuring a minimum candidate floor if the model is overly strict.
2. **Unconstrained Strict AI Filter**: Discard all candidates failing the strict score threshold without minimum floors.
3. **Pure Heuristic Filtering**: Avoid AI models entirely and use keyword matching.

## Decision Outcome

Chosen option: **Two-Phase Pipeline with Heuristic Floor**.

### Positive Consequences
- Preserves high precision while safeguarding against total harvest starvation.
- One-click GUI profiles (`Точность`, `Баланс`, `Полнота`) give non-technical users transparent trade-off control.
- Heuristic fallback ensures graceful degradation if LLM endpoints encounter network timeouts.

### Negative Consequences
- Increases internal ranking state machine complexity.
