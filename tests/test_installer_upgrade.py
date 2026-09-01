from __future__ import annotations

import ctypes
import os
import subprocess
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


class TestInstallerUpgradeArchitecture(unittest.TestCase):
    def setUp(self) -> None:
        self.installer_iss = ROOT_DIR / "packaging" / "installer.iss"
        self.install_ps1 = ROOT_DIR / "packaging" / "install_windows.ps1"
        self.uninstall_ps1 = ROOT_DIR / "packaging" / "uninstall_windows.ps1"
        self.gui_app_py = ROOT_DIR / "gui_app.py"

    def test_installer_iss_declares_upgrade_and_mutex_directives(self) -> None:
        self.assertTrue(self.installer_iss.exists(), "installer.iss must exist")
        iss_content = self.installer_iss.read_text(encoding="utf-8")

        required_directives = [
            "AppId={{D3F76A0C-82B1-4F48-97F2-8A74902F1C6E}",
            "AppMutex=GithubSearchDownloaderAppMutex",
            "CloseApplications=force",
            "CloseApplicationsFilter=GithubSearchDownloader.exe",
            "RestartApplications=no",
            "UsePreviousAppDir=yes",
            "DisableDirPage=auto",
            "DirExistsWarning=no",
            "CreateUninstallRegKey=yes",
            "UpdateUninstallLogAppName=yes",
            "Flags: ignoreversion restartreplace",
            "[InstallDelete]",
        ]
        for directive in required_directives:
            self.assertIn(directive, iss_content, f"Missing required directive: {directive}")

    def test_installer_iss_code_section_handles_process_and_registry_cleanup(self) -> None:
        iss_content = self.installer_iss.read_text(encoding="utf-8")

        required_code_elements = [
            "function IsAppProcessRunning(): Boolean;",
            "function TerminateAppProcess(): Boolean;",
            "function InitializeSetup(): Boolean;",
            "function PrepareToInstall(var NeedsRestart: Boolean): String;",
            "procedure CurStepChanged(CurStep: TSetupStep);",
            "CheckForMutexes",
            "taskkill.exe",
            "LegacyUninstallKey",
            "RegDeleteKeyIncludingSubkeys",
        ]
        for element in required_code_elements:
            self.assertIn(element, iss_content, f"Missing code element: {element}")

    def test_installer_iss_compiles_cleanly_with_iscc(self) -> None:
        iscc_candidates = [
            Path(r"C:\Users\admin\AppData\Local\Programs\Antigravity IDE\resources\app\node_modules\innosetup\bin\ISCC.exe"),
            Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        ]
        iscc_exe = None
        for cand in iscc_candidates:
            if cand.exists():
                iscc_exe = cand
                break

        if not iscc_exe:
            self.skipTest("ISCC compiler not found in standard paths.")

        dist_exe = ROOT_DIR / "dist" / "GithubSearchDownloader.exe"
        created_dummy = False
        if not dist_exe.exists():
            dist_exe.parent.mkdir(parents=True, exist_ok=True)
            dist_exe.write_bytes(b"MZ dummy executable for Inno Setup test" * 64)
            created_dummy = True

        try:
            result = subprocess.run(
                [str(iscc_exe), str(self.installer_iss)],
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"ISCC compilation failed: {result.stdout}\n{result.stderr}")
            self.assertIn("Successful compile", result.stdout)
        finally:
            if created_dummy and dist_exe.exists():
                try:
                    dist_exe.unlink()
                except Exception:
                    pass

    def test_gui_app_has_named_mutex_implementation(self) -> None:
        self.assertTrue(self.gui_app_py.exists(), "gui_app.py must exist")
        app_content = self.gui_app_py.read_text(encoding="utf-8")

        self.assertIn("APP_MUTEX_NAME = \"GithubSearchDownloaderAppMutex\"", app_content)
        self.assertIn("def acquire_app_mutex(", app_content)
        self.assertIn("def release_app_mutex(", app_content)
        self.assertIn("def activate_existing_instance(", app_content)

    def test_named_mutex_single_instance_detection(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows Named Mutex test only runs on Windows (nt)")

        import gui_app

        test_mutex_name = f"TestGithubSearchDownloaderAppMutex_{os.getpid()}"
        acquired_first = gui_app.acquire_app_mutex(test_mutex_name)
        self.assertTrue(acquired_first, "First mutex acquisition should succeed")

        # Second acquisition of the exact same mutex in another call
        kernel32 = ctypes.windll.kernel32
        h2 = kernel32.CreateMutexW(None, False, test_mutex_name)
        last_error = kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        self.assertEqual(last_error, ERROR_ALREADY_EXISTS, "Second mutex check should report ERROR_ALREADY_EXISTS")
        if h2:
            kernel32.CloseHandle(h2)

        gui_app.release_app_mutex()

    def test_install_and_uninstall_scripts_handle_process_safety(self) -> None:
        install_text = self.install_ps1.read_text(encoding="utf-8")
        self.assertIn("Get-CimInstance Win32_Process", install_text)
        self.assertIn("Stop-Process", install_text)

        uninstall_text = self.uninstall_ps1.read_text(encoding="utf-8")
        self.assertIn("Get-CimInstance Win32_Process", uninstall_text)
        self.assertIn("Close GithubSearchDownloader.exe before uninstalling", uninstall_text)

    def test_activate_existing_instance_invoked_safely(self) -> None:
        import gui_app

        # Should execute cleanly without throwing unhandled exceptions
        gui_app.activate_existing_instance()

    def test_inno_setup_icons_section_declares_shortcuts_and_uninstaller(self) -> None:
        iss_content = self.installer_iss.read_text(encoding="utf-8")
        self.assertIn('Name: "{group}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"', iss_content)
        self.assertIn('Name: "{group}\\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"', iss_content)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"', iss_content)

    def test_install_script_creates_start_menu_uninstaller_and_desktop_shortcuts(self) -> None:
        install_text = self.install_ps1.read_text(encoding="utf-8")
        self.assertIn("Uninstall GitHub Search Downloader.lnk", install_text)
        self.assertIn("uninstaller_shortcut", install_text)
        self.assertIn("New-AppShortcut", install_text)
        self.assertIn("powershell.exe", install_text)
        self.assertIn("uninstall_windows.ps1", install_text)

    def test_uninstaller_script_handles_purge_user_data_and_removes_shortcuts(self) -> None:
        uninstall_text = self.uninstall_ps1.read_text(encoding="utf-8")
        self.assertIn("[switch]$PurgeUserData", uninstall_text)
        self.assertIn("Purging user data and secrets", uninstall_text)
        self.assertIn("StartMenuDir", uninstall_text)
        self.assertIn("DesktopShortcut", uninstall_text)
        self.assertIn("UninstallRegistryKey", uninstall_text)
        self.assertIn("LOCALAPPDATA", uninstall_text)
        self.assertIn("APPDATA", uninstall_text)

    def test_app_paths_separate_program_binaries_from_user_secrets(self) -> None:
        from github_harvester.secret_store import default_secret_dir

        secret_dir = default_secret_dir()
        secret_str = str(secret_dir).lower()

        # User secrets must be under %LOCALAPPDATA%\GithubSearchDownloader\secrets
        self.assertTrue(secret_str.endswith(r"githubsearchdownloader\secrets"))
        # Program binaries are installed to %LOCALAPPDATA%\Programs\GithubSearchDownloader
        self.assertNotIn(r"programs\githubsearchdownloader\secrets", secret_str)


if __name__ == "__main__":
    unittest.main()
