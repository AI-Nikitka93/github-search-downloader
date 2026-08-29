# Architecture Decision Records (ADR Master Index)

This document serves as the master catalog and index for all Architectural Decision Records (ADRs) governing **GitHub Search Downloader**. Each individual decision is documented in standard [MADR 4.0.0](https://adr.github.io/madr/) format under [`docs/decisions/`](./decisions/).

## Architecture Decision Index

| ADR | Title | Status | Date | Area |
| :--- | :--- | :--- | :--- | :--- |
| [ADR-0001](decisions/ADR-0001-date-sharded-search.md) | Date-Range Sharding for GitHub Search API | `accepted` | 2026-02-11 | Search & Harvester |
| [ADR-0002](decisions/ADR-0002-windows-dpapi-secret-storage.md) | Windows DPAPI for Secret Storage | `accepted` | 2026-03-15 | Security & Cryptography |
| [ADR-0003](decisions/ADR-0003-shared-backend-gui-cli.md) | Shared Python Backend with Dual GUI and CLI Interfaces | `accepted` | 2026-02-05 | Core Architecture |
| [ADR-0004](decisions/ADR-0004-process-tree-kill-clone-timeout.md) | Process-Tree Kill for Git Clone Timeout Enforcement | `accepted` | 2026-02-12 | Git Engine & OS |
| [ADR-0005](decisions/ADR-0005-batch-downloads-and-retries.md) | Batch Downloads and Transient Clone Failure Retries | `accepted` | 2026-02-14 | Downloader Reliability |
| [ADR-0006](decisions/ADR-0006-repository-age-filter.md) | Repository Age Filter for Targeted Temporal Relevance | `accepted` | 2026-02-18 | Search & Filtering |
| [ADR-0007](decisions/ADR-0007-ai-task-planner-ollama.md) | AI Task Planner with Local Ollama Integration | `accepted` | 2026-02-20 | AI & Automation |
| [ADR-0008](decisions/ADR-0008-superficial-ai-relevance-filter.md) | Superficial AI Relevance Pre-Filtering on Metadata | `accepted` | 2026-02-23 | AI & Relevance |
| [ADR-0009](decisions/ADR-0009-two-phase-ai-filtering-recall-protection.md) | Two-Phase Fast AI Filtering with Recall Protection | `accepted` | 2026-02-26 | AI & Precision/Recall |
| [ADR-0010](decisions/ADR-0010-deterministic-ranking-safe-degraded-mode.md) | Deterministic Ranking and Safe Degraded Mode | `accepted` | 2026-03-01 | Ranking & Fault Tolerance |
| [ADR-0011](decisions/ADR-0011-preview-shortlist-manual-selection.md) | Preview Shortlist with Manual Include/Exclude Before Clone | `accepted` | 2026-03-03 | UX & Workflows |
| [ADR-0012](decisions/ADR-0012-query-safety-recovery-autopilot.md) | Query-Safety Recovery for Autopilot Searches | `accepted` | 2026-03-05 | API Resilience |
| [ADR-0013](decisions/ADR-0013-unified-json-config-cli-gui.md) | Unified JSON Configuration Path for CLI and GUI | `accepted` | 2026-03-08 | CLI & Configuration |
| [ADR-0014](decisions/ADR-0014-resumable-clone-run-state.md) | Resumable Run-State Persistence for Clone Sessions | `accepted` | 2026-03-10 | State & Recovery |
| [ADR-0015](decisions/ADR-0015-incremental-mode-previous-metadata.md) | Incremental Mode Based on Historical Search Metadata | `accepted` | 2026-03-12 | Storage & De-duplication |
| [ADR-0016](decisions/ADR-0016-sqlite-export-analytics-surface.md) | SQLite Export as an Embedded Analytics Surface | `accepted` | 2026-03-14 | Analytics & Database |
| [ADR-0017](decisions/ADR-0017-github-rest-rate-limit-guidance.md) | GitHub REST Rate-Limit Guidance Compliance | `accepted` | 2026-03-16 | API & Rate Limiting |
| [ADR-0018](decisions/ADR-0018-authoritative-retry-results-run-state.md) | Authoritative Retry Results in Run-State Tracking | `accepted` | 2026-03-18 | State Consistency |
| [ADR-0019](decisions/ADR-0019-windows-reserved-device-names-hardening.md) | Windows Reserved Device Names Path Hardening | `accepted` | 2026-03-20 | Windows Filesystem |
| [ADR-0020](decisions/ADR-0020-verifiable-windows-release-package.md) | Verifiable Windows Release Package Workflow | `accepted` | 2026-03-22 | Release & Packaging |
| [ADR-0021](decisions/ADR-0021-ollama-runtime-profiles.md) | Explicit Profile-Driven Ollama Runtime Options | `accepted` | 2026-03-24 | AI Configuration |
| [ADR-0022](decisions/ADR-0022-configurable-clone-strategy.md) | Configurable and Logged Git Clone Strategies | `accepted` | 2026-03-26 | Git Engine Performance |
| [ADR-0023](decisions/ADR-0023-optional-graphql-enrichment.md) | Optional GraphQL Metadata Enrichment on Final Shortlist | `accepted` | 2026-03-28 | GraphQL API |
| [ADR-0024](decisions/ADR-0024-bounded-deep-relevance-scoring.md) | Bounded In-Memory Deep Relevance Scoring via README/Tree | `accepted` | 2026-03-30 | Deep Search Quality |
| [ADR-0025](decisions/ADR-0025-universal-openai-compatible-adapter.md) | Universal OpenAI-Compatible AI Provider Adapter | `accepted` | 2026-04-02 | AI Gateway Integration |

---

## Decision Summaries

### [ADR-0001: Date-Range Sharding for GitHub Search API](decisions/ADR-0001-date-sharded-search.md)
Overcomes the hard 1,000-result cap per search query by recursively bisecting search intervals (`created:start..end`) until each shard contains $\le 1000$ repositories.

### [ADR-0002: Windows DPAPI for Secret Storage](decisions/ADR-0002-windows-dpapi-secret-storage.md)
Eliminates plaintext tokens on disk and in git commits by encrypting personal access tokens and cloud AI keys using Windows Data Protection API (`CryptProtectData`) stored under `%LOCALAPPDATA%\GithubSearchDownloader\secrets`.

### [ADR-0003: Shared Python Backend with Dual GUI and CLI Interfaces](decisions/ADR-0003-shared-backend-gui-cli.md)
Decouples business logic into a reusable harvester service library invoked by both Tkinter desktop GUI (`gui_app.py`) and CLI script (`app.py`), preventing feature and behavioral drift.

### [ADR-0004: Process-Tree Kill for Git Clone Timeout Enforcement](decisions/ADR-0004-process-tree-kill-clone-timeout.md)
Enforces bounded clone timeouts on Windows by killing the entire Git process tree using `taskkill /T /F`, releasing NTFS file locks and preventing orphaned subprocess hangs.

### [ADR-0005: Batch Downloads and Transient Clone Failure Retries](decisions/ADR-0005-batch-downloads-and-retries.md)
Processes repository downloads in configurable batches with delayed retry queues, ensuring resilience against transient network failures without requiring full harvest restarts.

### [ADR-0006: Repository Age Filter for Targeted Temporal Relevance](decisions/ADR-0006-repository-age-filter.md)
Introduces a dynamic `max_age_years` filter calculated at runtime against repository creation dates, allowing users to easily exclude legacy or unmaintained codebases.

### [ADR-0007: AI Task Planner with Local Ollama Integration](decisions/ADR-0007-ai-task-planner-ollama.md)
Translates conversational natural language user prompts into structured GitHub search qualifier parameters and folder naming schemes using local Ollama models (`/api/generate`, `/api/tags`).

### [ADR-0008: Superficial AI Relevance Pre-Filtering on Metadata](decisions/ADR-0008-superficial-ai-relevance-filter.md)
Executes fast pre-clone relevance scoring over repository metadata (names, descriptions, topics, star counts) via local LLMs to reject false positives before initiating clone operations.

### [ADR-0009: Two-Phase Fast AI Filtering with Recall Protection](decisions/ADR-0009-two-phase-ai-filtering-recall-protection.md)
Guarantees balanced discovery using a two-phase architecture: Phase 1 gathers broad candidates with exploration sampling; Phase 2 performs bounded AI scoring with heuristic floor guarantees to prevent catastrophic over-pruning.

### [ADR-0010: Deterministic Ranking and Safe Degraded Mode](decisions/ADR-0010-deterministic-ranking-safe-degraded-mode.md)
Enforces global deterministic ranking across shards, composite relevance scoring, atomic metadata writes, and automatic graceful degradation to heuristics if LLMs experience outages.

### [ADR-0011: Preview Shortlist with Manual Include/Exclude Before Clone](decisions/ADR-0011-preview-shortlist-manual-selection.md)
Provides a desktop GUI preview mode enabling users to inspect candidate metadata, view AI recommendations, and manually include/exclude repositories before downloading gigabytes of source code.

### [ADR-0012: Query-Safety Recovery for Autopilot Searches](decisions/ADR-0012-query-safety-recovery-autopilot.md)
Sanitizes qualifier-only AI queries and intercepts GitHub API HTTP `422 Validation Failed` errors, automatically falling back to safe deterministic query variants without crashing runs.

### [ADR-0013: Unified JSON Configuration Path for CLI and GUI](decisions/ADR-0013-unified-json-config-cli-gui.md)
Establishes a unified JSON configuration schema shared between `gui_settings.json` and CLI `--config-file`, with deterministic precedence rules (CLI flag > Config file > Default).

### [ADR-0014: Resumable Run-State Persistence for Clone Sessions](decisions/ADR-0014-resumable-clone-run-state.md)
Maintains atomic `metadata/run_state_*.json` records per repository, allowing interrupted harvests to resume via `--resume-state-file` and cleanly skip already downloaded projects.

### [ADR-0015: Incremental Mode Based on Historical Search Metadata](decisions/ADR-0015-incremental-mode-previous-metadata.md)
Implements `--incremental` mode by scanning previous search metadata in the target output directory and de-duplicating repository IDs before executing new AI filtering or cloning passes.

### [ADR-0016: SQLite Export as an Embedded Analytics Surface](decisions/ADR-0016-sqlite-export-analytics-surface.md)
Provides embedded relational analytics via Python standard library `sqlite3` (`--export-sqlite`), recording runs and repositories in structured tables with indexed query surfaces.

### [ADR-0017: GitHub REST Rate-Limit Guidance Compliance](decisions/ADR-0017-github-rest-rate-limit-guidance.md)
Adheres to GitHub REST API `2026-03-10` guidelines: prioritizes `Retry-After`, waits on `X-RateLimit-Reset` only when `X-RateLimit-Remaining == 0`, and applies exponential backoff for secondary rate limits.

### [ADR-0018: Authoritative Retry Results in Run-State Tracking](decisions/ADR-0018-authoritative-retry-results-run-state.md)
Ensures successful retries update the primary run-state records authoritatively while tracking retries on dedicated telemetry counters to prevent UI progress distortion.

### [ADR-0019: Windows Reserved Device Names Path Hardening](decisions/ADR-0019-windows-reserved-device-names-hardening.md)
Sanitizes clone path segments against Windows reserved DOS device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) by prefixing segments with `reserved_`, preventing Win32 filesystem errors.

