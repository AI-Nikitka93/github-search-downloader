from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import gui_app


class TestGuiProfiles(unittest.TestCase):
    def test_ai_provider_profiles_include_runtime_generation_options(self) -> None:
        profiles = gui_app.AI_PROVIDER_PROFILES
        self.assertIn("DeepSeek", profiles)
        self.assertIn("Ollama (Локально)", profiles)
        for profile in profiles.values():
            self.assertIn(profile["provider_type"], {"ollama", "openai-compatible"})
            self.assertTrue(str(profile["endpoint"]).startswith("http"))
            self.assertTrue(str(profile["model"]).strip())
            self.assertGreaterEqual(int(profile["timeout"]), 5)
            self.assertIn("temperature", profile)
            self.assertIn("num_ctx", profile)
            self.assertIn("num_predict", profile)

    def test_gui_applies_ai_provider_profile_to_run_config(self) -> None:
        import tkinter as tk

        original_refresh = gui_app.GitHubSearchGUI.refresh_ollama_models
        gui_app.GitHubSearchGUI.refresh_ollama_models = lambda self: None
        root = tk.Tk()
        root.withdraw()
        try:
            app = gui_app.GitHubSearchGUI(root)
            app.query_var.set("ai agents")
            app.output_var.set(str(ROOT_DIR / "_smoke_output" / "gui_profile_test"))
            app.ai_provider_profile_var.set("DeepSeek")
            app.deep_relevance_var.set(True)
            app.deep_relevance_max_repos_var.set("12")
            app.deep_relevance_min_score_var.set("0.35")
            app.apply_ai_provider_profile(notify=False)
            config = app._build_config()
        finally:
            root.destroy()
            gui_app.GitHubSearchGUI.refresh_ollama_models = original_refresh

        expected = gui_app.AI_PROVIDER_PROFILES["DeepSeek"]
        self.assertEqual(config.ai_provider_type, expected["provider_type"])
        self.assertEqual(config.ai_filter_endpoint, expected["endpoint"])
        self.assertEqual(config.ai_filter_model, expected["model"])
        self.assertEqual(config.ai_filter_timeout, int(expected["timeout"]))
        self.assertEqual(config.ai_num_ctx, int(expected["num_ctx"]))
        self.assertEqual(config.ai_num_predict, int(expected["num_predict"]))
        self.assertEqual(config.ai_temperature, float(expected["temperature"]))
        self.assertTrue(config.deep_relevance_enabled)
        self.assertEqual(config.deep_relevance_max_repos, 12)
        self.assertAlmostEqual(config.deep_relevance_min_score, 0.35)

    def test_gui_uses_saved_local_github_token_when_field_and_env_are_empty(self) -> None:
        import tkinter as tk

        saved_token = "ghp_" + "b" * 36
        original_refresh = gui_app.GitHubSearchGUI.refresh_ollama_models
        original_load_secret = gui_app.load_secret
        original_has_secret = gui_app.has_secret
        old_env_token = os.environ.pop("GITHUB_TOKEN", None)
        gui_app.GitHubSearchGUI.refresh_ollama_models = lambda self: None
        gui_app.load_secret = lambda name=gui_app.DEFAULT_SECRET_NAME: saved_token
        gui_app.has_secret = lambda name=gui_app.DEFAULT_SECRET_NAME: True
        root = tk.Tk()
        root.withdraw()
        try:
            app = gui_app.GitHubSearchGUI(root)
            app.query_var.set("ai agents")
            app.output_var.set(str(ROOT_DIR / "_smoke_output" / "gui_saved_token_test"))
            app.token_var.set("")
            config = app._build_config()
        finally:
            root.destroy()
            gui_app.GitHubSearchGUI.refresh_ollama_models = original_refresh
            gui_app.load_secret = original_load_secret
            gui_app.has_secret = original_has_secret
            if old_env_token is not None:
                os.environ["GITHUB_TOKEN"] = old_env_token

        self.assertEqual(config.token, saved_token)
        self.assertEqual(app._last_token_source, "saved")

    def test_gui_uses_saved_local_ai_api_key_for_openai_compatible_provider(self) -> None:
        import tkinter as tk

        saved_key = "sk_test_saved"
        original_refresh = gui_app.GitHubSearchGUI.refresh_ollama_models
        original_load_secret = gui_app.load_secret
        original_has_secret = gui_app.has_secret
        old_openai_key = os.environ.pop("OPENAI_API_KEY", None)
        gui_app.GitHubSearchGUI.refresh_ollama_models = lambda self: None
        gui_app.load_secret = lambda name: saved_key if str(name).startswith("ai_openai-compatible_") else ""
        gui_app.has_secret = lambda name: str(name).startswith("ai_openai-compatible_")
        root = tk.Tk()
        root.withdraw()
        try:
            app = gui_app.GitHubSearchGUI(root)
            app.query_var.set("ai agents")
            app.output_var.set(str(ROOT_DIR / "_smoke_output" / "gui_saved_ai_key_test"))
            app.ai_provider_type_var.set("openai-compatible")
            app.ai_endpoint_var.set("https://api.example.com/v1")
            app.ai_model_var.set("example-model")
            app.ai_api_key_var.set("")
            app.ai_api_key_env_var.set("")
            config = app._build_config()
        finally:
            root.destroy()
            gui_app.GitHubSearchGUI.refresh_ollama_models = original_refresh
            gui_app.load_secret = original_load_secret
            gui_app.has_secret = original_has_secret
            if old_openai_key is not None:
                os.environ["OPENAI_API_KEY"] = old_openai_key

        self.assertEqual(config.ai_provider_type, "openai-compatible")
        self.assertEqual(config.ai_api_key, saved_key)
        self.assertEqual(app._last_ai_key_source, "saved")

    def test_assets_icon_files_exist_and_are_valid(self) -> None:
        from PIL import Image

        ico_path = ROOT_DIR / "assets" / "icon.ico"
        png_path = ROOT_DIR / "assets" / "icon.png"
        self.assertTrue(ico_path.exists(), "assets/icon.ico should exist")
        self.assertTrue(png_path.exists(), "assets/icon.png should exist")

        with Image.open(png_path) as png_img:
            self.assertEqual(png_img.format, "PNG")
            self.assertEqual(png_img.size, (256, 256))

        with Image.open(ico_path) as ico_img:
            self.assertEqual(ico_img.format, "ICO")
            self.assertGreaterEqual(ico_img.size[0], 16)

    def test_enable_high_dpi_awareness_safe_execution(self) -> None:
        # Calling enable_high_dpi_awareness should be idempotent and never raise
        gui_app.enable_high_dpi_awareness()

    def test_gui_theme_toggle_updates_treeview_and_subtitle_contrast(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        original_refresh = gui_app.GitHubSearchGUI.refresh_ollama_models
        gui_app.GitHubSearchGUI.refresh_ollama_models = lambda self: None
        root = tk.Tk()
        root.withdraw()
        try:
            app = gui_app.GitHubSearchGUI(root)
            # Create a mock preview tree
            table_frame = ttk.Frame(root)
            tree = ttk.Treeview(table_frame, columns=("repo", "score"))
            app.preview_tree = tree

            # Test dark theme styling
            app._apply_theme_colors(dark=True)
            self.assertEqual(str(app.header_subtitle.cget("foreground")), "#8b949e")
            self.assertEqual(str(tree.tag_configure("highly_recommended", "background")), "#1e2d24")
            self.assertEqual(str(tree.tag_configure("highly_recommended", "foreground")), "#e6edf3")

            # Test light theme styling
            app._apply_theme_colors(dark=False)
            self.assertEqual(str(app.header_subtitle.cget("foreground")), "#57606a")
            self.assertEqual(str(tree.tag_configure("highly_recommended", "background")), "#d4edda")
            self.assertEqual(str(tree.tag_configure("highly_recommended", "foreground")), "#155724")
        finally:
            root.destroy()
            gui_app.GitHubSearchGUI.refresh_ollama_models = original_refresh


if __name__ == "__main__":
    unittest.main()
