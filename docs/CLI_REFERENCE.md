# Command-Line Interface (CLI) Reference

This document provides a comprehensive technical reference for all CLI arguments, parameters, environment variables, and exit codes supported by `app.py`.

---

## General Command Syntax

```powershell
python app.py --query <string> [options]
```

---

## Search & Filtering Parameters

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--query`, `-q` | `string` | *(Required)( | GitHub search query terms, topics, or keywords. |
| `--min-stars` | `integer` | `0` | Minimum repository stargazer count filter. |
| `--language`, `-l` | `string` | `""` | Primary programming language filter (e.g., `python`, `rust`, `go`). |
| `--created-after` | `YYYY-MM-DD` | `2008-01-01` | Filter repositories created on or after this date. |
| `--created-before` | `YYYY-MM-DD` | Today | Filter repositories created on or before this date. |
| `--max-age-years` | `integer` | `0` (Off) | Restrict search to repositories created within the last N years. |
| `--sort` | `string` | `stars` | Sorting metric: `stars`, `forks`, `updated`. |
| `--order` | `string` | `desc` | Sort direction: `desc` (descending) or `asc` (ascending). |
| `--max-repos` | `integer` | `0` (Uncapped) | Maximum total repositories to harvest (0 = collect all discovered). |
| `--include-keywords` | `csv string` | `""` | Comma-separated list of required keywords in name or description. |
| `--exclude-keywords` | `csv string` | `""` | Comma-separated list of prohibited keywords to filter out noise. |
| `--no-sharding` | `switch` | `False` | Force-disable date bisection sharding (limits results to first 1,000). |

---

## Download & Git Cloning Parameters

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `path` | `.\output` | Root directory where cloned repos and metadata are saved. |
| `--workers`, `-w` | `integer` | `4` | Number of concurrent Git clone background threads. |
| `--batch-size` | `integer` | `100` | Number of search results fetched per GitHub API page (max 100). |
| `--clone-timeout` | `integer` | `300` | Subprocess timeout per repository clone in seconds. |
| `--retry-failed-clones` | `integer` | `2` | Number of retry attempts on network or transient clone failure. |
| `--retry-delay-seconds` | `integer` | `5` | Backoff delay between failed clone retry attempts. |
| `--no-skip-existing` | `switch` | `False` | Force re-cloning even if destination directory already exists. |
| `--full-clone` | `switch` | `False` | Perform complete git history clone instead of optimized shallow clone. |
| `--clone-depth` | `integer` | `1` | Git shallow commit depth (when `--full-clone` is not set). |
| `--dry-run` | `switch` | `False` | Execute search, AI scoring, and metadata export without downloading code. |

---

## AI Relevance & Filtering Parameters

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--ai-filter` | `switch` | `False` | Enable 2-phase AI review pool and semantic relevance scoring. |
| `--ai-provider` | `string` | `ollama` | AI Provider: `ollama`, `openai-compatible`, `openrouter`, `groq`, `deepseek`. |
| `--ai-filter-endpoint` | `URL` | `http://127.0.0.1:11434` | REST API endpoint URL for the selected AI service. |
| `--ai-filter-model` | `string` | `llama3.2:latest` | Model identifier to dispatch evaluation prompts to. |
| `--ai-filter-timeout` | `integer` | `20` | HTTP request timeout for LLM inference in seconds. |
| `--ai-filter-min-score` | `float` | `0.55` | Relevance acceptance score threshold (0.0 - 1.0). |
| `--ai-filter-max-reviews` | `integer` | `10` | Maximum candidate repositories sent to the LLM per batch. |
| `--deep-relevance` | `switch` | `False` | Fetch README and Git tree via API to score candidate repositories. |
| `--deep-relevance-max-repos` | `integer` | `25` | Maximum candidates to inspect with deep relevance. |

---

## Export & State Parameters

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--export-sqlite` | `path` | `None` | Export harvested repository metadata into a local SQLite database. |
| `--export-csv` | `switch` | `False` | Export harvested repository metadata into a sanitized CSV file. |
| `--graphql-enrich` | `switch` | `False` | Enrich repository metadata via batch GitHub GraphQL API queries. |
| `--incremental` | `switch` | `False` | Deduplicate and skip repositories recorded in historical runs. |
| `--resume-state` | `path` | `None` | Resume an interrupted harvest run from an existing state JSON file. |

---

## Credentials & Secrets Management

| Flag | Description |
| :--- | :--- |
| `--save-github-token` | Securely store a GitHub Personal Access Token into Windows DPAPI vault. |
| `--save-ai-api-key` | Securely store a cloud II API Key into Windows DPAPI vault. |
| `--show-token-status` | Display whether GitHub and AI credentials are currently enrolled. |
| `--delete-saved-github-token` | Remove the GitHub Token from the Windows DPAPI encrypted vault. |
| `--delete-saved-ai-api-key` | Remove the II API Key from the Windows DPAPI encrypted vault. |

---

## Environment Variables

| Variable | Description |
| :--- | :--- |
| `GITHUB_TOKEN` | Fallback GitHub Personal Access Token if DPAPI vault is unpopulated. |
| `OPENROUTER_API_KEY` | Fallback OpenRouter API key. |
| `OPENAI_API_KEY` | Fallback generic OpenAI-compatible API key. |
| `GROQ_API_KEY` | Fallback Groq API key. |
| `DEEPSEEK_API_KEY` | Fallback DeepSeek API key. |

---

## Exit Codes

| Code | Meaning |
| :--- | :--- |
| `0` | Success: Search, export, or clone completed without errors. |
| `1` | Configuration or CLI argument validation error. |
| `2` | Network failure or unrecoverable GitHub rate limit exhaustion. |
| `130` | Execution cancelled by user (Ctrl+C / SIGINT). |

---
*Architected & Packaged by [AI_Nikitka](https://t.me/Ai_nikitka93)*
