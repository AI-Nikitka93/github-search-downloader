---
status: accepted
date: 2026-03-08
deciders: Nikita Kizevich
consulted: CLI & Config Architecture
informed: Core Engineering
---

# ADR-0013: Unified JSON Configuration Path for CLI and GUI Interoperability

## Context and Problem Statement

Users frequently alternate between exploring queries interactively via the Tkinter GUI and executing automated headless batch harvests via the CLI. If configuration files (`gui_settings.json`) use a schema incompatible with CLI parameters, settings cannot be shared, leading to configuration drift, repeated manual parameter entry, and script fragility. How should configuration files be unified across interfaces?

## Decision Drivers

- Single shared configuration schema for GUI settings and CLI `--config-file` flags.
- Deterministic parameter precedence (explicit CLI flags override config file values).
- Explicit override flags (e.g. `--no-ai-filter`) for disabling config-enabled features in scripts.

## Considered Options

1. **Unified Configuration Parser with Strict Hierarchy**: Implement `--config-file` in `app.py` accepting the exact JSON format produced by `gui_app.py`, applying a deterministic precedence order (CLI flag > Config file > Default value).
2. **Distinct Schemas for GUI and CLI**: Maintain separate configuration files for GUI (`gui_settings.json`) and CLI (`cli_config.yaml`).
3. **Environment Variables Exclusively**: Disallow JSON configuration files in CLI and require shell environment variables.

## Decision Outcome

Chosen option: **Unified Configuration Parser with Strict Hierarchy**.

### Positive Consequences
- Users can configure search parameters visually in the GUI and reuse the exact config file in automated CLI pipelines.
- Explicit CLI flags allow runtime overrides without mutating configuration files on disk.
- Simplifies configuration migration and schema validation.

### Negative Consequences
- Slightly expands `app.py` argparse definitions and type coercion logic.
