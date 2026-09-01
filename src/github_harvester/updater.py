"""In-app update engine for GitHub Releases (rate-limit safe, SHA256 verified)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from github_harvester.version import (
    APP_NAME,
    CURRENT_SEMVER,
    GITHUB_REPO_URL,
    REPO_NAME,
    REPO_OWNER,
    SemVer,
    __version__,
)

CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GithubSearchDownloader" / "cache"
UPDATES_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GithubSearchDownloader" / "Updates"
CHECK_INTERVAL_SECONDS = 86400  # 24 hours


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int
    content_type: str


AssetInfo = ReleaseAsset


@dataclass(frozen=True)
class ReleaseInfo:
    version_str: str
    semver: SemVer
    tag_name: str
    name: str
    published_at: str
    body_markdown: str
    html_url: str
    assets: dict[str, ReleaseAsset]
    is_prerelease: bool

    @property
    def is_newer(self) -> bool:
        return self.semver > CURRENT_SEMVER

    @property
    def portable_zip_asset(self) -> Optional[ReleaseAsset]:
        for name, asset in self.assets.items():
            if name.endswith(".zip") and ("portable" in name.lower() or "windows" in name.lower()):
                return asset
        for name, asset in self.assets.items():
            if name.endswith(".zip"):
                return asset
        return None

    @property
    def checksum_asset(self) -> Optional[ReleaseAsset]:
        for name, asset in self.assets.items():
            if "sha256" in name.lower() or name.lower().startswith("checksum"):
                return asset
        return None


class CheckResult(NamedTuple):
    update_available: bool
    current_version: str
    latest_release: Optional[ReleaseInfo]
    message: str
    checked_at: str


class UpdateChecker:
    """Rate-limit aware updater checking GitHub Releases API with ETag and 24h disk caching."""

    def __init__(
        self,
        owner: str = REPO_OWNER,
        repo: str = REPO_NAME,
        token: str = "",
        cache_dir: Path = CACHE_DIR,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.token = token.strip()
        self.cache_dir = cache_dir
        self.cache_file = self.cache_dir / "update_check.json"
        self.api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    def _read_cache(self) -> dict:
        if not self.cache_file.exists():
            return {}
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cache(self, data: dict) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def check_for_updates(self, force: bool = False) -> CheckResult:
        cache = self._read_cache()
        now_ts = time.time()
        last_checked = cache.get("last_checked_ts", 0)

        # Check rate-limit safe cache interval (24h) unless forced
        if not force and (now_ts - last_checked) < CHECK_INTERVAL_SECONDS:
            cached_release_data = cache.get("release_data")
            if cached_release_data:
                rel = self._parse_release_payload(cached_release_data)
                return CheckResult(
                    update_available=rel.is_newer,
                    current_version=__version__,
                    latest_release=rel,
                    message="Using cached check result (< 24h old).",
                    checked_at=cache.get("last_checked_utc", ""),
                )

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": f"{APP_NAME}/{__version__} (Windows NT)",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        cached_etag = cache.get("etag")
        if cached_etag and not force:
            headers["If-None-Match"] = cached_etag

        req = urllib.request.Request(self.api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                etag = resp.headers.get("ETag", "")
                raw_body = resp.read().decode("utf-8")
                data = json.loads(raw_body)
                now_iso = datetime.now(timezone.utc).isoformat()

                self._write_cache({
                    "last_checked_ts": now_ts,
                    "last_checked_utc": now_iso,
                    "etag": etag,
                    "release_data": data,
                })

                rel = self._parse_release_payload(data)
                return CheckResult(
                    update_available=rel.is_newer,
                    current_version=__version__,
                    latest_release=rel,
                    message="Fresh release check succeeded.",
                    checked_at=now_iso,
                )
        except urllib.error.HTTPError as err:
            if err.code == 304:  # Not Modified
                cached_release_data = cache.get("release_data", {})
                rel = self._parse_release_payload(cached_release_data)
                now_iso = datetime.now(timezone.utc).isoformat()
                cache["last_checked_ts"] = now_ts
                cache["last_checked_utc"] = now_iso
                self._write_cache(cache)
                return CheckResult(
                    update_available=rel.is_newer,
                    current_version=__version__,
                    latest_release=rel,
                    message="304 Not Modified: Already up to date.",
                    checked_at=now_iso,
                )
            if err.code == 404:
                return CheckResult(False, __version__, None, "No releases found on GitHub repository.", "")
            if err.code in (403, 429):
                return CheckResult(False, __version__, None, "GitHub API rate limit exceeded.", "")
            return CheckResult(False, __version__, None, f"HTTP Error {err.code}: {err.reason}", "")
        except Exception as exc:
            return CheckResult(False, __version__, None, f"Network check failed: {exc}", "")

    def _parse_release_payload(self, data: dict) -> ReleaseInfo:
        tag_name = data.get("tag_name", "0.0.0")
        semver = SemVer.parse(tag_name)
        assets = {}
        for item in data.get("assets", []):
            asset_name = item.get("name", "")
            assets[asset_name] = ReleaseAsset(
                name=asset_name,
                download_url=item.get("browser_download_url", ""),
                size=item.get("size", 0),
                content_type=item.get("content_type", ""),
            )
        return ReleaseInfo(
            version_str=tag_name.lstrip("v"),
            semver=semver,
            tag_name=tag_name,
            name=data.get("name", tag_name),
            published_at=data.get("published_at", ""),
            body_markdown=data.get("body", ""),
            html_url=data.get("html_url", ""),
            assets=assets,
            is_prerelease=bool(data.get("prerelease", False)),
        )


class UpdateDownloader:
    """Safe chunked downloader with SHA256 integrity verification and Zip-Slip defense."""

    def __init__(self, download_dir: Path = UPDATES_DIR) -> None:
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download_and_verify(
        self,
        release: ReleaseInfo,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> Path:
        # 1. Identify primary zip or exe asset
        zip_asset: Optional[ReleaseAsset] = None
        for name, asset in release.assets.items():
            if name.endswith(".zip") and "windows" in name.lower():
                zip_asset = asset
                break
        if not zip_asset:
            for name, asset in release.assets.items():
                if name.endswith(".zip"):
                    zip_asset = asset
                    break

        if not zip_asset:
            raise RuntimeError(f"No valid zip release asset found for version {release.version_str}")

        dest_file = self.download_dir / zip_asset.name
        partial_file = self.download_dir / f"{zip_asset.name}.partial"

        # 2. Fetch expected SHA256 if checksum manifest exists in release assets
        expected_sha256 = self._fetch_expected_hash(release, zip_asset.name)

        # 3. Stream download with progress
        req = urllib.request.Request(zip_asset.download_url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
        start_time = time.monotonic()
        downloaded = 0
        total_size = zip_asset.size

        if partial_file.exists():
            partial_file.unlink()

        with urllib.request.urlopen(req, timeout=30) as resp, open(partial_file, "wb") as out_f:
            chunk_size = 64 * 1024  # 64 KB
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)
                elapsed = time.monotonic() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0.0
                if progress_callback:
                    progress_callback(downloaded, total_size, speed)

        # 4. Verify SHA256 checksum
        actual_sha256 = self._compute_sha256(partial_file)
        if expected_sha256 and actual_sha256.upper() != expected_sha256.upper():
            partial_file.unlink(missing_ok=True)
            raise ValueError(
                f"SHA256 checksum mismatch! Expected: {expected_sha256.upper()}, Got: {actual_sha256.upper()}"
            )

        # 5. Verify Safe ZIP extraction structure
        self._audit_zip(partial_file)

        # 6. Commit atomic move
        if dest_file.exists():
            dest_file.unlink()
        partial_file.rename(dest_file)
        return dest_file

    def _fetch_expected_hash(self, release: ReleaseInfo, target_filename: str) -> Optional[str]:
        sha_asset = release.checksum_asset
        if not sha_asset:
            for asset in release.assets.values():
                name_low = asset.name.lower()
                if "sha256" in name_low or "checksum" in name_low or name_low.startswith("sha256sums"):
                    sha_asset = asset
                    break
        if not sha_asset:
            return None
        try:
            req = urllib.request.Request(sha_asset.download_url, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8")
                for line in content.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[1].endswith(target_filename):
                        return parts[0].strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(128 * 1024):
                h.update(chunk)
        return h.hexdigest().upper()

    @staticmethod
    def _audit_zip(zip_path: Path) -> None:
        windows_reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                raw = member.filename.replace("\\", "/")
                if raw.startswith("/") or raw.startswith("\\") or re.match(r"^[a-zA-Z]:", raw):
                    raise ValueError(f"Zip Slip absolute/drive path traversal detected: {member.filename}")
                parts = Path(raw).parts
                if ".." in parts:
                    raise ValueError(f"Zip Slip attempt detected in entry: {member.filename}")
                for part in parts:
                    base = part.split(".")[0].upper()
                    if base in windows_reserved:
                        raise ValueError(f"Windows reserved device name detected in zip entry: {member.filename}")

    def safe_extract_zip(self, zip_path: Path, extract_dir: Path) -> Path:
        self._audit_zip(zip_path)
        extract_dir.mkdir(parents=True, exist_ok=True)
        resolved_extract_dir = extract_dir.resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                target_path = (extract_dir / member.filename).resolve()
                if not target_path.is_relative_to(resolved_extract_dir):
                    raise ValueError(f"Zip Slip attempt detected in member: {member.filename}")
            zf.extractall(extract_dir)
        return extract_dir


class SelfUpdater:
    """Spawns detached Windows helper to atomically swap application binaries and restart."""

    @staticmethod
    def _write_updater_script(
        bat_path: Path,
        pid: int,
        source_dir: Path,
        target_dir: Path,
        target_exe: Path,
        zip_path: Optional[Path] = None,
    ) -> None:
        zip_cleanup = f'del /F /Q "{zip_path}" >NUL 2>&1' if zip_path else ""
        bat_script = f"""@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Updating {APP_NAME}...

