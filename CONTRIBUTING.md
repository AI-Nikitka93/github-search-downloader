# Contributing to GitHub Search Downloader

Thank you for your interest in contributing to GitHub Search Downloader.

## Development Setup

### Prerequisites
- Windows 11 (or Windows 10 x64)
- Python 3.11+
- Git in system `PATH`
- Optional: Ollama locally or access to an OpenAI-compatible endpoint for AI features

### Local Environment
```powershell
# Clone the repository
git clone https://github.com/AI-Nikitka93/github-search-downloader.git
cd github-search-downloader

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install package in editable mode with development/build dependencies
python -m pip install -e .[build]
```

---

## Testing & Quality Gates

Run all automated unit tests before submitting changes:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Verify dry-run CLI execution:

```powershell
python app.py --query "test" --output ".\_smoke_output\test" --dry-run --max-repos 5
```

Check AST parity between English and Russian documentation:

```powershell
python scripts/verify_ast_parity.py
```

---

## Commit & Decision Shadow Protocol

Every commit must document **why** architectural changes were made using Git Trailers:

```text
<type>(<scope>): <what changed> — <why>

Constraint: <constraint that influenced the implementation>
Rejected: <rejected alternative> | <reason for rejection>
Directive: <instruction for future AI agents / developers>
Not-tested: <untested edge cases>
```

### Allowed Types
- `feat`: New user-facing feature or CLI option
- `fix`: Bug fix in harvester, planner, or UI
- `docs`: Documentation updates (maintaining 100% AST parity)
- `refactor`: Internal code improvement without behavioral changes
- `test`: Adding or improving unit tests
- `chore`: Packaging, release scripts, or metadata maintenance

---

## Contributor License Agreement (CLA)

By submitting a Pull Request, patch, or code contribution to this repository, you agree to the following terms:

1. **Work Made for Hire & Assignment:** To the maximum extent permitted by applicable law, all contributions shall be considered a "work made for hire." To the extent any contribution does not qualify as a work made for hire, you hereby **irrevocably assign** to the project copyright holder all right, title, and interest (including all patent, copyright, trademark, and trade secret rights) in and to the contribution.
2. **Representation of Originality:** You represent and warrant that your contribution is your original creation and does not infringe upon any third-party intellectual property rights.
3. **No Dual Licensing:** Contributions are incorporated into the proprietary distribution under the terms specified in [LICENSE.txt](LICENSE.txt).
