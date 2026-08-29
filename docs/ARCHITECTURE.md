# Architecture

## Purpose

Collect large sets of GitHub repositories for a given topic/query and store them locally for future AI-assisted analysis.

## Components

- `gui_app.py`
  - Desktop UI entry point for non-CLI usage.
  - Collects parameters, starts background run, shows progress/logs.
  - Supports stop/cancel action during active runs.
  - Supports AI planning flow for natural-language tasks.
  - Supports AI provider profiles for local Ollama and OpenAI-compatible endpoints.
  - Supports quality profiles (`Точность`, `Баланс`, `Полнота`) for one-click strategy tuning.
  - Lets users save, load, and delete the GitHub API token through local Windows protected storage without writing it to `gui_settings.json`.
  - Lets users save, load, and delete cloud AI API keys through local Windows protected storage without writing them to `gui_settings.json`.

- `start_gui.bat`
  - Double-click launcher for Windows users.

- `build_windows.ps1` / `release_windows.ps1`
  - Build the PyInstaller one-file executable.
  - Package the Windows release zip with README/architecture docs.
  - Emit SHA256 checksums, release manifest, and Authenticode signature status.
  - Stamp the staged installer version from the release `-Version` value before zipping.
  - Compute SHA256 hashes through .NET so packaging automation does not depend on PowerShell cmdlet autoload behavior.
  - Include `LICENSE.txt` in release artifacts.
  - Include per-user install/uninstall/update-check PowerShell scripts in the release zip.
  - Include the standalone release verifier in the release zip.
  - Emit `update_manifest.json` with version, package URL, SHA256 hashes, signature state, and installer/updater script names for static-hosted update channels.
  - Emit staged `update_channel.json` when `-UpdateBaseUrl` is provided so installed updaters can discover the hosted manifest.
  - Optionally enforce code signing when a certificate and SignTool are available.

- `verify_release_windows.ps1`
  - Verifies `release_manifest.json`, `update_manifest.json`, `SHA256SUMS.txt`, release zip contents, SHA256 hashes, and Authenticode status.
  - Uses the same .NET SHA256 path as the release builder/updater.
  - Treats Authenticode lookup failures as `Unavailable` for non-strict unsigned verification, while `-RequireSignature` still requires `Valid`.
  - Provides hard gates for public publishing through `-RequireSignature` and `-RequireHostedUpdateUrl`.

- `packaging/install_windows.ps1` / `packaging/uninstall_windows.ps1`
  - Install or remove the app per-user under `%LOCALAPPDATA%\Programs\GithubSearchDownloader`.
  - Create/remove Start Menu shortcut and optional Desktop shortcut.
  - Copy README, license, architecture note, updater, uninstaller, and hosted channel config when present.
  - Copy `update_channel.json` into the install directory when the release was built with a hosted update channel.
  - Register/remove the per-user Windows uninstall entry under `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\GithubSearchDownloader`.
  - Require GithubSearchDownloader product markers before recursively removing a custom install directory.
  - Avoid requiring administrator privileges for standard Windows installs.

- `packaging/check_updates_windows.ps1`
  - Reads an explicit `-UpdateManifest`, an installed `update_channel.json`, or a local `update_manifest.json`.
  - Compares the installed/current version with `latest_version`.
  - Resolves relative package URLs from the manifest location.
  - Downloads the release zip only when `-DownloadOnly` or `-Install` is passed, using an atomic `.partial` file before replacing the final package path.
  - Verifies declared package size and rejects unsafe zip entry paths before extraction.
  - Verifies package and executable SHA256 hashes before exposing or installing an update.
  - Treats Authenticode lookup failures as `Unavailable` for non-strict unsigned download verification in automation hosts.
  - Optionally enforces Authenticode validity through `-RequireSignature`.