### [ADR-0020: Verifiable Windows Release Package Workflow](decisions/ADR-0020-verifiable-windows-release-package.md)
Establishes reproducible PowerShell packaging pipelines (`release_windows.ps1`), SHA-256 manifests, Authenticode signature checks, and integrity verification gates (`verify_release_windows.ps1`).

### [ADR-0021: Explicit Profile-Driven Ollama Runtime Options](decisions/ADR-0021-ollama-runtime-profiles.md)
Standardizes LLM inference runtime parameters (`temperature`, `num_ctx`, `num_predict`) across GUI profiles and CLI parameters, preventing truncated JSON responses from local models.

### [ADR-0022: Configurable and Logged Git Clone Strategies](decisions/ADR-0022-configurable-clone-strategy.md)
Exposes shallow partial cloning (`--depth 1`, `--filter=blob:none`, `--single-branch`, `--no-tags`) as fast defaults while supporting full archival fidelity and logging the active strategy.

### [ADR-0023: Optional GraphQL Metadata Enrichment on Final Shortlist](decisions/ADR-0023-optional-graphql-enrichment.md)
Enriches post-filtered candidate shortlists with default branch HEAD commit OIDs, releases, homepages, and topics via batched GraphQL queries while conserving API quota.

### [ADR-0024: Bounded In-Memory Deep Relevance Scoring via README/Tree](decisions/ADR-0024-bounded-deep-relevance-scoring.md)
Evaluates README text and Git file tree blobs in memory for candidate shortlists (`--deep-relevance`), computing semantic relevance without persisting unneeded file content to disk.

### [ADR-0025: Universal OpenAI-Compatible AI Provider Adapter](decisions/ADR-0025-universal-openai-compatible-adapter.md)
Implements universal support for OpenAI-compatible `/chat/completions` and `/models` gateways (OpenRouter, Groq, LM Studio, vLLM) secured by Windows DPAPI encryption.
