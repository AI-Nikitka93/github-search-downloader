from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class TestReleasePackaging(unittest.TestCase):
    _dist_dir: Path
    _exe_path: Path
    _created_dummy_exe: bool = False

    @classmethod
    def setUpClass(cls) -> None:
        cls._dist_dir = ROOT_DIR / "dist"
        cls._dist_dir.mkdir(exist_ok=True)
        cls._exe_path = cls._dist_dir / "GithubSearchDownloader.exe"
        if not cls._exe_path.exists():
            cls._exe_path.write_bytes(b"MZ dummy executable header for packaging unit tests\x00" * 32)
            cls._created_dummy_exe = True

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._created_dummy_exe and cls._exe_path.exists():
            try:
                cls._exe_path.unlink()
            except Exception:
                pass

    def test_readme_uses_current_project_path(self) -> None:
        readme = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn(r"M:\Projects\Programs\GithubSearch", readme)
        self.assertNotIn(r"M:\Projects\GithubSearch", readme)

    def test_release_artifacts_include_license_file(self) -> None:
        license_path = ROOT_DIR / "LICENSE.txt"
        self.assertTrue(license_path.exists(), "release should include a LICENSE.txt file")
        license_text = license_path.read_text(encoding="utf-8")
        self.assertIn("All rights reserved", license_text)

        release_script = (ROOT_DIR / "release_windows.ps1").read_text(encoding="utf-8")
        verifier_script = (ROOT_DIR / "verify_release_windows.ps1").read_text(encoding="utf-8")
        pyproject = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("LICENSE.txt", release_script)
        self.assertIn("LICENSE.txt", verifier_script)
        self.assertIn('license-files = ["LICENSE.txt"]', pyproject)

    def test_release_script_declares_public_distribution_gates(self) -> None:
        script_path = ROOT_DIR / "release_windows.ps1"
        self.assertTrue(script_path.exists(), "release_windows.ps1 should exist")
        script = script_path.read_text(encoding="utf-8")
        for expected in (
            "Get-AuthenticodeSignature",
            "System.Security.Cryptography.SHA256",
            "Compress-Archive",
            "release_manifest.json",
            "update_manifest.json",
            "verify_release_windows.ps1",
            "SHA256SUMS.txt",
            "RequireSignature",
            "SignTool",
            "UpdateBaseUrl",
            "install_windows.ps1",
            "uninstall_windows.ps1",
            "check_updates_windows.ps1",
            "uninstall_registry_key",
            "Set-InstallerVersion",
            "$ProductVersion = `\"$ReleaseVersion`\"",
        ):
            self.assertIn(expected, script)

    def test_release_script_stamps_installer_version_from_release_version(self) -> None:
        script_path = ROOT_DIR / "release_windows.ps1"
        smoke_root = ROOT_DIR / "_smoke_output"
        smoke_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="release-version-test-", dir=smoke_root) as temp_dir:
            output_dir = Path(temp_dir) / "release"
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-SkipBuild",
                    "-Version",
                    "9.8.7",
                    "-OutputDir",
                    str(output_dir),
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            staged_installer = output_dir / "GithubSearchDownloader-9.8.7-windows-x64" / "install_windows.ps1"
            self.assertTrue(staged_installer.exists(), "staged installer should exist")
            self.assertIn('$ProductVersion = "9.8.7"', staged_installer.read_text(encoding="utf-8"))

            update_manifest = json.loads((output_dir / "update_manifest.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(update_manifest["latest_version"], "9.8.7")

    def test_release_script_writes_hosted_update_channel_config(self) -> None:
        script_path = ROOT_DIR / "release_windows.ps1"
        smoke_root = ROOT_DIR / "_smoke_output"
        smoke_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="release-channel-test-", dir=smoke_root) as temp_dir:
            output_dir = Path(temp_dir) / "release"
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-SkipBuild",
                    "-Version",
                    "9.8.6",
                    "-OutputDir",
                    str(output_dir),
                    "-UpdateBaseUrl",
                    "https://updates.example.com/github-search-downloader",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            release_name = "GithubSearchDownloader-9.8.6-windows-x64"
            update_channel_path = output_dir / release_name / "update_channel.json"
            self.assertTrue(update_channel_path.exists(), "hosted release should stage update_channel.json")
            update_channel = json.loads(update_channel_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(update_channel["product"], "GithubSearchDownloader")
            self.assertEqual(update_channel["latest_version"], "9.8.6")
            self.assertEqual(
                update_channel["update_manifest_url"],
                "https://updates.example.com/github-search-downloader/update_manifest.json",
            )

            update_manifest = json.loads((output_dir / "update_manifest.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(
                update_manifest["download_url"],
                "https://updates.example.com/github-search-downloader/GithubSearchDownloader-9.8.6-windows-x64.zip",
            )
            with zipfile.ZipFile(output_dir / f"{release_name}.zip") as archive:
                self.assertIn("update_channel.json", archive.namelist())

    def test_release_script_parses_as_powershell(self) -> None:
        script_path = ROOT_DIR / "release_windows.ps1"
        command = (
            "$null = [scriptblock]::Create((Get-Content -Raw "
            f"'{script_path.as_posix()}')); 'parse-ok'"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("parse-ok", result.stdout)

    def test_release_verifier_declares_integrity_and_signature_checks(self) -> None:
        script_path = ROOT_DIR / "verify_release_windows.ps1"
        self.assertTrue(script_path.exists(), "verify_release_windows.ps1 should exist")
        script = script_path.read_text(encoding="utf-8")
        for expected in (
            "release_manifest.json",
            "update_manifest.json",
            "SHA256SUMS.txt",
            "System.Security.Cryptography.SHA256",
            "Get-AuthenticodeSignature",
            "Get-ReleaseSignature",
            "System.IO.Compression.ZipFile",
            "RequireSignature",
            "RequireHostedUpdateUrl",
        ):
            self.assertIn(expected, script)

    def test_release_verifier_runs_in_automation_host_without_required_signature(self) -> None:
        script_path = ROOT_DIR / "verify_release_windows.ps1"
        manifest_path = ROOT_DIR / "release" / "release_manifest.json"
        test_version = "1.0.1"
        if not manifest_path.exists():
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT_DIR / "release_windows.ps1"),
                    "-SkipBuild",
                    "-Version",
                    "1.0.1",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        else:
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                test_version = manifest_data.get("version", "1.0.1")
            except Exception as e:
                test_version = "1.0.1"

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-Version",
                test_version,
            ],
            cwd=ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release verification OK", result.stdout)

        strict_result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-Version",
                test_version,
                "-RequireSignature",
            ],
            cwd=ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(strict_result.returncode, 0)
        self.assertIn("Signature gate failed", strict_result.stdout + strict_result.stderr)

    def test_distribution_scripts_parse_as_powershell(self) -> None:
        for relative_path in (
            "packaging/install_windows.ps1",
            "packaging/uninstall_windows.ps1",
            "packaging/check_updates_windows.ps1",
            "verify_release_windows.ps1",
        ):
            script_path = ROOT_DIR / relative_path
            self.assertTrue(script_path.exists(), f"{relative_path} should exist")
            command = (
                "$null = [scriptblock]::Create((Get-Content -Raw "
                f"'{script_path.as_posix()}')); 'parse-ok'"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("parse-ok", result.stdout)

    def test_update_checker_declares_safe_download_and_install_flow(self) -> None:
        script_path = ROOT_DIR / "packaging" / "check_updates_windows.ps1"
        self.assertTrue(script_path.exists(), "check_updates_windows.ps1 should exist")
        script = script_path.read_text(encoding="utf-8")
        for expected in (
            "Invoke-WebRequest",
            "Expand-Archive",
            "System.Security.Cryptography.SHA256",
            "Get-AuthenticodeSignature",
            "Get-ReleaseSignature",
            "latest_version",
            "download_url",
            "package_sha256",
            "Compare-Version",
            "DownloadOnly",
            "Install",
            "RequireSignature",
            "update_script",
            "package_size_bytes",
            ".partial",
            "System.IO.Compression.ZipFile",
            "update_channel.json",
            "update_manifest_url",
        ):
            self.assertIn(expected, script)

    def test_update_checker_uses_persisted_update_channel_when_manifest_not_passed(self) -> None:
        script_path = ROOT_DIR / "packaging" / "check_updates_windows.ps1"
        smoke_root = ROOT_DIR / "_smoke_output"
        smoke_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="update-channel-test-", dir=smoke_root) as temp_dir:
            temp_path = Path(temp_dir)
            app_dir = temp_path / "installed"
            app_dir.mkdir()
            package_dir = temp_path / "channel"
            package_dir.mkdir()
            script_copy = app_dir / "check_updates_windows.ps1"
            script_copy.write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")

            package_path = package_dir / "GithubSearchDownloader-9.9.8-windows-x64.zip"
            exe_bytes = b"fake executable for update channel fixture"
            with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("GithubSearchDownloader.exe", exe_bytes)
                archive.writestr("install_windows.ps1", "Write-Host 'install fixture'\n")
                archive.writestr("check_updates_windows.ps1", "Write-Host 'update fixture'\n")

            manifest = {
                "product": "GithubSearchDownloader",
                "latest_version": "9.9.8",
                "release_name": "GithubSearchDownloader-9.9.8-windows-x64",
                "download_url": package_path.name,
                "package_name": package_path.name,
                "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
                "package_size_bytes": package_path.stat().st_size,
                "executable_sha256": hashlib.sha256(exe_bytes).hexdigest(),
                "install_script": "install_windows.ps1",
                "update_script": "check_updates_windows.ps1",
            }
            manifest_path = package_dir / "update_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            channel = {
                "product": "GithubSearchDownloader",
                "channel": "stable",
                "latest_version": "9.9.8",
                "update_manifest_url": str(manifest_path),
            }
            (app_dir / "update_channel.json").write_text(json.dumps(channel), encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_copy),
                    "-CurrentVersion",
                    "0.0.0",
                    "-DownloadDir",
                    str(temp_path / "downloads"),
                    "-DownloadOnly",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["downloaded"])
            self.assertEqual(payload["manifest_source"], str(manifest_path))
            self.assertEqual(payload["message"], "Update package downloaded and verified.")

    def test_update_checker_runs_in_automation_host_without_required_signature(self) -> None:
        script_path = ROOT_DIR / "packaging" / "check_updates_windows.ps1"
        if not (ROOT_DIR / "release" / "update_manifest.json").exists():
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ROOT_DIR / "release_windows.ps1"),
                    "-SkipBuild",
                    "-Version",
                    "1.0.1",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        smoke_root = ROOT_DIR / "_smoke_output"
        smoke_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="update-automation-test-", dir=smoke_root) as temp_dir:
            temp_path = Path(temp_dir)
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-UpdateManifest",
                    str(ROOT_DIR / "release" / "update_manifest.json"),
                    "-CurrentVersion",
                    "0.9.0",
                    "-DownloadDir",
                    str(temp_path / "downloads"),
                    "-DownloadOnly",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["downloaded"])
            self.assertEqual(payload["message"], "Update package downloaded and verified.")
            self.assertIn(payload["signature_status"], {"NotSigned", "Unavailable"})

            strict_result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-UpdateManifest",
                    str(ROOT_DIR / "release" / "update_manifest.json"),
                    "-CurrentVersion",
                    "0.9.0",
                    "-DownloadDir",
                    str(temp_path / "strict-downloads"),
                    "-DownloadOnly",
                    "-RequireSignature",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(strict_result.returncode, 0)
            self.assertIn("Update package signature gate failed", strict_result.stdout + strict_result.stderr)

    def test_update_checker_rejects_package_size_mismatch(self) -> None:
        script_path = ROOT_DIR / "packaging" / "check_updates_windows.ps1"
        smoke_root = ROOT_DIR / "_smoke_output"
        smoke_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="update-size-test-", dir=smoke_root) as temp_dir:
            temp_path = Path(temp_dir)
            package_path = temp_path / "GithubSearchDownloader-9.9.9-windows-x64.zip"
            exe_bytes = b"not a real executable, only a hash fixture"
            with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("GithubSearchDownloader.exe", exe_bytes)
                archive.writestr("install_windows.ps1", "Write-Host 'install fixture'\n")
                archive.writestr("check_updates_windows.ps1", "Write-Host 'update fixture'\n")

            manifest = {
                "product": "GithubSearchDownloader",
                "latest_version": "9.9.9",
                "release_name": "GithubSearchDownloader-9.9.9-windows-x64",
                "download_url": package_path.name,
                "package_name": package_path.name,
                "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
                "package_size_bytes": package_path.stat().st_size + 1,
                "executable_sha256": hashlib.sha256(exe_bytes).hexdigest(),
                "install_script": "install_windows.ps1",
                "update_script": "check_updates_windows.ps1",
            }
            manifest_path = temp_path / "update_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-UpdateManifest",
                    str(manifest_path),
                    "-CurrentVersion",
                    "0.0.0",
                    "-DownloadDir",
                    str(temp_path / "downloads"),
                    "-DownloadOnly",
                ],
                cwd=ROOT_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Package size mismatch", result.stdout + result.stderr)

    def test_installer_registers_per_user_uninstall_entry(self) -> None:
        script_path = ROOT_DIR / "packaging" / "install_windows.ps1"
        script = script_path.read_text(encoding="utf-8")
        for expected in (
            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\GithubSearchDownloader",
            "DisplayName",
            "DisplayVersion",
            "InstallLocation",
            "UninstallString",
            "QuietUninstallString",
            "EstimatedSize",
            "uninstall_registry_key",
            "update_channel.json",
            "LICENSE.txt",
            "Uninstall GitHub Search Downloader.lnk",
            "uninstaller_shortcut",
        ):
            self.assertIn(expected, script)

    def test_uninstaller_removes_per_user_uninstall_entry(self) -> None:
        script_path = ROOT_DIR / "packaging" / "uninstall_windows.ps1"
        script = script_path.read_text(encoding="utf-8")
        for expected in (
            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\GithubSearchDownloader",
            "Remove-Item",
            "uninstall registry",
            "PurgeUserData",
        ):
            self.assertIn(expected, script)

    def test_uninstaller_requires_product_markers_before_recursive_delete(self) -> None:
        script_path = ROOT_DIR / "packaging" / "uninstall_windows.ps1"
        script = script_path.read_text(encoding="utf-8")
        for expected in (
            "Assert-ProductInstallDirectory",
            "install_manifest.json",
            "GithubSearchDownloader.exe",
            "Refusing to remove install directory without GithubSearchDownloader product markers",
        ):
            self.assertIn(expected, script)

    def test_packaging_and_spec_include_icon_and_assets(self) -> None:
        build_script = (ROOT_DIR / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("icon.ico", build_script)
        self.assertIn("assets", build_script)

        installer_path = ROOT_DIR / "packaging" / "install_windows.ps1"
        self.assertTrue(installer_path.exists(), "install_windows.ps1 should exist")
        installer_content = installer_path.read_text(encoding="utf-8")
        self.assertIn("assets", installer_content)
        self.assertIn("icon.ico", installer_content)


if __name__ == "__main__":
    unittest.main()
