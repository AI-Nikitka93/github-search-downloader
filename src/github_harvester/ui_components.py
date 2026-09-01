"""Modern, reusable UI components for Python Tkinter/ttk.
Designed for high-aesthetic desktop applications compatible with sv_ttk (Dark and Light themes).
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Sequence

try:
    import sv_ttk
except ImportError:
    sv_ttk = None


# ==============================================================================
# 1. SEMANTIC COLOR TOKENS & THEME HELPERS
# ==============================================================================

class UIColors:
    """Semantic color tokens matching modern GitHub Dark and Light UI standards."""

    # Dark Theme Colors (GitHub Dark Dimmed / Modern Slate)
    DARK_BG_CANVAS = "#0d1117"
    DARK_BG_CARD = "#161b22"
    DARK_BG_SUBTLE = "#21262d"
    DARK_BG_MUTED = "#30363d"
    DARK_BORDER = "#30363d"
    DARK_BORDER_MUTED = "#21262d"
    DARK_FG_PRIMARY = "#f0f6fc"
    DARK_FG_SECONDARY = "#8b949e"
    DARK_FG_MUTED = "#6e7681"
    DARK_ACCENT_GREEN = "#238636"
    DARK_ACCENT_GREEN_HOVER = "#2ea043"
    DARK_ACCENT_BLUE = "#1f6feb"
    DARK_ACCENT_BLUE_HOVER = "#388bfd"
    DARK_ACCENT_RED = "#da3633"
    DARK_ACCENT_RED_HOVER = "#f85149"
    DARK_ACCENT_PURPLE = "#8957e5"
    DARK_ACCENT_PURPLE_HOVER = "#a371f7"
    DARK_TREE_STRIPE_EVEN = "#161b22"
    DARK_TREE_STRIPE_ODD = "#0d1117"
    DARK_TREE_HIGHLIGHT = "#1e2d24"

    # Light Theme Colors (GitHub Light)
    LIGHT_BG_CANVAS = "#ffffff"
    LIGHT_BG_CARD = "#f6f8fa"
    LIGHT_BG_SUBTLE = "#eaeef2"
    LIGHT_BG_MUTED = "#d0d7de"
    LIGHT_BORDER = "#d0d7de"
    LIGHT_BORDER_MUTED = "#e1e4e8"
    LIGHT_FG_PRIMARY = "#1f2328"
    LIGHT_FG_SECONDARY = "#656d76"
    LIGHT_FG_MUTED = "#8c959f"
    LIGHT_ACCENT_GREEN = "#1f883d"
    LIGHT_ACCENT_GREEN_HOVER = "#1a7f37"
    LIGHT_ACCENT_BLUE = "#0969da"
    LIGHT_ACCENT_BLUE_HOVER = "#0860ca"
    LIGHT_ACCENT_RED = "#cf222e"
    LIGHT_ACCENT_RED_HOVER = "#a40e26"
    LIGHT_ACCENT_PURPLE = "#8250df"
    LIGHT_ACCENT_PURPLE_HOVER = "#6e40c9"
    LIGHT_TREE_STRIPE_EVEN = "#ffffff"
    LIGHT_TREE_STRIPE_ODD = "#f6f8fa"
    LIGHT_TREE_HIGHLIGHT = "#dafbe1"

    @classmethod
    def is_dark(cls) -> bool:
        if sv_ttk is not None:
            try:
                return sv_ttk.get_theme() == "dark"
            except Exception:
                pass
        return True

    @classmethod
    def card_bg(cls) -> str:
        return cls.DARK_BG_CARD if cls.is_dark() else cls.LIGHT_BG_CARD

    @classmethod
    def card_border(cls) -> str:
        return cls.DARK_BORDER if cls.is_dark() else cls.LIGHT_BORDER

    @classmethod
    def fg_primary(cls) -> str:
        return cls.DARK_FG_PRIMARY if cls.is_dark() else cls.LIGHT_FG_PRIMARY

    @classmethod
    def fg_secondary(cls) -> str:
        return cls.DARK_FG_SECONDARY if cls.is_dark() else cls.LIGHT_FG_SECONDARY

    @classmethod
    def fg_muted(cls) -> str:
        return cls.DARK_FG_MUTED if cls.is_dark() else cls.LIGHT_FG_MUTED

    @classmethod
    def bg_subtle(cls) -> str:
        return cls.DARK_BG_SUBTLE if cls.is_dark() else cls.LIGHT_BG_SUBTLE


def register_custom_ttk_styles(is_dark: bool = True) -> None:
    """Configures global ttk style overrides for custom components."""
    style = ttk.Style()
    
    # Configure ModernTreeview
    tree_bg = UIColors.DARK_BG_CANVAS if is_dark else UIColors.LIGHT_BG_CANVAS
    tree_fg = UIColors.DARK_FG_PRIMARY if is_dark else UIColors.LIGHT_FG_PRIMARY
    head_bg = UIColors.DARK_BG_CARD if is_dark else UIColors.LIGHT_BG_SUBTLE
    head_fg = UIColors.DARK_FG_PRIMARY if is_dark else UIColors.LIGHT_FG_PRIMARY
    selected_bg = UIColors.DARK_ACCENT_BLUE if is_dark else UIColors.LIGHT_ACCENT_BLUE
    
    style.configure(
        "Modern.Treeview",
        background=tree_bg,
        foreground=tree_fg,
        fieldbackground=tree_bg,
        rowheight=28,
        font=("Segoe UI Variable Text", 10),
        borderwidth=0,
    )
    style.map(
        "Modern.Treeview",
        background=[("selected", selected_bg)],
        foreground=[("selected", "#ffffff")],
    )
    style.configure(
        "Modern.Treeview.Heading",
        background=head_bg,
        foreground=head_fg,
        font=("Segoe UI Variable Display", 10, "bold"),
        padding=(8, 6),
        relief="flat",
        borderwidth=1,
    )


# ==============================================================================
# 2. CARD FRAME COMPONENT (CardFrame)
# ==============================================================================

class CardFrame(tk.Frame):
    """
    A padded modern card container with subtle simulated border,
    soft background (#161b22 / #f6f8fa), optional colored header accent stripe,
    and responsive theme auto-sync.
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str | None = None,
        subtitle: str | None = None,
        accent_color: str | None = None,
        padding: int | tuple[int, int] | tuple[int, int, int, int] = 16,
        radius: int = 8,
        **kwargs,
    ):
        self.dark = UIColors.is_dark()
        self.card_bg = UIColors.card_bg()
        self.border_color = UIColors.card_border()
        self.accent_color = accent_color
        self.radius = radius
        self.padding = padding

        super().__init__(parent, bg=self.card_bg, highlightthickness=1, highlightbackground=self.border_color, **kwargs)

        # Header section if title provided
        self.header_frame: tk.Frame | None = None
        self.title_label: tk.Label | None = None
        self.subtitle_label: tk.Label | None = None
        self.accent_stripe: tk.Frame | None = None

        if accent_color or title or subtitle:
            self._build_header(title, subtitle, accent_color)

        # Content container
        if isinstance(padding, int):
            padx, pady = padding, padding
        elif len(padding) == 2:
            padx, pady = padding
        else:
            padx, pady = padding[0], padding[1]

        self.body = tk.Frame(self, bg=self.card_bg)
        self.body.pack(fill="both", expand=True, padx=padx, pady=pady)

    def _build_header(self, title: str | None, subtitle: str | None, accent_color: str | None):
        self.header_frame = tk.Frame(self, bg=self.card_bg)
        self.header_frame.pack(fill="x", padx=12, pady=(10, 4))

        if accent_color:
            self.accent_stripe = tk.Frame(self.header_frame, bg=accent_color, width=4)
            self.accent_stripe.pack(side="left", fill="y", padx=(0, 8), pady=2)

        titles_box = tk.Frame(self.header_frame, bg=self.card_bg)
        titles_box.pack(side="left", fill="both", expand=True)

        if title:
            self.title_label = tk.Label(
                titles_box,
                text=title,
                font=("Segoe UI Variable Display", 11, "bold"),
                bg=self.card_bg,
                fg=UIColors.fg_primary(),
                anchor="w",
            )
            self.title_label.pack(fill="x", anchor="w")

        if subtitle:
            self.subtitle_label = tk.Label(
                titles_box,
                text=subtitle,
                font=("Segoe UI Variable Text", 9),
                bg=self.card_bg,
                fg=UIColors.fg_secondary(),
                anchor="w",
            )
            self.subtitle_label.pack(fill="x", anchor="w")

        # Subtle separator line
        sep = tk.Frame(self, bg=self.border_color, height=1)
        sep.pack(fill="x", padx=8, pady=(4, 0))

    def update_theme(self, is_dark: bool | None = None) -> None:
        """Refreshes card colors upon theme toggle."""
        if is_dark is None:
            is_dark = UIColors.is_dark()
        self.dark = is_dark
        self.card_bg = UIColors.card_bg()
        self.border_color = UIColors.card_border()

        self.configure(bg=self.card_bg, highlightbackground=self.border_color)
        if self.header_frame:
            self.header_frame.configure(bg=self.card_bg)
        if self.title_label:
            self.title_label.configure(bg=self.card_bg, fg=UIColors.fg_primary())
        if self.subtitle_label:
            self.subtitle_label.configure(bg=self.card_bg, fg=UIColors.fg_secondary())
        if hasattr(self, "body"):
            self.body.configure(bg=self.card_bg)


