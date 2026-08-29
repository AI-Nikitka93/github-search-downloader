## Summary of Changes

Provide a clear and concise description of what this Pull Request accomplishes.

## Motivation & Context

- Why is this change required?
- What problem does it solve?
- If it fixes an open issue, link it here: Closes #

## Changes Made

- [ ] Core Engine / API (`src/github_harvester/`)
- [ ] GUI Interface (`gui_app.py`)
- [ ] CLI Routing (`app.py`)
- [ ] Exporters & Storage (`exporters.py`, SQLite, CSV)
- [ ] Packaging & Windows Scripts (`*.ps1`, `packaging/`)
- [ ] Documentation & AST parity (`README.md`, `README.ru.md`, `docs/`)

## Verification & Proof of Work

- [ ] Unit tests pass: `python -m unittest discover -s tests -p "test_*.py"`
- [ ] AST Parity passes: `python scripts/verify_ast_parity.py`
- [ ] Dry-run tested: `python app.py --query "test" --output ".\_smoke_output\test" --dry-run --max-repos 5`

### Raw Test Log
```text
(Paste terminal stdout showing Exit Code 0)
```

## Contributor Agreement
- [ ] I agree to the CLA terms outlined in [CONTRIBUTING.md](CONTRIBUTING.md).
