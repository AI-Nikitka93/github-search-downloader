"""Robust, freeze-proof Windows clipboard implementation using native Win32 API and ctypes.

Eliminates UI deadlocks caused by synchronous clip.exe subprocess calls, 64-bit ctypes handle
truncation, and Tkinter clipboard lock contention.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# Win32 Clipboard Formats and Global Memory Flags
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040

_WIN32_LIBS: Optional[Tuple[Any, Any]] = None
_WIN32_INIT_ATTEMPTED = False


def _init_win32_bindings() -> Optional[Tuple[Any, Any]]:
    """Initializes and caches 64-bit/32-bit type-safe Win32 API bindings."""
    global _WIN32_LIBS, _WIN32_INIT_ATTEMPTED
    if _WIN32_INIT_ATTEMPTED:
        return _WIN32_LIBS

    _WIN32_INIT_ATTEMPTED = True
    if os.name != "nt" or sys.platform != "win32":
        return None

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # kernel32 64-bit safe signatures
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p

        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL

        # user32 64-bit safe signatures
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL

        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL

        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE

        user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

        _WIN32_LIBS = (user32, kernel32)
        return _WIN32_LIBS
    except Exception as exc:
        logger.debug(f"Failed to initialize Win32 clipboard bindings: {exc}")
        return None


def _set_clipboard_win32(text: str, retries: int = 10, retry_delay: float = 0.025) -> bool:
    """Copies text to the Windows OS clipboard directly via native Win32 API.

    Zero subprocess overhead, zero pipe hangs, 64-bit type safe, handles transient locks gracefully.
    """
    libs = _init_win32_bindings()
    if not libs:
        return False

    user32, kernel32 = libs

    if not isinstance(text, str):
        text = str(text)

    encoded = (text + "\0").encode("utf-16-le")
    size = len(encoded)

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
    if not h_mem:
        logger.debug("GlobalAlloc failed for clipboard data")
        return False

    p_mem = kernel32.GlobalLock(h_mem)
    if not p_mem:
        kernel32.GlobalFree(h_mem)
        logger.debug("GlobalLock failed for clipboard data")
        return False

    try:
        ctypes.memmove(p_mem, encoded, size)
    finally:
        kernel32.GlobalUnlock(h_mem)

    # Retry loop in case another application (e.g. Win+V clipboard history) holds the lock
    opened = False
    for _ in range(max(1, retries)):
        if user32.OpenClipboard(0):
            opened = True
            break
        time.sleep(retry_delay)

    if not opened:
        kernel32.GlobalFree(h_mem)
        logger.debug("OpenClipboard timed out / failed to acquire clipboard lock")
        return False

    try:
        user32.EmptyClipboard()
        # On success, the OS takes ownership of h_mem (caller must NOT GlobalFree)
        res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        if not res:
            kernel32.GlobalFree(h_mem)
            logger.debug("SetClipboardData failed")
            return False
        return True
    finally:
        user32.CloseClipboard()


def _get_clipboard_win32(retries: int = 10, retry_delay: float = 0.025) -> Optional[str]:
    """Retrieves Unicode text from the Windows OS clipboard via native Win32 API."""
    libs = _init_win32_bindings()
    if not libs:
        return None

    user32, kernel32 = libs

    opened = False
    for _ in range(max(1, retries)):
        if user32.OpenClipboard(0):
            opened = True
            break
        time.sleep(retry_delay)

    if not opened:
        return None

    try:
        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_mem:
            return None
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return None
        try:
            return ctypes.wstring_at(p_mem)
        finally:
            kernel32.GlobalUnlock(h_mem)
    finally:
        user32.CloseClipboard()


def safe_copy_to_clipboard(
    text: str,
    tk_widget: Optional[Any] = None,
) -> bool:
    """Safe, freeze-proof clipboard copy.

    1. Attempts direct native Win32 API (no subprocess spawn, 64-bit safe, no deadlock).
    2. Gracefully falls back to Tkinter clipboard if on non-Windows or if Win32 fails.
    3. Guarantees thread-safety (never calls Tkinter clipboard functions directly from background threads).
    4. Never raises unhandled exceptions or blocks the GUI event loop.
    """
    if not isinstance(text, str):
        text = str(text)

    # 1. Native Windows Win32 API
    if os.name == "nt":
        try:
            if _set_clipboard_win32(text):
                return True
        except Exception as exc:
            logger.debug(f"Win32 clipboard error: {exc}")

    # 2. Tkinter fallback (if widget provided and Win32 failed or non-Windows)
    if tk_widget is not None:
        if threading.current_thread() is threading.main_thread():
            try:
                tk_widget.clipboard_clear()
                tk_widget.clipboard_append(text)
                return True
            except Exception as exc:
                logger.debug(f"Tkinter clipboard fallback error: {exc}")
        else:
            # If called from a non-main thread, dispatch to main thread safely
            try:
                if hasattr(tk_widget, "after"):
                    def _do_tk_copy():
                        try:
                            tk_widget.clipboard_clear()
                            tk_widget.clipboard_append(text)
                        except Exception as exc:
                            logger.debug(f"Tkinter thread-dispatched fallback error: {exc}")
                    tk_widget.after(0, _do_tk_copy)
                    return True
            except Exception as exc:
                logger.debug(f"Tkinter thread-dispatch error: {exc}")

    return False


def copy_to_clipboard_async(
    text: str,
    tk_widget: Optional[Any] = None,
    on_complete: Optional[Callable[[bool], None]] = None,
) -> threading.Thread:
    """Asynchronously copies text to clipboard in a background daemon thread.

    Guarantees the caller thread / UI event loop is never paused, delayed, or deadlocked.
    """
    def _worker():
        success = safe_copy_to_clipboard(text, tk_widget=None)
        if not success and tk_widget is not None:
            # Try Tk fallback on main thread
            success = safe_copy_to_clipboard(text, tk_widget=tk_widget)

        if on_complete:
            try:
                if tk_widget is not None and hasattr(tk_widget, "after"):
                    tk_widget.after(0, lambda: on_complete(success))
                else:
                    on_complete(success)
            except Exception as exc:
                logger.debug(f"Error in on_complete clipboard callback: {exc}")

    thread = threading.Thread(target=_worker, daemon=True, name="ClipboardCopyWorker")
    thread.start()
    return thread
