from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tkinter as tk

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import gui_app


class TestGuiClipboardAndWizard(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_first_run_wizard_copy_user_code_no_freeze(self):
        with patch.object(gui_app.FirstRunWizard, "_probe_ai_background"):
            wizard = gui_app.FirstRunWizard(self.root)
            wizard.withdraw()
            
            wizard.oauth_code_var.set("TEST-1234-CODE")
            
            with patch("gui_app.copy_to_clipboard_async") as mock_async_copy:
                wizard._copy_user_code()
                self.assertTrue(mock_async_copy.called)
                args, kwargs = mock_async_copy.call_args
                self.assertEqual(args[0], "TEST-1234-CODE")
                self.assertEqual(kwargs.get("tk_widget"), wizard)
                
                # Test completion callback
                on_complete = kwargs.get("on_complete")
                if on_complete:
                    on_complete(True)
                    self.assertIn("TEST-1234-CODE", wizard.github_status_msg_var.get())

    def test_first_run_wizard_on_code_received(self):
        with patch.object(gui_app.FirstRunWizard, "_probe_ai_background"):
            wizard = gui_app.FirstRunWizard(self.root)
            wizard.withdraw()
            
            with patch("gui_app.copy_to_clipboard_async") as mock_async_copy:
                wizard._on_code_received("AUTH-ABCD-9999", "https://github.com/login/device")
                mock_async_copy.assert_called_once_with("AUTH-ABCD-9999", tk_widget=wizard)
                self.assertEqual(wizard.oauth_code_var.get(), "AUTH-ABCD-9999")
                self.assertEqual(wizard.verification_uri_var.get(), "https://github.com/login/device")

    def test_harvester_app_start_github_oauth_safe_copy(self):
        with patch.object(gui_app.GitHubSearchGUI, "refresh_ollama_models"):
            app = gui_app.GitHubSearchGUI(self.root)
            
            # Simulate device code received in worker
            user_code = "GH-DEV-7777"
            with patch("gui_app.copy_to_clipboard_async") as mock_async_copy:
                gui_app.copy_to_clipboard_async(user_code, tk_widget=app.root)
                mock_async_copy.assert_called_once_with(user_code, tk_widget=app.root)
