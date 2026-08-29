---
status: accepted
date: 2026-03-18
deciders: Nikita Kizevich
consulted: State & Concurrency Architecture
informed: Core Engineering
---

# ADR-0018: Authoritative Retry Results in Run-State Tracking

## Context and Problem Statement

When clone retries succeed after an initial transient failure, the run-state must accurately reflect the final success. If only the initial failure is recorded in `run_state_*.json`, a subsequent `--resume-state-file` run will erroneously mark a recovered repository as failed or pending and attempt redundant downloads. Additionally, naive retry progress counting can cause UI progress bars to jump backwards or exceed 100%. How should retry transitions be tracked?

## Decision Drivers

- Absolute correctness of final repository status in persistent run-state.
- Monotonic, non-distorted progress reporting in GUI and CLI logs.
- Clean separation between primary candidate queues and retry queues.

## Considered Options

1. **In-Place Authoritative Status Updates with Separate Retry Counters**: Ensure retry completion updates the original repository entry in `run_state.json` directly, while tracking retry attempts on a separate telemetry counter that does not skew total progress denominators.
2. **Append-Only Event Log**: Write a new event line for every attempt and re-aggregate state in memory upon load.
3. **Ignore Retries in State**: Only track the first pass and treat retries as unrecorded background jobs.

## Decision Outcome

Chosen option: **In-Place Authoritative Status Updates with Separate Retry Counters**.

### Positive Consequences
- Guarantees `run_state_*.json` always contains the true, final status of every repository.
- Progress bars remain accurate and monotonic without overshoots.
- Resuming interrupted runs avoids redundant downloads of successfully recovered repositories.

### Negative Consequences
- Requires thread-safe record updates in the run-state manager.
