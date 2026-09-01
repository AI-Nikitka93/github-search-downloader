from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from github_harvester.models import Repo


INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
NON_ALNUM = re.compile(r"[^A-Za-z0-9_-]+")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "using",
    "tool",
    "tools",
    "project",
    "repository",
    "repo",
    "python",
    "javascript",
    "typescript",
}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class CloneResult:
    repo_full_name: str
    target_path: Path
    status: str
    message: str


@dataclass(frozen=True)
class CloneOptions:
    depth: int = 1
    partial_clone: bool = True
    single_branch: bool = True
    no_tags: bool = True


def ensure_git_available() -> None:
    if shutil.which("git"):
        return
    raise RuntimeError("Git не установлен или недоступен в PATH.")


def download_repositories(
    repositories: Sequence[Repo],
    output_root: Path,
    workers: int = 4,
    clone_timeout: int = 900,
    skip_existing: bool = True,
    progress_callback: Callable[[int, int, CloneResult], None] | None = None,
    log_callback: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    clone_options: CloneOptions | None = None,
) -> list[CloneResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[CloneResult] = []
    total = len(repositories)
    completed_count = 0
    logger = log_callback or (lambda _: None)
    effective_clone_options = clone_options or CloneOptions()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for repo in repositories:
            logger(f"Старт клонирования: {repo.full_name}")
            futures.append(
                executor.submit(
                    clone_repository,
                    repo,
                    output_root,
                    clone_timeout,
                    skip_existing,
                    logger,
                    cancel_event,
                    effective_clone_options,
                )
            )
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed_count += 1
            if progress_callback:
                progress_callback(completed_count, total, result)
    return sorted(results, key=lambda item: item.repo_full_name.lower())


def clone_repository(
    repository: Repo,
    output_root: Path,
    clone_timeout: int = 900,
    skip_existing: bool = True,
    log_callback: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    clone_options: CloneOptions | None = None,
) -> CloneResult:
    owner, repo_name = repository.full_name.split("/", maxsplit=1)
    safe_owner = sanitize_path_segment(owner)
    safe_repo = sanitize_path_segment(repo_name).lower()
    owner_dir = output_root / safe_owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    logger = log_callback or (lambda _: None)

    existing_repo_path = find_existing_repo_path(owner_dir, safe_repo)
    if existing_repo_path:
        if skip_existing:
            logger(f"Пропуск (уже существует): {repository.full_name} -> {existing_repo_path}")
            return CloneResult(repository.full_name, existing_repo_path, "skipped", "Папка уже существует.")
        logger(f"Ошибка (конфликт папки): {repository.full_name} -> {existing_repo_path}")
        return CloneResult(repository.full_name, existing_repo_path, "failed", "Целевая папка уже существует.")

    folder_name = build_repo_folder_name(repository)
    target_path = owner_dir / folder_name

    if cancel_event and cancel_event.is_set():
        logger(f"Отменено до старта clone: {repository.full_name}")
        return CloneResult(repository.full_name, target_path, "cancelled", "Остановлено пользователем.")

    if target_path.exists():
        if skip_existing:
            logger(f"Пропуск (target exists): {repository.full_name} -> {target_path}")
            return CloneResult(repository.full_name, target_path, "skipped", "Папка уже существует.")
        logger(f"Ошибка (target exists): {repository.full_name} -> {target_path}")
        return CloneResult(repository.full_name, target_path, "failed", "Целевая папка уже существует.")

    command = build_git_clone_command(repository, target_path, clone_options or CloneOptions())
    logger(f"git clone start: {repository.full_name} -> {target_path}")
    start_time = time.monotonic()
    next_heartbeat = start_time + 15.0

    with tempfile.TemporaryFile() as err_file:
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=err_file,
                creationflags=creationflags,
            )
        except Exception as exc:
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)
            logger(f"Ошибка запуска git clone для {repository.full_name}: {exc}")
            return CloneResult(repository.full_name, target_path, "failed", f"Ошибка запуска git clone: {exc}")

        timed_out = False
        while True:
            if cancel_event and cancel_event.is_set():
                kill_process_tree(process.pid)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    kill_process_tree(process.pid)
                if target_path.exists():
                    shutil.rmtree(target_path, ignore_errors=True)
                return CloneResult(
                    repository.full_name,
                    target_path,
                    "cancelled",
                    "Остановлено пользователем.",
                )
            return_code = process.poll()
            if return_code is not None:
                break

            elapsed = time.monotonic() - start_time
            if elapsed >= clone_timeout:
                timed_out = True
                kill_process_tree(process.pid)
                break

            now = time.monotonic()
            if now >= next_heartbeat:
                logger(f"Клонирование идет: {repository.full_name} ({int(elapsed)} сек)")
                next_heartbeat = now + 15.0
            time.sleep(1)

        if timed_out:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                kill_process_tree(process.pid)
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)
            return CloneResult(
                repository.full_name,
                target_path,
                "failed",
                f"Превышен таймаут клонирования ({clone_timeout} сек).",
            )

        process.wait(timeout=10)
        if process.returncode == 0:
            logger(f"git clone success: {repository.full_name} -> {target_path}")
            return CloneResult(repository.full_name, target_path, "cloned", "OK")

        err_file.seek(0)
        stderr_text = err_file.read().decode("utf-8", errors="replace").strip()
        error_message = stderr_text or f"git clone завершился с кодом {process.returncode}"
        logger(f"git clone failed: {repository.full_name}: {error_message}")
        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)
        return CloneResult(repository.full_name, target_path, "failed", error_message)


