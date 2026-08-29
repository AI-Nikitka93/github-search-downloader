---
status: accepted
date: 2026-03-30
deciders: Nikita Kizevich
consulted: Ranking & Search Architecture
informed: Core Engineering
---

# ADR-0024: Bounded In-Memory Deep Relevance Scoring via README and Git Tree

## Context and Problem Statement

Top-level metadata (repository name, short description, tags, stars) often provides insufficient signal to distinguish authentic production implementations from toy prototypes, empty starter repos, or documentation forks. However, cloning every candidate to disk or passing hundreds of full codebases to AI models for evaluation is prohibitively slow, consumes massive bandwidth, and raises data privacy concerns. How can the harvester perform high-accuracy relevance scoring prior to physical cloning?

## Decision Drivers

- Superior relevance accuracy based on actual documentation and repository file tree layout.
- Zero disk clutter: analyze README and tree structures strictly in memory without local file persistence.
- Bounded REST API calls with opt-in control (`--deep-relevance`).

## Considered Options

1. **Bounded In-Memory README and Tree Scoring (`--deep-relevance`)**: Fetch README raw text and Git tree blob manifests via GitHub REST API only for a bounded candidate shortlist (`--deep-relevance-max-repos`), score semantic and structural alignment in memory, record numeric scores in metadata, and never persist full text to disk.
2. **Pre-Clone Full Repository Download**: Download full zip archives for all candidates and run local file analysis tools.
3. **LLM Full-Text Ingestion**: Feed the entire repository tree to an LLM context window for every search hit.

## Decision Outcome

Chosen option: **Bounded In-Memory README and Tree Scoring (`--deep-relevance`)**.

### Positive Consequences
- Significantly enhances search ranking for curated dry-runs and automated pipelines.
- Avoids writing transient file contents to disk, preserving privacy and I/O bandwidth.
- Graceful error isolation: if a specific repository README or tree fetch fails, the repository is retained with an error annotation rather than dropped.

### Negative Consequences
- Increases API request volume on candidate shortlists, requiring a GitHub token for optimal performance.
