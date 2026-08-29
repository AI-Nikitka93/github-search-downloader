---
status: accepted
date: 2026-02-05
deciders: Nikita Kizevich
consulted: Architecture Review
informed: Core Engineering
---

# ADR-0003: Shared Python Backend with Dual GUI and CLI Interfaces

## Context and Problem Statement

The application requires both an intuitive, zero-setup desktop GUI for non-technical users and analysts, as well as a flexible, scriptable CLI for automated cron jobs, CI/CD pipelines, and terminal workflows. Implementing separate business logic for each interface would lead to feature drift, double maintenance overhead, and testing divergences. How should the application interface architecture be structured?

## Decision Drivers

- Single source of truth for search orchestration, rate-limiting, and git download routines.
- Frictionless desktop UX via Tkinter without external heavyweight frameworks.
- Fully scriptable CLI with argparse supporting batch scripts and pipeline integration.

## Considered Options

1. **Shared Harvester Core (`src/github_harvester/`) with Dual Entrypoints**: Decouple business logic into a reusable service library invoked by `gui_app.py` and `app.py`.
2. **GUI-Only Application**: Focus exclusively on Tkinter desktop UI, limiting headless automation.
3. **CLI-Only Utility**: Build CLI tool only, requiring non-technical users to manage shell parameters.

## Decision Outcome

Chosen option: **Shared Harvester Core with Dual Entrypoints**.

### Positive Consequences
- Guarantees identical search, filtering, and cloning behavior across GUI and CLI executions.
- Eliminates duplicated code paths and simplifies automated testing (`test_service.py`, `test_cli.py`).
- Enables headless scriptability while maintaining user-friendly desktop accessibility.

### Negative Consequences
- Requires careful abstraction of state notifications, progress callbacks, and cancellation signals between thread-based GUI and console CLI.
