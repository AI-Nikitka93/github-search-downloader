# Step-by-Step Onboarding Tutorial

Welcome to **GitHub Search Downloader**! This tutorial guides you from a fresh installation through generating a GitHub personal access token, launching your first date-sharded search, applying AI relevance filtering, and analyzing results in a local SQLite database.

---

## Prerequisites

Before starting, ensure your Windows system meets the following requirements:
1. **Windows 10 (x64) or Windows 11**.
2. **Git for Windows** installed and available in system PATH (git --version).
3. **Python 3.11+** (if running from source or CLI).
4. Optional: **Ollama** installed locally (ollama serve) or an API key from an OpenAI-compatible provider (OpenRouter, Groq, DeepSeek).

---

## Step 1: Create a GitHub Personal Access Token

While GitHub allows anonymous searching (limited to 60 requests/hour), authenticating raises your quota to **5,000 requests/hour** and enables GraphQL repository enrichment.

1. Log into your GitHub account at [github.com](https://github.com).
2. Navigate to **Settings** -> **Developer Settings** -> **Personal access tokens** -> **Tokens (classic)** (or Fine-grained tokens).
3. Click **Generate new token (classic)**.
4. Set note: GitHubSearchDownloader.
5. Select scope: public_repo (Read-only access to public repositories).
6. Click **Generate token** and copy the string (e.g., ghp_... or github_pat_...).

---

## Step 2: Store Token in Windows DPAPI Vault

GitHub Search Downloader uses hardware/user-bound Windows DPAPI encryption to safeguard credentials.

### Option A: Via GUI (First-Run Wizard)
1. Double-click start_gui.bat in the application folder.
2. The First-Run Wizard will appear automatically.
3. Paste your GitHub Token into the secure input field and click **Save & Test Connection**.
4. The token is immediately encrypted in %LOCALAPPDATA%\GithubSearchDownloader\secrets\github_token.json with zero plaintext leakage.

### Option B: Via CLI
`powershell
python app.py --save-github-token
`
You will be prompted to securely enter your token. Verify its status:
`powershell
python app.py --show-token-status
`

---

## Step 3: Run Your First Discovery Search (Dry-Run Mode)

Dry-run mode searches the GitHub API, applies date-sharding, scores repositories, and exports structured metadata without downloading git blobs to disk.

`powershell
python app.py --query "kubernetes operators" --output ".\output\k8s_discovery" --dry-run --max-repos 10 --export-sqlite "metadata\k8s.sqlite"
`

**What Happens:**
1. The engine checks the total count for kubernetes operators.
2. If total results exceed 1,000, it recursively divides the date range into smaller slices.
3. Metadata for the top 10 repositories is saved to output\k8s_discovery\metadata\search_*.json.
4. A queryable SQLite database is created at output\k8s_discovery\metadata\k8s.sqlite.

---

## Step 4: Configure AI Relevance Filtering

To filter out irrelevant tutorials, homework assignments, or dead forks:

1. Ensure Ollama is running locally:
`powershell
ollama run llama3.2:latest
`
2. Run a filtered harvest:
`powershell
python app.py --query "malware dynamic analysis" --output ".\output\malware_tools" --dry-run --max-repos 15 --ai-filter --ai-provider ollama --ai-filter-endpoint "http://127.0.0.1:11434" --ai-filter-model "llama3.2:latest" --ai-filter-min-score 0.65
`

**How It Works:**
- **Auto-Keep:** High-scoring repositories skip LLM review.
- **Auto-Drop:** Low-relevance noise is rejected before sending prompts.
- **LLM Review:** Ambiguous candidates are evaluated against strict criteria.

---

## Step 5: Query Exported Data in SQLite

Open the generated SQLite database using Python, SQLite CLI, or DB Browser for SQLite:

`powershell
python -c "import sqlite3; conn = sqlite3.connect(r'output\k8s_discovery\metadata\k8s.sqlite'); print(conn.execute('SELECT full_name, stars, language FROM repositories LIMIT 5').fetchall())"
`

---

## Next Steps

- Explore full CLI parameter options in [CLI Reference](CLI_REFERENCE.md).
- Understand internal sharding and rate-limiting in [Architecture Guide](ARCHITECTURE.md).
- View project milestones in [Roadmap](ROADMAP.md).

---
*Architected & Packaged by [AI_Nikitka](https://t.me/Ai_nikitka93)*
