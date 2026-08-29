---
status: accepted
date: 2026-03-12
deciders: Nikita Kizevich
consulted: Search & Storage Architecture
informed: Core Engineering
---

# ADR-0015: Incremental Mode Based on Historical Search Metadata

## Context and Problem Statement

Users frequently re-run broad searches against target topics to discover newly created repositories or expand existing archives into the same output directory. Executing full search queries without knowledge of past harvests wastes GitHub API requests, AI filtering cycles, and Git clone bandwidth on repositories that are already stored locally. How can new discovery runs efficiently exclude previously discovered repositories?

## Decision Drivers

- Zero duplicate downloads when appending to an existing output directory.
- Fast candidate de-duplication based on immutable GitHub repository IDs.
- Robust against folder renames or local branch alterations.

## Considered Options

1. **Metadata Scan De-Duplication (`--incremental`)**: Scan previous `metadata/search_*.json` files in the target directory, collect the set of known repository IDs, and prune them from the newly discovered candidate pool before AI filtering and cloning.
2. **Directory Name Matching**: Check if a folder named `owner_repo` already exists on disk.
3. **Always Perform Full Re-Download**: Re-download all candidates regardless of previous runs.

## Decision Outcome

Chosen option: **Metadata Scan De-Duplication (`--incremental`)**.

### Positive Consequences
- Drastically saves API tokens, AI token budgets, and disk I/O during repeated topic monitoring.
- De-duplication is based on unique, immutable GitHub repository IDs rather than fragile directory paths.
- Clean integration with search metadata artifacts.

### Negative Consequences
- Conservative de-duplication skips repositories even if upstream commits were added (users should run `git pull` or full sync for update tracking).
