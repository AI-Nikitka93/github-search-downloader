from __future__ import annotations

import sys
import unittest
from pathlib import Path
import tkinter as tk
from tkinter import ttk

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import gui_app
from github_harvester.ui_components import (
    UIColors,
    CardFrame,
    HeroSearchBar,
    PillBadge,
    AccentButton,
    ModernTreeview,
)


class TestGuiTabMainAndEdgeCases(unittest.TestCase):
    def setUp(self):
        self._orig_refresh = gui_app.GitHubSearchGUI.refresh_ollama_models
        self._orig_onboard = gui_app.GitHubSearchGUI._check_and_show_onboarding
        self._orig_update = gui_app.GitHubSearchGUI._start_background_update_check
        gui_app.GitHubSearchGUI.refresh_ollama_models = lambda self: None
        gui_app.GitHubSearchGUI._check_and_show_onboarding = lambda self: None
        gui_app.GitHubSearchGUI._start_background_update_check = lambda self: None
        
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = gui_app.GitHubSearchGUI(self.root)
        self.app.query_var.set("")
        self.app.ai_task_text.delete("1.0", "end")

    def tearDown(self):
        for after_attr in ("_onboard_after_id", "_update_after_id", "_animation_after_id"):
            after_id = getattr(self.app, after_attr, None)
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
        try:
            self.root.destroy()
        except Exception:
            pass
        gui_app.GitHubSearchGUI.refresh_ollama_models = self._orig_refresh
        gui_app.GitHubSearchGUI._check_and_show_onboarding = self._orig_onboard
        gui_app.GitHubSearchGUI._start_background_update_check = self._orig_update

    # -------------------------------------------------------------
    # 1. _append_tag_to_search Verification & Edge Cases
    # -------------------------------------------------------------
    def test_append_tag_stars(self):
        self.app._append_tag_to_search("stars:>500")
        self.assertEqual(self.app.query_var.get(), "stars:>500")

        # Duplicate stars tag should not duplicate
        self.app._append_tag_to_search("stars:>1000")
        self.assertEqual(self.app.query_var.get(), "stars:>500")

        # Stars tag with existing query
        self.app.query_var.set("python fastapi")
        self.app._append_tag_to_search("stars:>500")
        self.assertEqual(self.app.query_var.get(), "python fastapi stars:>500")

    def test_append_tag_regular_and_emojis(self):
        self.app._append_tag_to_search("Python")
        self.assertIn("Python", self.app.ai_task_text.get("1.0", "end-1c"))
        self.assertEqual(self.app.query_var.get(), "python")

        self.app._append_tag_to_search("🤖 AI/LLM")
        ai_text = self.app.ai_task_text.get("1.0", "end-1c")
        self.assertIn("🤖 AI/LLM", ai_text)
        query = self.app.query_var.get()
        self.assertTrue("ai/llm" in query or "python" in query)

        # Duplicate tag should not duplicate in query_var
        self.app._append_tag_to_search("Python")
        self.assertEqual(self.app.query_var.get().count("python"), 1)

    def test_append_tag_preset_chips(self):
        preset_tags = [
            ("🤖 AI/LLM", "AI LLM agent"),
            ("🐍 Python", "Python"),
            ("🛡 OSINT", "OSINT security"),
            ("⭐ >500", "stars:>500"),
            ("🔥 Trending", "trending"),
            ("⚡ FastAPI", "FastAPI"),
            ("🦀 Rust", "Rust"),
        ]
        for label, tag_val in preset_tags:
            self.app._append_tag_to_search(tag_val)

        q = self.app.query_var.get()
        ai = self.app.ai_task_text.get("1.0", "end-1c")
        self.assertIn("stars:>500", q)
        self.assertIn("fastapi", q)
        self.assertIn("rust", q)
        self.assertIn("OSINT security", ai)

    def test_append_tag_edge_cases(self):
        edge_cases = [
            "",
            "   ",
            "   \n\t  ",
            "🤖",
            "🦀",
            "🔥",
            "⭐",
            "C++",
            "C#",
            "a" * 200,
            "'; DROP TABLE repos; --",
            "<script>alert('xss')</script>",
            "query with spaces and \n newlines",
            "  stars:>500  ",
            "stars:   ",
        ]
        for tag in edge_cases:
            try:
                self.app._append_tag_to_search(tag)
            except Exception as e:
                self.fail(f"_append_tag_to_search crashed on input '{tag}': {e}")

    # -------------------------------------------------------------
    # 2. Main Tab Widgets Verification
    # -------------------------------------------------------------
    def test_tab_main_widgets_exist_and_functional(self):
        self.assertTrue(hasattr(self.app, "ai_task_text"))
        self.assertTrue(hasattr(self.app, "query_var"))
        self.assertTrue(hasattr(self.app, "search_profile_var"))
        self.assertTrue(hasattr(self.app, "max_repos_var"))
        self.assertTrue(hasattr(self.app, "max_age_years_var"))
        self.assertTrue(hasattr(self.app, "min_stars_var"))
        self.assertTrue(hasattr(self.app, "export_csv_var"))
        self.assertTrue(hasattr(self.app, "export_ai_ready_var"))

        # Verify profile switching
        for profile_name in gui_app.SEARCH_PROFILES.keys():
            self.app.search_profile_var.set(profile_name)
            self.app.apply_selected_profile(notify=False)
            self.assertTrue(len(str(self.app.max_repos_var.get())) > 0)
            self.assertTrue(len(str(self.app.min_stars_var.get())) > 0)

    # -------------------------------------------------------------
    # 3. Header Status Widget Verification
    # -------------------------------------------------------------
    def test_header_status_widget_updates(self):
        widget = self.app.status_pill_widget
        self.assertIsNotNone(widget)

        # Anonymous GitHub
        widget.update_github(None, 60, 60)
        self.assertIn("Анонимный", widget.github_text_var.get())

        # Authenticated GitHub
        widget.update_github("octocat", 4950, 5000)
        self.assertIn("@octocat", widget.github_text_var.get())

        # AI updates
        widget.update_ai("Ollama", "qwen2.5-coder:7b", ready=True)
        self.assertIn("🟢", widget.ai_text_var.get())
        widget.update_ai("Ollama", "qwen2.5-coder:7b", ready=False)
        self.assertIn("⚪", widget.ai_text_var.get())

        # Disk updates
        widget.update_disk(Path("C:/"))
        self.assertIn("GB свободно", widget.disk_text_var.get())

        # Disk update on invalid path
        widget.update_disk(Path("Z:/NonExistentPath_XYZ_12345/SubDir"))
        self.assertTrue(len(widget.disk_text_var.get()) > 0)

    # -------------------------------------------------------------
    # 4. Theme Toggle Verification
    # -------------------------------------------------------------
    def test_theme_toggle_stability(self):
        self.app._toggle_theme()
        self.app.root.update_idletasks()
        self.app._toggle_theme()
        self.app.root.update_idletasks()


if __name__ == "__main__":
    unittest.main()
