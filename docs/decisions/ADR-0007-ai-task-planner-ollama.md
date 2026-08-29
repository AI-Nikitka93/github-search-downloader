---
status: accepted
date: 2026-02-20
deciders: Nikita Kizevich
consulted: AI Engineering
informed: Core Engineering
---

# ADR-0007: AI Task Planner with Local Ollama Integration

## Context and Problem Statement

Configuring GitHub search queries with advanced qualifiers (`language:`, `stars:`, `topic:`, `in:readme`), date windows, and keywords requires specialized knowledge of GitHub search syntax. Users often have high-level natural language intent (e.g., "Find modern Rust web frameworks with WebAssembly support") but struggle to craft optimal API search strings and output folder structures. How should natural language queries be transformed into structured harvest parameters?

## Decision Drivers

- Privacy-first local AI execution without requiring cloud API keys.
- Automatic query translation from conversational intent to GitHub search syntax.
- Dynamic detection of available local models.

## Considered Options

1. **Local AI Task Planner via Ollama API**: Communicate with local Ollama daemon (`/api/generate` and `/api/tags`), prompting local LLMs to produce structured JSON harvest configurations.
2. **Hardcoded Keyword Mapping Rules**: Use regex and dictionary heuristics to map keywords to qualifiers.
3. **Cloud-Only LLM API Dependency**: Require external cloud API keys (e.g. OpenAI) for all query planning.

## Decision Outcome

Chosen option: **Local AI Task Planner via Ollama API**.

### Positive Consequences
- Zero-cost, zero-data-leakage local natural language processing.
- Dynamic population of installed model drop-downs in the GUI via Ollama `/api/tags`.
- Automatic output folder name slugging and query parameter extraction.

### Negative Consequences
- Dependent on user having a running Ollama service when AI planning mode is activated.