# ==============================================================================
# 3. HERO SEARCH BAR (HeroSearchBar)
# ==============================================================================

class HeroSearchBar(tk.Frame):
    """
    Large modern search bar with:
    - Leading search icon 🔍
    - High-visibility font and placeholder support
    - Quick clear button ✕ (appears when query is typed)
    - Preset quick-filter tag chips below
    """

    def __init__(
        self,
        parent: tk.Misc,
        placeholder: str = "Поиск репозиториев, технологий, AI агентов...",
        preset_tags: Sequence[str] = ("OSINT", "LLM Agent", "FastAPI", "React", "Rust", "Security"),
        on_search: Callable[[str], None] | None = None,
        on_tag_selected: Callable[[str], None] | None = None,
        **kwargs,
    ):
        self.placeholder = placeholder
        self.preset_tags = list(preset_tags)
        self.on_search = on_search
        self.on_tag_selected = on_tag_selected

        card_bg = UIColors.card_bg()
        super().__init__(parent, bg=card_bg, **kwargs)

        self.query_var = tk.StringVar()
        self._build_bar()
        self._build_preset_chips()

    def _build_bar(self):
        # Outer container with rounded border feel
        border_col = UIColors.card_border()
        input_bg = UIColors.DARK_BG_CANVAS if UIColors.is_dark() else "#ffffff"

        self.bar_container = tk.Frame(
            self,
            bg=input_bg,
            highlightthickness=1,
            highlightbackground=border_col,
            highlightcolor=UIColors.DARK_ACCENT_BLUE if UIColors.is_dark() else UIColors.LIGHT_ACCENT_BLUE,
            padx=10,
            pady=6,
        )
        self.bar_container.pack(fill="x", expand=True)

        # 🔍 Search Icon
        self.icon_label = tk.Label(
            self.bar_container,
            text="🔍",
            font=("Segoe UI Emoji", 12),
            bg=input_bg,
            fg=UIColors.fg_secondary(),
        )
        self.icon_label.pack(side="left", padx=(2, 8))

        # Main Entry Field
        self.entry = tk.Entry(
            self.bar_container,
            textvariable=self.query_var,
            font=("Segoe UI Variable Text", 12),
            bg=input_bg,
            fg=UIColors.fg_primary(),
            insertbackground=UIColors.fg_primary(),
            relief="flat",
            bd=0,
        )
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<Return>", lambda e: self._handle_search())
        self.entry.bind("<KeyRelease>", self._on_key_release)

        # Clear button ✕
        self.clear_btn = tk.Label(
            self.bar_container,
            text="✕",
            font=("Segoe UI Variable Text", 11, "bold"),
            bg=input_bg,
            fg=UIColors.fg_muted(),
            cursor="hand2",
            padx=4,
        )
        self.clear_btn.bind("<Button-1>", lambda e: self.clear())
        self.clear_btn.bind("<Enter>", lambda e: self.clear_btn.configure(fg=UIColors.fg_primary()))
        self.clear_btn.bind("<Leave>", lambda e: self.clear_btn.configure(fg=UIColors.fg_muted()))

        # Search Action Button
        self.search_btn = tk.Label(
            self.bar_container,
            text=" Найти ",
            font=("Segoe UI Variable Text", 10, "bold"),
            bg=UIColors.DARK_ACCENT_BLUE if UIColors.is_dark() else UIColors.LIGHT_ACCENT_BLUE,
            fg="#ffffff",
            cursor="hand2",
            padx=12,
            pady=4,
        )
        self.search_btn.pack(side="right", padx=(6, 0))
        self.search_btn.bind("<Button-1>", lambda e: self._handle_search())

    def _build_preset_chips(self):
        if not self.preset_tags:
            return

        self.chips_frame = tk.Frame(self, bg=self["bg"])
        self.chips_frame.pack(fill="x", pady=(8, 0))

        lbl = tk.Label(
            self.chips_frame,
            text="Быстрый выбор:",
            font=("Segoe UI Variable Text", 9),
            bg=self["bg"],
            fg=UIColors.fg_secondary(),
        )
        lbl.pack(side="left", padx=(2, 6))

        for tag in self.preset_tags:
            chip = PillBadge(
                self.chips_frame,
                text=f"#{tag}",
                bg_color=UIColors.bg_subtle(),
                fg_color=UIColors.fg_primary(),
                hover_color=UIColors.DARK_ACCENT_BLUE if UIColors.is_dark() else UIColors.LIGHT_ACCENT_BLUE,
                hover_fg="#ffffff",
                on_click=lambda t=tag: self._handle_tag_click(t),
            )
            chip.pack(side="left", padx=3)

    def _on_key_release(self, event=None):
        text = self.query_var.get()
        if text:
            self.clear_btn.pack(side="right", padx=(2, 4))
        else:
            self.clear_btn.pack_forget()

    def _handle_search(self):
        query = self.query_var.get().strip()
        if self.on_search:
            self.on_search(query)

    def _handle_tag_click(self, tag: str):
        self.set_query(tag)
        if self.on_tag_selected:
            self.on_tag_selected(tag)
        elif self.on_search:
            self.on_search(tag)

    def clear(self):
        self.query_var.set("")
        self.clear_btn.pack_forget()
        self.entry.focus_set()

    def get_query(self) -> str:
        return self.query_var.get().strip()

    def set_query(self, text: str) -> None:
        self.query_var.set(text)
        self._on_key_release()


