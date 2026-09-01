from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from github_harvester.clipboard import (
    _get_clipboard_win32,
    _set_clipboard_win32,
    copy_to_clipboard_async,
    safe_copy_to_clipboard,
)


class TestClipboard(unittest.TestCase):
    def test_win32_clipboard_copy_and_read(self):
        if os.name != "nt":
            self.skipTest("Win32 clipboard test requires Windows")

        test_text = "GitHub-Harvester-Win32-Test-12345-✨"
        success = _set_clipboard_win32(test_text)
        self.assertTrue(success)

        read_back = _get_clipboard_win32()
        self.assertEqual(read_back, test_text)

    def test_safe_copy_to_clipboard_windows(self):
        test_text = "Safe-Copy-Test-Code-9999"
        success = safe_copy_to_clipboard(test_text)
        self.assertTrue(success)

        if os.name == "nt":
            self.assertEqual(_get_clipboard_win32(), test_text)

    def test_safe_copy_fallback_on_win32_error(self):
        mock_widget = MagicMock()
        with patch("github_harvester.clipboard._set_clipboard_win32", return_value=False):
            success = safe_copy_to_clipboard("Fallback-Code", tk_widget=mock_widget)
            self.assertTrue(success)
            mock_widget.clipboard_clear.assert_called_once()
            mock_widget.clipboard_append.assert_called_once_with("Fallback-Code")

    def test_safe_copy_handles_all_exceptions(self):
        mock_widget = MagicMock()
        mock_widget.clipboard_clear.side_effect = RuntimeError("Tk clipboard failure")
        with patch("github_harvester.clipboard._set_clipboard_win32", return_value=False):
            success = safe_copy_to_clipboard("Fail-Code", tk_widget=mock_widget)
            self.assertFalse(success)

    def test_safe_copy_background_thread_fallback(self):
        mock_widget = MagicMock()
        result = []

        def worker():
            with patch("github_harvester.clipboard._set_clipboard_win32", return_value=False):
                res = safe_copy_to_clipboard("Thread-Code", tk_widget=mock_widget)
                result.append(res)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertTrue(result[0])
        mock_widget.after.assert_called_once()

    def test_async_clipboard_worker(self):
        callback_called = threading.Event()
        callback_result = []

        def on_done(success: bool):
            callback_result.append(success)
            callback_called.set()

        copy_to_clipboard_async("Async-Test-Code", on_complete=on_done)
        self.assertTrue(callback_called.wait(timeout=3.0))
        self.assertTrue(callback_result[0])


if __name__ == "__main__":
    unittest.main()