- `app.py`
  - CLI entry point.
  - Parses input options and passes config to shared service.
  - Supports `--config-file` (including `gui_settings.json`-compatible mapping) with CLI overrides.
  - Supports local token management commands: `--save-github-token`, `--show-token-status`, and `--delete-saved-github-token`.
  - Supports OpenAI-compatible AI provider options and local AI API key commands: `--save-ai-api-key`, `--show-ai-api-key-status`, and `--delete-saved-ai-api-key`.
  - Supports metadata-only download/resume mode via `--metadata-file` and `--resume-state-file`.
  - Supports incremental collection, include/exclude keyword filters, and SQLite export.

- `src/github_harvester/secret_store.py`
  - Stores the GitHub API token locally through Windows DPAPI for the current Windows user.
  - Writes only encrypted DPAPI ciphertext and metadata under `%LOCALAPPDATA%\GithubSearchDownloader\secrets`.
  - Stores AI provider API keys under deterministic provider/Base URL secret names without exposing endpoint/key plaintext in filenames.
  - Rejects plaintext config-file token/API-key loading; GUI and CLI resolve secrets from explicit input, environment, or protected local storage.

- `src/github_harvester/ai_planner.py`
  - Provides a shared AI provider adapter for planner/filter calls.
  - Keeps the existing Ollama route (`/api/generate`, `/api/tags`) and adds OpenAI-compatible `/chat/completions` and `/models`.
  - Normalizes provider errors for authentication, model not found, rate limits, timeouts, and local connection-refused cases.

- `src/github_harvester/service.py`
  - Shared orchestration layer used by both GUI and CLI.
  - Validates config, applies age-date filtering, runs search, writes metadata.
  - Applies keyword filters and incremental filtering before clone/AI-filtered finalization.
  - Performs adaptive low-result expansion pass before AI-filtering when candidate pool is too small.
  - Optionally runs superficial AI relevance filter on repositories before cloning.
  - Optionally enriches final repositories through GitHub GraphQL when token-backed enrichment is enabled.
  - Optionally ranks the final shortlist with bounded README/Git-tree deep relevance scoring before metadata/SQLite/clone.
  - Downloads repositories in batches, retries failed clones, supports cancellation.
  - Passes explicit clone strategy to downloader: depth, partial blob filter, single-branch, and tag fetching mode.
  - Returns final summary and run log path.

- `src/github_harvester/run_state.py`
  - Writes `metadata/run_state_*.json` with per-repository clone status.
  - Lets later runs skip already cloned/skipped repositories and retry pending/failed/cancelled items.
  - Reads previous `metadata/search_*.json` files for incremental repo-id filtering.

- `src/github_harvester/exporters.py`
  - Exports repository metadata to SQLite for local analytics.
  - Stores run records, repository records, and run-to-repository membership.
  - Migrates older local SQLite schemas when richer repository metadata columns are added.

- `src/github_harvester/github_api.py`
  - Calls GitHub Search API.
  - Sends the current GitHub REST API version header.
  - Handles retry and rate limit waiting according to `Retry-After`, primary reset, and secondary fallback rules.
  - Splits date ranges when a query exceeds 1000 results.
  - Fetches repository README content and recursive Git tree path snapshots for optional deep relevance scoring.
  - Provides token-backed GraphQL repository enrichment using REST `node_id` values and bounded batches.

- `src/github_harvester/downloader.py`
  - Verifies Git availability.
  - Clones repositories in parallel workers.
  - Builds descriptive Windows-safe folder names from repository name + description keywords.
  - Avoids Windows reserved device names in generated path segments.
  - Prevents duplicate downloads on reruns by checking existing repo folder prefix.
  - Builds reproducible `git clone` commands from `CloneOptions`; default strategy is shallow partial clone (`depth=1`, blob filter, one branch, no tags).

- `src/github_harvester/models.py`
  - Data models for repositories and search options.
  - Preserves core analytics fields such as forks, issues, watchers, size, license, fork/archive flags, and visibility.
  - Preserves GraphQL enrichment fields such as homepage URL, default branch commit, latest release, mirror/empty flags, and enrichment provenance.
  - Preserves deep relevance scores/provenance without storing README body content.

