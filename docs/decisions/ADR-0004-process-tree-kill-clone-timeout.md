---
status: accepted
date: 2026-02-12
deciders: Nikita Kizevich
consulted: Systems & Platform Architecture
informed: Core Engineering
---

# ADR-0004: Process-Tree Kill for Git Clone Timeout Enforcement on Windows

## Context and Problem Statement

When cloning large or unresponsive repositories over unstable connections, Git worker processes (e.g., `git-remote-https.exe`, `ssh.exe`) can hang indefinitely or ignore soft timeout signals in Python `subprocess`. On Windows, standard `process.kill()` or `process.terminate()` calls terminate only the root parent process, leaving orphaned child processes holding file locks and network sockets. How should clone operations be strictly bounded in execution time?

## Decision Drivers

- Bounded execution time per repository without process hangs.
- Complete cleanup of orphan child processes on Windows.
- Clean release of Windows NTFS file handles to prevent lock contention.

## Considered Options

1. **Windows Process-Tree Force Kill (`taskkill /T /F /PID <pid>`)**: Spawn monitoring threads that enforce hard timeout limits and forcibly terminate the entire process hierarchy.
2. **Standard Python Soft Timeout (`subprocess.run(timeout=...)`)**: Rely only on standard library timeout exceptions without recursive child cleanup.
3. **External Job Object Subsystem**: Wrap subprocess creation in native Windows Win32 Job Objects.

## Decision Outcome

Chosen option: **Windows Process-Tree Force Kill (`taskkill /T /F /PID <pid>`)**.

### Positive Consequences
- Guarantees complete termination of all nested Git subprocesses on timeout.
- Unlocks directory handles immediately, enabling safe cleanup of partially cloned directories.
- Prevents silent application freezes during long unattended bulk downloads.

### Negative Consequences
- Windows-specific command invocation (`taskkill.exe`), requiring OS checks before execution.
