---
status: accepted
date: 2026-03-26
deciders: Nikita Kizevich
consulted: Git & Systems Architecture
informed: Core Engineering
---

# ADR-0022: Configurable and Logged Git Clone Strategies

## Context and Problem Statement

Mass repository downloads represent major network bandwidth and disk storage bottlenecks. By default, code analysis and AI dataset harvesting require only recent source snapshots rather than decades of historical git commits, large binary blobs, or unused release tags. However, certain research and archival use cases require complete commit histories, all remote branches, and full git tags. Hardcoding git clone arguments prevented tailored performance tuning. How should Git cloning strategies be structured?

## Decision Drivers

- Minimal disk consumption and maximum download speed for default harvesting.
- Full fidelity configuration support for archival workflows.
- Transparent telemetry logging of active clone strategy per repository run.

## Considered Options

1. **Configurable `CloneOptions` with Fast Defaults and Strategy Logging**: Expose `--clone-depth` (default `1`), `--clone-filter` (default `blob:none`), `--clone-single-branch` (default `true`), and `--clone-tags` (default `false`), and log the exact active strategy in application telemetry.
2. **Hardcoded Deep Clones (`git clone <url>`)**: Always perform full repository clones with complete history.
3. **Hardcoded Shallow Clones Only**: Enforce shallow clones without allowing users to configure depth or disable blob filters.

## Decision Outcome

Chosen option: **Configurable `CloneOptions` with Fast Defaults and Strategy Logging**.

### Positive Consequences
- Default harvests achieve 5x–10x faster download speeds and massive disk space savings via shallow partial cloning.
- Advanced archival users can specify depth `0`, disable partial filters, and fetch all branches/tags without modifying code.
- Operational logs provide full traceability of Git transfer parameters.

### Negative Consequences
- Users must understand Git options when creating specialized deep archival configurations.