def build_git_clone_command(repository: Repo, target_path: Path, options: CloneOptions) -> list[str]:
    clone_url = str(repository.clone_url or "").strip()
    if not re.match(r"^(https?|git)://", clone_url):
        raise ValueError(f"Недопустимый протокол clone URL: {clone_url}")
    command = ["git", "clone"]
    if options.depth > 0:
        command.extend(["--depth", str(options.depth)])
    if options.partial_clone:
        command.append("--filter=blob:none")
    if options.single_branch:
        command.append("--single-branch")
    if options.no_tags:
        command.append("--no-tags")
    command.extend(["--quiet", "--", clone_url, str(target_path)])
    return command


def sanitize_path_segment(raw_segment: str) -> str:
    cleaned = INVALID_PATH_CHARS.sub("_", raw_segment).strip().rstrip(".")
    if not cleaned:
        return "unknown"
    device_name = cleaned.split(".", maxsplit=1)[0].upper()
    if device_name in WINDOWS_RESERVED_NAMES:
        return f"reserved_{cleaned}"
    return cleaned


def build_repo_folder_name(repository: Repo) -> str:
    owner, repo_name = repository.full_name.split("/", maxsplit=1)
    del owner
    base_repo = normalize_slug(sanitize_path_segment(repo_name))
    summary = build_description_slug(repository.description)
    if summary:
        combined = f"{base_repo}__{summary}"
    else:
        combined = base_repo
    combined = combined[:110].strip("._- ")
    return combined or "unknown"


def build_description_slug(description: str, max_words: int = 6, max_chars: int = 64) -> str:
    words = [w.lower() for w in WORD_PATTERN.findall(description or "")]
    if not words:
        return ""
    filtered = [word for word in words if word not in STOP_WORDS and len(word) >= 3]
    if not filtered:
        filtered = words
    slug = "_".join(filtered[:max_words])
    slug = normalize_slug(slug)
    return slug[:max_chars].strip("._- ")


def normalize_slug(text: str) -> str:
    normalized = NON_ALNUM.sub("_", text).strip("._- ")
    normalized = re.sub(r"_+", "_", normalized)
    return normalized or "unknown"


def find_existing_repo_path(owner_dir: Path, repo_name_slug: str) -> Path | None:
    if not owner_dir.exists():
        return None
    prefix = f"{repo_name_slug}__"
    for entry in owner_dir.iterdir():
        if not entry.is_dir():
            continue
        lowered = entry.name.lower()
        if lowered == repo_name_slug or lowered.startswith(prefix):
            return entry
    return None


def kill_process_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