- `src/github_harvester/ai_planner.py`
  - Converts user task text to structured run parameters via AI model.
  - Supports Ollama endpoints and model discovery via `/api/tags`.
  - Sends explicit Ollama runtime options (`temperature`, `num_ctx`, `num_predict`) for reproducible planner/filter behavior.
  - Normalizes and validates model output.
  - Reused by service for Ollama JSON parsing / request helper in AI relevance filtering.

- `tests/`
  - Unit tests for core helper logic.

## Data Flow

1. User starts run from GUI (`gui_app.py`) or CLI (`app.py`).
   - Token source priority is explicit run input, `GITHUB_TOKEN`, local Windows DPAPI storage, then no token.
   - Plaintext `token` fields from config files are ignored.
2. Optional: user asks AI to prepare settings from natural-language task through Ollama or an OpenAI-compatible provider.
3. Shared service validates settings and builds search options.
4. Shared service normalizes search query for GitHub compatibility; for `422 Validation Failed` it can apply one safe fallback query and retry.
5. If candidate pool is still too small and AI-filtering is enabled, service performs one widened retrieval pass and merges unique repositories.
6. API module computes sharded date ranges.
7. API module fetches repository pages and de-duplicates by repository ID.
8. Optional: AI filter runs through the selected AI provider in two phases:
   - recall phase builds a broad candidate pool with exploration sampling,
   - precision phase applies bounded AI checks and fallback heuristics.
9. Optional GraphQL enrichment runs on the final shortlist when `graphql_enrich` is enabled and a token is available.
10. Optional deep relevance scoring fetches README and Git tree paths for the bounded final shortlist, stores only score/error fields, then reorders checked candidates by score.
11. Metadata is written to `output/metadata` with schema version (`schema_version`) for compatibility checks.
12. Optional SQLite export writes the same repository set to a queryable local database.
13. Downloader initializes `run_state_*.json` and clones repositories into `output/repos/{owner}/{repo}` in batches using the configured clone strategy.
14. Each completed clone result, including retry results, updates run-state for resume support.
15. Failed clones are retried based on configured retry policy.
16. Summary is returned to CLI output or GUI status/log panel.

## Preview and Manual Selection

- GUI includes a new workflow `Предпросмотр и выбор`:
  - run search in dry-run mode,
  - load `metadata/search_*.json`,
  - show shortlist with quick relevance recommendation.
- User can manually include/exclude repositories and then start clone only for selected items.
- Backend supports this mode via `run_download_for_repositories(...)`, which reuses:
  - batch cloning,
  - retry policy,
  - cancellation,
  - run/failure logs.

## Ollama Runtime Profiles

- GUI exposes Ollama provider profiles for fast local, quality local, and large/cloud-style model routes.
- Profiles set endpoint, model, timeout, `temperature`, `num_ctx`, and `num_predict`.
- CLI/config-file runs can set the same runtime options, so GUI and CLI behavior do not drift.

## Resume, Incremental, And Export

- `--incremental` reads previous `metadata/search_*.json` files under the output folder and skips repository IDs already recorded there.
- `--resume-state-file` reads a previous `metadata/run_state_*.json` and skips repositories already marked `cloned` or `skipped`.
- `--metadata-file` bypasses GitHub search and downloads/verifies a saved repository list.
- `--export-sqlite` writes a local SQLite database with `runs`, `repositories`, and `run_repositories`, including richer analytics fields when GitHub returns them.
- `--graphql-enrich` uses GitHub GraphQL only after final filtering/trimming, requires a token, batches `node_id` lookups, and falls back to REST metadata if enrichment cannot run.
- `--deep-relevance` uses REST README and Git Trees endpoints only after final filtering/trimming, is bounded by `--deep-relevance-max-repos`, and keeps repository rows even when an individual README/tree fetch fails.
