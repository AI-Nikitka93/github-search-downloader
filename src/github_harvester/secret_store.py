from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import re
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path


SECRET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
DEFAULT_SECRET_NAME = "github_token"
STORE_SCHEMA_VERSION = 1


class SecretStoreError(RuntimeError):
    """Raised when a local protected secret cannot be saved or loaded."""


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def default_secret_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "GithubSearchDownloader" / "secrets"
    return Path.home() / "AppData" / "Local" / "GithubSearchDownloader" / "secrets"


def secret_file_path(name: str = DEFAULT_SECRET_NAME, base_dir: Path | None = None) -> Path:
    safe_name = _validate_secret_name(name)
    root = base_dir or default_secret_dir()
    return root / f"{safe_name}.json"


def secret_name_for_ai_provider(provider_type: str, endpoint: str) -> str:
    provider_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(provider_type or "").strip().lower())
    provider_slug = provider_slug.replace("_", "-").strip("-") or "custom"
    provider_slug = provider_slug[:32].strip("-") or "custom"
    normalized_endpoint = str(endpoint or "").strip().rstrip("/").lower()
    digest = hashlib.sha256(f"{provider_slug}|{normalized_endpoint}".encode("utf-8")).hexdigest()[:16]
    return _validate_secret_name(f"ai_{provider_slug}_{digest}")


def store_secret(name: str, value: str, base_dir: Path | None = None) -> Path:
    safe_name = _validate_secret_name(name)
    secret_value = value.strip()
    if not secret_value:
        raise SecretStoreError("Secret value is empty.")
    if os.name != "nt":
        raise SecretStoreError("Protected local secret storage is available only on Windows.")

    encrypted = _protect_for_current_user(secret_value.encode("utf-8"))
    target = secret_file_path(safe_name, base_dir=base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": STORE_SCHEMA_VERSION,
        "provider": "windows-dpapi",
        "scope": "current-user",
        "name": safe_name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ciphertext_b64": base64.b64encode(encrypted).decode("ascii"),
    }
    _atomic_write_text(target, json.dumps(payload, indent=2, ensure_ascii=False))
    return target


def load_secret(name: str = DEFAULT_SECRET_NAME, base_dir: Path | None = None) -> str:
    safe_name = _validate_secret_name(name)
    path = secret_file_path(safe_name, base_dir=base_dir)
    if not path.exists():
        return ""
    if os.name != "nt":
        raise SecretStoreError("Protected local secret storage is available only on Windows.")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SecretStoreError(f"Could not read protected secret file: {path}") from exc
    if not isinstance(payload, dict):
        raise SecretStoreError("Protected secret file is not a JSON object.")
    if payload.get("provider") != "windows-dpapi":
        raise SecretStoreError(f"Unsupported secret provider: {payload.get('provider')}")
    ciphertext = str(payload.get("ciphertext_b64") or "").strip()
    if not ciphertext:
        raise SecretStoreError("Protected secret file is missing ciphertext.")
    try:
        encrypted = base64.b64decode(ciphertext, validate=True)
        return _unprotect_for_current_user(encrypted).decode("utf-8")
    except Exception as exc:
        raise SecretStoreError("Could not decrypt protected secret for the current Windows user.") from exc


def delete_secret(name: str = DEFAULT_SECRET_NAME, base_dir: Path | None = None) -> bool:
    path = secret_file_path(name, base_dir=base_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def has_secret(name: str = DEFAULT_SECRET_NAME, base_dir: Path | None = None) -> bool:
    return secret_file_path(name, base_dir=base_dir).exists()


def _validate_secret_name(name: str) -> str:
    safe_name = str(name or "").strip()
    if not SECRET_NAME_PATTERN.fullmatch(safe_name):
        raise SecretStoreError("Secret name must contain only letters, digits, dot, underscore, or hyphen.")
    return safe_name


def _protect_for_current_user(data: bytes) -> bytes:
    return _crypt_protect_data(data)


def _unprotect_for_current_user(data: bytes) -> bytes:
    return _crypt_unprotect_data(data)


def _crypt_protect_data(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, _input_buffer = _bytes_to_blob(data)
    output_blob = DATA_BLOB()
    try:
        if not crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0x01,
            ctypes.byref(output_blob),
        ):
            raise ctypes.WinError()
        return _blob_to_bytes(output_blob)
    finally:
        _free_blob(kernel32, output_blob)


def _crypt_unprotect_data(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_blob, _input_buffer = _bytes_to_blob(data)
    output_blob = DATA_BLOB()
    try:
        if not crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            0x01,
            ctypes.byref(output_blob),
        ):
            raise ctypes.WinError()
        return _blob_to_bytes(output_blob)
    finally:
        _free_blob(kernel32, output_blob)


def _bytes_to_blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.pbData or blob.cbData == 0:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _free_blob(kernel32: object, blob: DATA_BLOB) -> None:
    if blob.pbData:
        kernel32.LocalFree(blob.pbData)


def _atomic_write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
