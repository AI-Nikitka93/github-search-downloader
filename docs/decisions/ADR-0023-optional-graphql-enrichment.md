---
status: accepted
date: 2026-03-28
deciders: Nikita Kizevich
consulted: GraphQL & Data Architecture
informed: Core Engineering
---

# ADR-0023: Optional GraphQL Metadata Enrichment on Final Shortlist

## Context and Problem Statement

GitHub REST Search API (`/search/repositories`) provides foundational discovery attributes, but lacks key analytics fields such as default branch HEAD commit OIDs, latest release tag and publication timestamps, repository homepage URLs, mirror/empty flags, and normalized topic arrays. Conversely, querying GraphQL for every intermediate discovery candidate would rapidly exhaust GraphQL node points and slow down initial discovery. How should extended repository metadata be collected efficiently?

## Decision Drivers

- Enrich final metadata exports with high-fidelity repository properties.
- Strictly protect GraphQL API node points and rate limits.
- Graceful degradation for unauthenticated runs or network timeouts.

## Considered Options

1. **Post-Filter Shortlist GraphQL Enrichment (`--graphql-enrich`)**: Retain REST Search for initial wide-window discovery; execute batched GraphQL queries (1–50 repositories per batch) exclusively on the post-filtered, deduplicated final candidate shortlist when a GitHub token is configured.
2. **GraphQL-First Discovery Pipeline**: Migrate all search queries entirely to GitHub GraphQL API.
3. **Individual REST Calls per Repository**: Perform separate REST API requests (`/repos/{owner}/{repo}`, `/releases/latest`, `/commits`) for each repository.

## Decision Outcome

Chosen option: **Post-Filter Shortlist GraphQL Enrichment (`--graphql-enrich`)**.

### Positive Consequences
- Populates SQLite and JSON metadata with detailed release, commit, and topic data for final download targets.
- Uses minimal GraphQL budget by enriching only surviving candidates.
- Unauthenticated or non-token runs continue uninterrupted, setting `graphql_enriched=false`.

### Negative Consequences
- Requires a valid GitHub Personal Access Token or App token for GraphQL access.
