---
status: accepted
date: 2026-03-15
deciders: Nikita Kizevich
consulted: Security Architecture
informed: Core Engineering
---

# ADR-0002: Windows DPAPI for Secret Storage

## Context and Problem Statement

GitHub Search Downloader requires sensitive credentials (GitHub personal access tokens and cloud AI API keys) to enable higher API limits, GraphQL enrichment, and AI-assisted filtering. Storing credentials in plaintext within configuration files (`gui_settings.json`), environment variables, or CLI arguments creates significant security risks (git leak, accidental sharing, process snooping). How should credentials be secured on Windows?

## Decision Drivers

- Zero plaintext credentials on disk or in repository commits.
- Native Windows user-session isolation.
- Seamless developer UX without requiring external password managers.

## Considered Options

1. **Windows Data Protection API (DPAPI)**: Encrypt credentials via `CryptProtectData` bound to the active Windows user context and store blobs in `%LOCALAPPDATA%\GithubSearchDownloader\secrets`.
2. **Plaintext JSON Configuration (`gui_settings.json`)**: Store token strings directly in application config files.
3. **OS Keyring Libraries (Keyring package)**: Use generic Python `keyring` wrapper with third-party backend dependencies.

## Decision Outcome

Chosen option: **Windows Data Protection API (DPAPI)**.

### Positive Consequences
- Secrets are cryptographically bound to the Windows user logon context via OS-native DPAPI.
- No plaintext keys are ever saved to `gui_settings.json` or committed to version control.
- Application logs automatically mask token prefixes and authorization headers.

### Negative Consequences
- Secrets do not roam automatically across different physical Windows machines or user profiles.
