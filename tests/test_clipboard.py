from __future__ import annotations

import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from github_harvester.clipboard import (
    _get_clipboard_win32,
    _set_clipboard_win32,
    _init_win32_bindings,
    copy_to_clipboard_async,
    safe_copy_to_clipboard,
)


def test_win32_clipboard_copy_and_read():
    if os.name != "nt":
        pytest.skip("Win32 clipboard test requires Windows")

    test_text = "GitHub-Harvester-Win32-Test-12345-✨"
    success = _set_clipboard_win32(test_text)
    assert success is True

    read_back = _get_clipboard_win32()
    assert read_back == test_text


def test_safe_copy_to_clipboard_windows():
    test_text = "Safe-Copy-Test-Code-9999"
    success = safe_copy_to_clipboard(test_text)
    assert success is True

    if os.name == "nt":
        assert _get_clipboard_win32() == test_text


def test_safe_copy_fallback_on_win32_error():
    mock_widget = MagicMock()
    with patch("github_harvester.clipboard._set_clipboard_win32", return_value=False):
        success = safe_copy_to_clipboard("Fallback-Code", tk_widget=mock_widget)
        assert success is True
        mock_widget.clipboard_clear.assert_called_once()
        mock_widget.clipboard_append.assert_called_once_with("Fallback-Code")


def test_safe_copy_handles_all_exceptions():
    mock_widget = MagicMock()
    mock_widget.clipboard_clear.side_effect = RuntimeError("Tk clipboard failure")
    with patch("github_harvester.clipboard._set_clipboard_win32", return_value=False):
        success = safe_copy_to_clipboard("Fail-Code", tk_widget=mock_widget)
        assert success is False


def test_safe_copy_background_thread_fallback():
    mock_widget = MagicMock()
    result = []

    def _worker():
        with patch("github_harvester.clipboard._set_clipboard_win32", return_value=False):
            res = safe_copy_to_clipboard("Bg-Fallback-Code", tk_widget=mock_widget)
            result.append(res)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    assert result == [True]
    mock_widget.after.assert_called_once()


def test_copy_to_clipboard_async():
    test_text = "Async-Clipboard-Test-5678"
    callback_called = threading.Event()
    result_holder = []

    def on_complete(res: bool):
        result_holder.append(res)
        callback_called.set()

    thread = copy_to_clipboard_async(test_text, on_complete=on_complete)
    assert thread.is_alive() or callback_called.is_set()

    assert callback_called.wait(timeout=2.0)
    assert len(result_holder) == 1
    assert result_holder[0] is True


def test_win32_bindings_initialization():
    if os.name == "nt":
        libs = _init_win32_bindings()
        assert libs is not None
        user32, kernel32 = libs
        assert hasattr(user32, "OpenClipboard")
        assert hasattr(kernel32, "GlobalAlloc")
