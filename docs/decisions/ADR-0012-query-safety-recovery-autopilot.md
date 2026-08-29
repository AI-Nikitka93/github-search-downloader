---
status: accepted
date: 2026-03-05
deciders: Nikita Kizevich
consulted: API Integration & Search Architecture
informed: Core Engineering
---

# ADR-0012: Query-Safety Recovery for Autopilot and AI-Generated Searches

## Context and Problem Statement

AI planner models occasionally generate GitHub search queries consisting entirely of qualifiers (e.g. `language:python stars:>50`) without a search term, or containing complex boolean expressions that trigger HTTP `422 Unprocessable Entity (Validation Failed)` responses from GitHub REST Search API. When unhandled, a single 422 error halts the entire harvesting process. How should invalid AI-generated queries be safely sanitized and recovered?

## Decision Drivers

- Resilient autopilot execution without abrupt crashes on malformed AI query strings.
- Automated query normalization to valid GitHub REST syntax.
- Clear diagnostics preserving GitHub API validation error details.

## Considered Options

1. **Automatic Query Normalization and Deterministic Fallback**: Detect qualifier-only query structures, reformat them with safe wildcards/OR-terms, and if a 422 error is returned, generate a deterministic fallback search query and retry automatically while logging error details.
2. **Fail-Fast Error Propagation**: Throw an immediate unhandled exception and terminate the harvest.
3. **Randomized LLM Mutation Retries**: Send the error message back to the LLM and wait for a revised prompt.

## Decision Outcome

Chosen option: **Automatic Query Normalization and Deterministic Fallback**.

### Positive Consequences
- Prevents query generation failures from breaking automated batch and autopilot workflows.
- Retries safely without introducing unbounded LLM retry loops.
- Provides actionable diagnostic output when GitHub API constraints are violated.

### Negative Consequences
- Slightly increases complexity in `github_api.py` query preparation and error handling.
