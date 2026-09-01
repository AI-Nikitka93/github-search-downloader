import os
import sys
import unittest
import tkinter as tk
from tkinter import ttk

# Add src to sys.path
sys.path.insert(0, r"m:\Projects\Programs\GithubSearch\src")
sys.path.insert(0, r"m:\Projects\Programs\GithubSearch")

from github_harvester.ui_components import (
    UIColors,
    CardFrame,
    HeroSearchBar,
    PillBadge,
    AccentButton,
    ModernTreeview,
    register_custom_ttk_styles,
)


class TestUIComponentsDeep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()

    def tearDown(self):
        try:
            self.top.destroy()
        except Exception:
            pass

    # -------------------------------------------------------------
    # UIColors & register_custom_ttk_styles
    # -------------------------------------------------------------
    def test_ui_colors_and_styles(self):
        self.assertTrue(isinstance(UIColors.card_bg(), str))
        self.assertTrue(isinstance(UIColors.card_border(), str))
        self.assertTrue(isinstance(UIColors.fg_primary(), str))
        self.assertTrue(isinstance(UIColors.fg_secondary(), str))
        self.assertTrue(isinstance(UIColors.fg_muted(), str))
        self.assertTrue(isinstance(UIColors.bg_subtle(), str))
        
        register_custom_ttk_styles(is_dark=True)
        register_custom_ttk_styles(is_dark=False)

    # -------------------------------------------------------------
    # CardFrame Tests
    # -------------------------------------------------------------
    def test_card_frame_variants(self):
        c1 = CardFrame(self.top)
        c1.pack()
        c1.update_theme(True)
        c1.update_theme(False)
        c1.update_theme(None)

        c2 = CardFrame(
            self.top,
            title="Test Title 🚀",
            subtitle="Subtitle with unicode: — © 😀",
            accent_color="#388bfd",
            padding=(10, 20),
        )
        c2.pack()
        c2.update_theme(True)

        c3 = CardFrame(self.top, title="Int Pad", padding=12)
        c3.pack()

        c4 = CardFrame(self.top, title="4-Pad", padding=(5, 10, 15, 20))
        c4.pack()

        c5 = CardFrame(self.top, title="", subtitle=None, accent_color=None)
        c5.pack()

        c7 = CardFrame(self.top, title="None Pad", padding=None)
        c7.pack()

        c8 = CardFrame(self.top, title="Empty Pad", padding=())
        c8.pack()

        c9 = CardFrame(self.top, title="Single Pad", padding=(15,))
        c9.pack()

        lbl = ttk.Label(c2.body, text="Inside Body")
        lbl.pack()
        self.top.update_idletasks()

    # -------------------------------------------------------------
    # HeroSearchBar Tests
    # -------------------------------------------------------------
    def test_hero_search_bar_behavior(self):
        searches_triggered = []
        tags_selected = []

        def on_search(q):
            searches_triggered.append(q)

        def on_tag(t):
            tags_selected.append(t)

        bar = HeroSearchBar(
            self.top,
            placeholder="Search here...",
            preset_tags=("OSINT", "Python", "⚡ FastAPI", "Unicode: 🤖"),
            on_search=on_search,
            on_tag_selected=on_tag,
        )
        bar.pack()
        self.top.update_idletasks()

        bar.set_query("fastapi")
        self.assertEqual(bar.get_query(), "fastapi")
        self.assertEqual(bar.clear_btn.winfo_manager(), "pack")

        bar._handle_search()
        self.assertIn("fastapi", searches_triggered)

        bar._handle_tag_click("Python")
        self.assertIn("Python", tags_selected)
        self.assertEqual(bar.get_query(), "Python")

        bar.clear()
        self.assertEqual(bar.get_query(), "")
        self.assertEqual(bar.clear_btn.winfo_manager(), "")

        searches_triggered_2 = []
        bar2 = HeroSearchBar(
            self.top,
            preset_tags=("Tag1", "Tag2"),
            on_search=lambda q: searches_triggered_2.append(q),
            on_tag_selected=None,
        )
        bar2.pack()
        bar2._handle_tag_click("Tag1")
        self.assertIn("Tag1", searches_triggered_2)

        bar3 = HeroSearchBar(self.top, preset_tags=())
        bar3.pack()
        self.assertFalse(hasattr(bar3, "chips_frame"))

        bar4 = HeroSearchBar(self.top, preset_tags=None)
        bar4.pack()
        self.assertFalse(hasattr(bar4, "chips_frame"))

        extreme_strings = [
            "",
            "   ",
            "stars:>500 repo:owner/name",
            "🚀🔥✨⚡🤖",
            "SELECT * FROM repos WHERE '1'='1'",
            "<tag attr=\"val\">hello</tag>",
            "A" * 5000,
            "line1\nline2",
            "tab\tseparated",
        ]
        for s in extreme_strings:
            bar.set_query(s)
            self.assertEqual(bar.get_query(), s.strip())
            bar._handle_search()

    # -------------------------------------------------------------
    # PillBadge Tests
    # -------------------------------------------------------------
    def test_pill_badge_rendering_and_events(self):
        clicked = []
        badge = PillBadge(
            self.top,
            text="🟢 Active",
            icon="⚡",
            on_click=lambda: clicked.append(True),
        )
        badge.pack()
        self.top.update_idletasks()

        badge.set_status("🔴 Inactive", icon="⛔", bg_color="#ff0000", fg_color="#ffffff", border_color="#aa0000")
        self.assertEqual(badge.text_content, "🔴 Inactive")
        self.assertEqual(badge.icon, "⛔")

        badge._on_enter()
        self.assertTrue(badge._is_hovered)
        badge._on_leave()
        self.assertFalse(badge._is_hovered)

        if badge.on_click:
            badge.on_click()
        self.assertEqual(clicked, [True])

        badge.config(width=1, height=1)
        badge._draw()
        badge.config(width=0, height=0)
        badge._draw()
        badge.config(width=500, height=50)
        badge._draw()

        b2 = PillBadge(self.top, text="", icon=None, on_click=None)
        b2.pack()
        b2._draw()

    # -------------------------------------------------------------
    # AccentButton Tests
    # -------------------------------------------------------------
    def test_accent_button_lifecycle(self):
        calls = []
        btn = AccentButton(
            self.top,
            text="Download",
            icon="💾",
            variant="success",
            command=lambda: calls.append("download"),
        )
        btn.pack()
        self.top.update_idletasks()

        btn._on_press()
        self.assertEqual(btn._current_bg, btn.palette["active"])
        btn._on_release()
        self.assertEqual(calls, ["download"])

        btn._on_enter()
        self.assertEqual(btn._current_bg, btn.palette["hover"])
        btn._on_leave()
        self.assertEqual(btn._current_bg, btn.palette["normal"])

        btn.configure_state("disabled")
        btn._on_enter()
        btn._on_press()
        btn._on_release()
        self.assertEqual(calls, ["download"])

        btn.configure_state("normal")
        btn._on_press()
        btn._on_release()
        self.assertEqual(calls, ["download", "download"])

        btn.set_text("Updated Action", icon="🔥")
        self.assertEqual(btn.text_content, "Updated Action")
        self.assertEqual(btn.icon, "🔥")

        for var in ("success", "primary", "danger", "purple", "invalid_variant_name"):
            b = AccentButton(self.top, text="Var", variant=var)
            b.pack()
            b._draw()

    # -------------------------------------------------------------
    # ModernTreeview Tests
    # -------------------------------------------------------------
    def test_modern_treeview_features(self):
        cols = ("repo", "stars", "forks", "updated")
        headings = ("Репозиторий", "Звезды ★", "Форки", "Обновлен")
        widths = (200, 80, 80, 100)
        alignments = ("left", "right", "center", "w")

        table = ModernTreeview(
            self.top,
            columns=cols,
            headings=headings,
            widths=widths,
            alignments=alignments,
        )
        table.pack(fill="both", expand=True)
        self.top.update_idletasks()

        r1 = table.insert_row(("owner/repo1", "1,250", "42", "2026-08-01"))
        r2 = table.insert_row(("owner/repo2", "★ 500", "$10", "2026-07-15"), tag="recommended")
        r3 = table.insert_row(("owner/repo3", "invalid_num", "0", "2026-06-01"), tag="dim")
        r4 = table.insert_row(("owner/repo4", "12.5", "100", "2026-05-20"))

        self.assertEqual(len(table.tree.get_children()), 4)

        table.sort_by_column("stars")
        self.assertFalse(table.sort_descending)
        table.sort_by_column("stars")
        self.assertTrue(table.sort_descending)

        table.sort_by_column("repo")
        self.assertFalse(table.sort_descending)

        table.clear()
        self.assertEqual(len(table.tree.get_children()), 0)


if __name__ == "__main__":
    unittest.main()
