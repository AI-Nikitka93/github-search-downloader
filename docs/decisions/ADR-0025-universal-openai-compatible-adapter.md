---
status: accepted
date: 2026-04-02
deciders: Nikita Kizevich
consulted: AI & Integration Architecture
informed: Core Engineering
---

# ADR-0025: Universal OpenAI-Compatible AI Provider Adapter

## Context and Problem Statement

Users require the ability to connect various external LLM APIs—including cloud gateways (OpenRouter, Groq, Mistral, OpenAI-compatible Google Gemini endpoints) and local OpenAI-compatible inference servers (LM Studio, LocalAI, vLLM)—beyond the built-in local Ollama integration. Writing vendor-specific API client code for each individual provider is fragile, high-maintenance, and risks exposing API secrets if stored unsafely. How should multi-provider LLM integrations be unified?

## Decision Drivers

- Support standard `/chat/completions` and `/models` protocols across all compliant providers.
- Single unified configuration object (`AiProviderConfig`) for planner and relevance filter routines.
- Zero plaintext API key storage using Windows DPAPI.

## Considered Options

1. **Universal OpenAI-Compatible Adapter with DPAPI Key Binding**: Implement `openai-compatible` provider mode adhering strictly to standard OpenAI REST specifications, store API keys securely in Windows DPAPI, and provide GUI presets for known endpoints.
2. **Vendor-Specific Client SDKs**: Import proprietary SDKs (e.g. `openai`, `google-genai`, `anthropic`) with separate authentication logic for each service.
3. **Ollama Only**: Restrict AI features exclusively to local Ollama.

## Decision Outcome

Chosen option: **Universal OpenAI-Compatible Adapter with DPAPI Key Binding**.

### Positive Consequences
- Immediate compatibility with OpenRouter, Groq, LM Studio, vLLM, and any future OpenAI-compatible inference backend without application updates.
- API keys are encrypted at rest via Windows DPAPI and never saved to config files or shown in plaintext.
- Consistent configuration across CLI flags (`--ai-provider`, `--ai-api-key-env`, `--save-ai-api-key`) and GUI.

### Negative Consequences
- Non-OpenAI-compatible proprietary endpoint formats (such as custom cloud workers) require standard adapter gateways or future dedicated drivers.