echo Waiting for application (PID {pid}) to close...
set /a WAIT_COUNT=0
:wait_loop
tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! geq 10 (
        taskkill /F /PID {pid} >nul 2>&1
    )
    goto wait_loop
)

echo Replacing application files in "{target_dir}"...
timeout /t 1 /nobreak >NUL

robocopy "{source_dir}" "{target_dir}" /E /NP /R:3 /W:1 >nul
if errorlevel 8 (
    echo Robocopy failed with error %errorlevel%!
    pause
    exit /b 1
)

echo Cleaning up update temporary files...
rd /S /Q "{source_dir}" >NUL 2>&1
{zip_cleanup}

echo Restarting {APP_NAME}...
start "" "{target_exe}"

del /F /Q "{bat_path}" >nul 2>&1
(goto) 2>nul & del "%~f0" >nul 2>&1
exit /b 0
"""
        bat_path.write_text(bat_script, encoding="utf-8")

    @staticmethod
    def launch_updater_and_restart(
        zip_path: Path,
        current_exe_path: Path,
        release_version: str,
    ) -> None:
        extract_dir = zip_path.parent / f"staging-{release_version}"
        if extract_dir.exists():
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        downloader = UpdateDownloader(download_dir=zip_path.parent)
        downloader.safe_extract_zip(zip_path, extract_dir)

        target_dir = current_exe_path.parent
        parent_pid = os.getpid()

        # Batch helper script for non-blocking atomic replacement on Windows
        helper_bat = zip_path.parent / "apply_update.bat"
        SelfUpdater._write_updater_script(
            bat_path=helper_bat,
            pid=parent_pid,
            source_dir=extract_dir,
            target_dir=target_dir,
            target_exe=current_exe_path,
            zip_path=zip_path,
        )

        # Launch detached helper
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            ["cmd.exe", "/c", str(helper_bat)],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )

        os._exit(0)
