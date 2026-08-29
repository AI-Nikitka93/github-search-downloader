---
status: accepted
date: 2026-03-10
deciders: Nikita Kizevich
consulted: Systems & Storage Architecture
informed: Core Engineering
---

# ADR-0014: Resumable Run-State Persistence for Git Clone Sessions

## Context and Problem Statement

Mass cloning operations can span thousands of repositories and run for several hours. Unforeseen interruptions—such as network disconnects, operating system reboots, user cancellations, or disk exhaustion—leave the download state ambiguous. A metadata file lists which repositories were scheduled for download, but does not track which individual clone operations completed successfully prior to the interruption. How should clone session progress be tracked and resumed?

## Decision Drivers

- Transparent, crash-resilient session state persistence.
- Fast skip of already completed or explicitly skipped repositories on restart.
- Decoupled state management independent of GUI process lifecycle.

## Considered Options

1. **Transactional Run-State File (`run_state_*.json`)**: Maintain a discrete JSON state file in the output `metadata/` directory updated after every repository clone or retry operation, and support `--resume-state-file` to resume interrupted sessions.
2. **Filesystem Existence Checks**: Inspect if target repository directories exist on disk before cloning.
3. **Database-Driven Daemon**: Require a persistent background database service to track download status.

## Decision Outcome

Chosen option: **Transactional Run-State File (`run_state_*.json`)**.

### Positive Consequences
- Allows interrupted harvests to resume seamlessly without re-downloading existing repositories or losing status history.
- Distinguishes between completed (`cloned`), skipped (`skipped`), and failed (`failed`) repositories.
- Fully decoupled from GUI state and verifiable via automated tests (`test_run_state.py`).

### Negative Consequences
- Creates one additional JSON metadata artifact per download session.
