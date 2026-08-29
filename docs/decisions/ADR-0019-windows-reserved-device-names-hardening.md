---
status: accepted
date: 2026-03-20
deciders: Nikita Kizevich
consulted: Windows Systems Architecture
informed: Core Engineering
---

# ADR-0019: Windows Reserved Device Names Path Hardening

## Context and Problem Statement

The Windows Win32 filesystem subsystem reserves legacy DOS device names—including `CON`, `PRN`, `AUX`, `NUL`, `COM1` through `COM9`, and `LPT1` through `LPT9`—regardless of file extensions (e.g. `aux.git`, `con.json`). Attempting to create folders or files matching these reserved tokens on Windows results in `WinError 87` or silent filesystem corruption. While these are valid GitHub repository names, they break local disk operations on Windows. How should destination repository paths be sanitized?

## Decision Drivers

- Flawless directory creation on Windows NTFS filesystems.
- Deterministic, bi-directional folder naming traceable to the original GitHub repository.
- Prevention of path traversal attacks and reserved character violations (`:`, `*`, `?`, `"`, `<`, `>`, `|`).

## Considered Options

1. **Prefix Reserved Segment Sanitization (`reserved_*`)**: Inspect each path segment against the Windows reserved name set; if a match is found (case-insensitively), prefix the segment with `reserved_` prior to directory creation.
2. **Hash-Only Directory Naming**: Name every local directory with its SHA-256 hash or numeric GitHub repository ID.
3. **Fail and Skip**: Flag any repository with a reserved device name as un-downloadable on Windows.

## Decision Outcome

Chosen option: **Prefix Reserved Segment Sanitization (`reserved_*`)**.

### Positive Consequences
- Prevents fatal OS filesystem exceptions when cloning repositories named `aux`, `nul`, or `com1`.
- Folders remain human-readable and readily identifiable by analysts.
- Fully compatible with downstream tooling and IDE navigation on Windows.

### Negative Consequences
- Slightly alters destination folder basename on Windows compared to the raw repository name.
