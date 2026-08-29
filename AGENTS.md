# AGENTS.md

## Обзор проекта
Windows-приложение (GUI + CLI) на Python для поиска, фильтрации, обогащения и скачивания репозиториев с GitHub, обходящее лимиты поиска через шардирование по датам, с поддержкой AI-планировщика и AI-отбора (Ollama, OpenAI-compatible).

## Команды верификации
- Тесты (проверено): `python -m unittest discover -s tests -p "test_*.py"`
- Сборка Windows .exe: `.\build_windows.ps1`
- Подготовка release-пакета: `.\release_windows.ps1 -Version "1.0.0"`
- Запуск CLI (проверено --dry-run): `python app.py --query "test" --dry-run --max-repos 5`
- Запуск GUI: `start_gui.bat` или `python gui_app.py`

## Архитектурные ограничения
- Стек: Python 3.11+, PyInstaller, Windows-specific (DPAPI, `.bat`, `.ps1`).
- Логика расположена в `src/github_harvester/` (service.py, ai_planner.py, github_api.py, downloader.py, exporters.py).
- Точка входа GUI: `gui_app.py`. Точка входа CLI: `app.py`.
- Токены хранятся в Windows DPAPI (`%LOCALAPPDATA%\GithubSearchDownloader\secrets`), НЕ использовать plaintext в файлах!
- Не изменять production secrets, не удалять кэши и локальные базы без причины.

## Правила тестирования
- Используется встроенный модуль `unittest`.
- Тесты лежат в папке `tests/` и должны запускаться через `python -m unittest discover -s tests -p "test_*.py"`.
