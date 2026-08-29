---
status: accepted
date: 2026-03-24
deciders: Nikita Kizevich
consulted: AI & Runtime Architecture
informed: Core Engineering
---

# ADR-0021: Explicit Profile-Driven Ollama Runtime Options

## Context and Problem Statement

When generating queries or scoring repository relevance via Ollama (`/api/generate`), inference quality and speed depend heavily on low-level engine parameters—including context window size (`num_ctx`), maximum predicted tokens (`num_predict`), and temperature. Specifying only a model name and endpoint resulted in unpredictable generation limits, truncated JSON responses, and inconsistent behavior across machines. How should AI runtime execution parameters be managed?

## Decision Drivers

- Reproducible AI inference across GUI, CLI, and configuration files.
- Prevention of truncated JSON outputs via explicit token prediction limits.
- Pre-configured, task-tailored runtime profiles for fast local, quality local, and cloud-scale execution.

## Considered Options

1. **Explicit `AiProviderConfig` Runtime Options with Preset GUI Profiles**: Extend `AiProviderConfig` with `temperature`, `num_ctx`, and `num_predict`, expose curated runtime presets in GUI, support CLI overrides, and dynamically validate active models against `/api/tags`.
2. **Hardcoded Engine Defaults**: Rely exclusively on server-side Ollama default parameters without passing explicit options.
3. **Free-Form Raw JSON Parameter String**: Require users to write raw JSON option dictionaries in the interface.

## Decision Outcome

Chosen option: **Explicit `AiProviderConfig` Runtime Options with Preset GUI Profiles**.

### Positive Consequences
- Guarantees predictable JSON outputs from local LLMs by guaranteeing sufficient prediction windows.
- Users can switch between fast (low latency) and quality (higher context) profiles with a single click.
- Full parity between GUI settings and CLI `--ai-temperature`, `--ai-num-ctx`, `--ai-num-predict` arguments.

### Negative Consequences
- Slightly expands configuration schema and parameter serialization surface.