# ==============================================================================
# 4. PILL BADGE COMPONENT (PillBadge)
# ==============================================================================

class PillBadge(tk.Canvas):
    """
    Rounded colored status chip / tag badge.
    Ideal for:
    - 🟢 Connected / ⚪ Anonymous
    - 🎁 Free Model / ⚡ 5000/5000 req / 💾 120 GB Free
    Supports smooth canvas anti-aliased pill drawing, dynamic text/color updates, and hover clicks.
    """

    def __init__(
        self,
        parent: tk.Misc,
        text: str = "Status",
        icon: str | None = None,
        bg_color: str | None = None,
        fg_color: str | None = None,
        border_color: str | None = None,
        hover_color: str | None = None,
        hover_fg: str | None = None,
        font: tuple = ("Segoe UI Variable Text", 9, "normal"),
        padding_x: int = 10,
        padding_y: int = 4,
        on_click: Callable[[], None] | None = None,
        **kwargs,
    ):
        self.text_content = text
        self.icon = icon
        self.font = font
        self.padding_x = padding_x
        self.padding_y = padding_y
        self.on_click = on_click

        self.bg_color = bg_color or UIColors.bg_subtle()
        self.fg_color = fg_color or UIColors.fg_primary()
        self.border_color = border_color or UIColors.card_border()
        self.hover_color = hover_color
        self.hover_fg = hover_fg

        self._is_hovered = False

        parent_bg = parent["bg"] if "bg" in parent.keys() else UIColors.card_bg()
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0, **kwargs)

        self.bind("<Configure>", self._draw)
        if self.on_click:
            self.config(cursor="hand2")
            self.bind("<Button-1>", lambda e: self.on_click())
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)

        self._recalculate_size()

    def _recalculate_size(self):
        display_text = f"{self.icon} {self.text_content}".strip() if self.icon else self.text_content
        # Estimate width and height
        char_w = 7.5
        text_w = int(len(display_text) * char_w)
        w = text_w + self.padding_x * 2 + 4
        h = 24 + self.padding_y
        self.config(width=w, height=h)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        fill_bg = self.hover_color if (self._is_hovered and self.hover_color) else self.bg_color
        text_fg = self.hover_fg if (self._is_hovered and self.hover_fg) else self.fg_color
        border_col = self.border_color

        r = (h - 2) // 2

        # Draw smooth rounded pill shape
        self.create_arc(1, 1, 2 * r, h - 1, start=90, extent=180, fill=fill_bg, outline=border_col)
        self.create_arc(w - 2 * r - 1, 1, w - 1, h - 1, start=270, extent=180, fill=fill_bg, outline=border_col)
        self.create_rectangle(r, 1, w - r, h - 1, fill=fill_bg, outline=fill_bg)
        # Top and bottom border lines
        self.create_line(r, 1, w - r, 1, fill=border_col)
        self.create_line(r, h - 1, w - r, h - 1, fill=border_col)

        display_text = f"{self.icon} {self.text_content}".strip() if self.icon else self.text_content
        self.create_text(w // 2, h // 2, text=display_text, fill=text_fg, font=self.font)

    def _on_enter(self, event=None):
        self._is_hovered = True
        self._draw()

    def _on_leave(self, event=None):
        self._is_hovered = False
        self._draw()

    def set_status(
        self,
        text: str,
        icon: str | None = None,
        bg_color: str | None = None,
        fg_color: str | None = None,
        border_color: str | None = None,
    ):
        """Dynamically updates badge status text, icon, and colors."""
        self.text_content = text
        if icon is not None:
            self.icon = icon
        if bg_color is not None:
            self.bg_color = bg_color
        if fg_color is not None:
            self.fg_color = fg_color
        if border_color is not None:
            self.border_color = border_color

        self._recalculate_size()
        self._draw()


# ==============================================================================
# 5. ACCENT BUTTON COMPONENT (AccentButton)
# ==============================================================================

class AccentButton(tk.Canvas):
    """
    High-contrast primary action button with hover elevation and active press depth.
    Variants:
    - 'success' (GitHub Green #238636 / #2ea043)
    - 'primary' (Brand Blue #0969da / #1f6feb)
    - 'danger' (Coral Red #da3633 / #f85149)
    - 'purple' (AI Purple #8957e5 / #a371f7)
    """

    PALETTES = {
        "success": {
            "normal": UIColors.DARK_ACCENT_GREEN,
            "hover": UIColors.DARK_ACCENT_GREEN_HOVER,
            "active": "#1b692a",
            "fg": "#ffffff",
        },
        "primary": {
            "normal": UIColors.LIGHT_ACCENT_BLUE,
            "hover": UIColors.LIGHT_ACCENT_BLUE_HOVER,
            "active": "#074fa8",
            "fg": "#ffffff",
        },
        "danger": {
            "normal": UIColors.DARK_ACCENT_RED,
            "hover": UIColors.DARK_ACCENT_RED_HOVER,
            "active": "#b62324",
            "fg": "#ffffff",
        },
        "purple": {
            "normal": UIColors.DARK_ACCENT_PURPLE,
            "hover": UIColors.DARK_ACCENT_PURPLE_HOVER,
            "active": "#6e3fc9",
            "fg": "#ffffff",
        },
    }

    def __init__(
        self,
        parent: tk.Misc,
        text: str = "Action",
        icon: str | None = None,
        variant: str = "success",
        command: Callable[[], None] | None = None,
        font: tuple = ("Segoe UI Variable Display", 10, "bold"),
        height: int = 34,
        corner_radius: int = 6,
        state: str = "normal",
        **kwargs,
    ):
        self.text_content = text
        self.icon = icon
        self.variant = variant
        self.command = command
        self.font = font
        self.btn_height = height
        self.corner_radius = corner_radius
        self.btn_state = state

        self.palette = self.PALETTES.get(variant, self.PALETTES["success"])
        self._current_bg = self.palette["normal"]

        parent_bg = parent["bg"] if "bg" in parent.keys() else UIColors.card_bg()
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0, height=height, **kwargs)

        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._recalculate_width()

    def _recalculate_width(self):
        display_text = f"{self.icon} {self.text_content}".strip() if self.icon else self.text_content
        char_w = 8.5
        w = max(90, int(len(display_text) * char_w) + 32)
        self.config(width=w, height=self.btn_height)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        if self.btn_state == "disabled":
            bg_col = UIColors.DARK_BG_MUTED if UIColors.is_dark() else UIColors.LIGHT_BG_MUTED
            fg_col = UIColors.DARK_FG_MUTED if UIColors.is_dark() else UIColors.LIGHT_FG_MUTED
            self.config(cursor="")
        else:
            bg_col = self._current_bg
            fg_col = self.palette["fg"]
            self.config(cursor="hand2")

        r = min(self.corner_radius, h // 2)

        # Draw rounded rectangle
        self.create_arc(1, 1, 2 * r, 2 * r, start=90, extent=90, fill=bg_col, outline=bg_col)
        self.create_arc(w - 2 * r - 1, 1, w - 1, 2 * r, start=0, extent=90, fill=bg_col, outline=bg_col)
        self.create_arc(w - 2 * r - 1, h - 2 * r - 1, w - 1, h - 1, start=270, extent=90, fill=bg_col, outline=bg_col)
        self.create_arc(1, h - 2 * r - 1, 2 * r, h - 1, start=180, extent=90, fill=bg_col, outline=bg_col)
        self.create_rectangle(r, 1, w - r, h - 1, fill=bg_col, outline=bg_col)
        self.create_rectangle(1, r, w - 1, h - r, fill=bg_col, outline=bg_col)

        display_text = f"{self.icon} {self.text_content}".strip() if self.icon else self.text_content
        self.create_text(w // 2, h // 2, text=display_text, fill=fg_col, font=self.font)

    def _on_enter(self, event=None):
        if self.btn_state != "disabled":
            self._current_bg = self.palette["hover"]
            self._draw()

    def _on_leave(self, event=None):
        if self.btn_state != "disabled":
            self._current_bg = self.palette["normal"]
            self._draw()

    def _on_press(self, event=None):
        if self.btn_state != "disabled":
            self._current_bg = self.palette["active"]
            self._draw()

    def _on_release(self, event=None):
        if self.btn_state != "disabled":
            self._current_bg = self.palette["hover"]
            self._draw()
            if self.command:
                self.command()

    def configure_state(self, state: str):
        self.btn_state = state
        self._current_bg = self.palette["normal"]
        self._draw()

    def set_text(self, text: str, icon: str | None = None):
        self.text_content = text
        if icon is not None:
            self.icon = icon
        self._recalculate_width()
        self._draw()


# ==============================================================================
# 6. MODERN TREEVIEW (ModernTreeview)
# ==============================================================================

class ModernTreeview(ttk.Frame):
    """
    Styled high-aesthetic results table with:
    - Clean row height and font padding
    - Alternating row striping (zebra colors)
    - Custom column headers with sort arrow glyphs
    - Seamless scrollbar integration
    - Pre-configured status tags (e.g. recommended, warning, dim)
    """

    ALIGN_MAP = {
        "left": "w",
        "right": "e",
        "center": "center",
        "w": "w",
        "e": "e",
    }

    def __init__(
        self,
        parent: tk.Misc,
        columns: Sequence[str],
        headings: Sequence[str] | None = None,
        widths: Sequence[int] | None = None,
        alignments: Sequence[str] | None = None,
        height: int = 15,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.columns = tuple(columns)
        self.sort_column_name: str | None = None
        self.sort_descending: bool = False

        register_custom_ttk_styles(UIColors.is_dark())

        self.tree = ttk.Treeview(
            self,
            columns=self.columns,
            show="headings",
            style="Modern.Treeview",
            height=height,
        )

        self.scrollbar_y = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        self.scrollbar_y.pack(side="right", fill="y")

        self._setup_columns(headings, widths, alignments)
        self._apply_row_tags()

    def _setup_columns(
        self,
        headings: Sequence[str] | None,
        widths: Sequence[int] | None,
        alignments: Sequence[str] | None,
    ):
        for idx, col in enumerate(self.columns):
            title = headings[idx] if headings and idx < len(headings) else col.capitalize()
            width = widths[idx] if widths and idx < len(widths) else 120
            raw_align = alignments[idx] if alignments and idx < len(alignments) else "w"
            align = self.ALIGN_MAP.get(raw_align.lower(), "w")

            self.tree.heading(col, text=title, command=lambda c=col: self.sort_by_column(c))
            self.tree.column(col, width=width, anchor=align)

    def _apply_row_tags(self):
        is_dark = UIColors.is_dark()
        stripe_even = UIColors.DARK_TREE_STRIPE_EVEN if is_dark else UIColors.LIGHT_TREE_STRIPE_EVEN
        stripe_odd = UIColors.DARK_TREE_STRIPE_ODD if is_dark else UIColors.LIGHT_TREE_STRIPE_ODD
        fg_col = UIColors.DARK_FG_PRIMARY if is_dark else UIColors.LIGHT_FG_PRIMARY

        self.tree.tag_configure("evenrow", background=stripe_even, foreground=fg_col)
        self.tree.tag_configure("oddrow", background=stripe_odd, foreground=fg_col)
        self.tree.tag_configure(
            "recommended",
            background=UIColors.DARK_TREE_HIGHLIGHT if is_dark else UIColors.LIGHT_TREE_HIGHLIGHT,
            foreground="#3fb950" if is_dark else "#1a7f37",
        )
        self.tree.tag_configure(
            "dim",
            foreground=UIColors.DARK_FG_MUTED if is_dark else UIColors.LIGHT_FG_MUTED,
        )

    def insert_row(self, values: Sequence, tag: str | None = None, iid: str | None = None) -> str:
        """Inserts a row with alternating stripe tag or custom tag."""
        row_count = len(self.tree.get_children())
        base_stripe = "evenrow" if row_count % 2 == 0 else "oddrow"
        tags = (base_stripe, tag) if tag else (base_stripe,)
        
        return self.tree.insert("", "end", iid=iid, values=values, tags=tags)

    def clear(self):
        """Clears all rows from table."""
        for item in self.tree.get_children():
            self.tree.delete(item)

    def sort_by_column(self, col: str):
        """Sorts treeview contents when user clicks column heading."""
        if self.sort_column_name == col:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column_name = col
            self.sort_descending = False

        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]

        # Attempt numeric sort if values are numbers
        def sort_key(val):
            try:
                clean_str = val[0].replace(",", "").replace("$", "").replace("★", "").strip()
                return (0, float(clean_str))
            except (ValueError, TypeError):
                return (1, str(val[0]).lower())

        items.sort(key=sort_key, reverse=self.sort_descending)

        for index, (_, k) in enumerate(items):
            self.tree.move(k, "", index)
            # Re-apply alternating colors
            current_tags = list(self.tree.item(k, "tags"))
            clean_tags = [t for t in current_tags if t not in ("evenrow", "oddrow")]
            stripe = "evenrow" if index % 2 == 0 else "oddrow"
            self.tree.item(k, tags=(stripe, *clean_tags))
