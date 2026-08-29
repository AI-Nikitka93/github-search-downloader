---
status: accepted
date: 2026-03-03
deciders: Nikita Kizevich
consulted: UX & Product Architecture
informed: Core Engineering
---

# ADR-0011: Preview Shortlist with Manual Include/Exclude Before Clone

## Context and Problem Statement

Direct end-to-end `search -> clone` execution does not allow human-in-the-loop verification before downloading gigabytes of source code. Users often want to inspect candidate repositories, review AI recommendation tags and descriptions, and selectively check or uncheck individual repositories prior to initiating Git cloning. How should the user interface support manual verification checkpoints?

## Decision Drivers

- Human-in-the-loop control over final download sets.
- Decoupling discovery dry-run from physical Git cloning.
- Responsive UI presentation of candidate lists with bulk select/deselect controls.

## Considered Options

1. **Two-Stage "Preview & Select" Workflow**: Support dry-run discovery in GUI, populate an interactive shortlist table with metadata and selection checkboxes, and expose `run_download_for_repositories()` for targeted subset cloning.
2. **Direct Unchecked Clone Execution Only**: Force users to clone everything discovered and delete unwanted folders manually.
3. **CLI Interactive Prompts**: Prompt `(y/n)` in terminal for every discovered repository.

## Decision Outcome

Chosen option: **Two-Stage "Preview & Select" Workflow**.

### Positive Consequences
- Gives users full precision control over which repositories consume disk space.
- Provides immediate visual feedback on AI relevance labels and descriptions.
- Clean architectural separation between discovery phase and download execution phase.

### Negative Consequences
- Introduces additional state management and callback logic in `gui_app.py`.
