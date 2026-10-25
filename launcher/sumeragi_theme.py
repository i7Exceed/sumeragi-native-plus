#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Centralized Dark Sengoku-Tech Theme and Design Tokens for Sumeragi Native+.

Provides unified color palettes, typography, spacing, and ttk widget styling
for an elegant, understated samurai control-center aesthetic.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Color Tokens
# ---------------------------------------------------------------------------

# Backgrounds & Surfaces
BG_MAIN = "#151619"          # Main application background
BG_SIDEBAR = "#1B1C20"       # Left navigation sidebar
BG_CARD = "#202126"          # Cards and content panels
BG_ELEVATED = "#292A2F"      # Elevated headers, toolbars, and input wells
BG_INPUT = "#1A1B1F"         # Text fields and dropdown background
BG_DROPDOWN_LIST = "#1E1F24" # Combobox dropdown popups

# Text & Foreground
TEXT_PRIMARY = "#F2EBDD"     # Soft ivory white for primary headers & body
TEXT_SECONDARY = "#B5B2AB"   # Warm muted gray for labels and secondary descriptions
TEXT_MUTED = "#72706A"       # Dimmed text for disabled states and footnotes
TEXT_INVERSE = "#151619"     # Dark text when placed over bright gold/accents

# Accents (Antique Gold & Samurai Crimson)
ACCENT_GOLD = "#B99A5A"      # Antique gold for highlights, active tabs, badges
ACCENT_GOLD_HOVER = "#D4B36A"# Brighter gold on hover and focus
ACCENT_GOLD_MUTED = "#3D3420"# Subdued gold background tint
ACCENT_CRIMSON = "#9C2B24"   # Primary action / Launch button crimson
ACCENT_CRIMSON_HOVER = "#B8362D" # Hover crimson
ACCENT_CRIMSON_ACTIVE = "#7A1F19" # Pressed crimson

# Status Colors
COLOR_SUCCESS = "#5FA371"    # Muted green for ready/installed/unlocked states
COLOR_WARNING = "#DCA048"    # Warm amber for warnings and required actions
COLOR_ERROR = "#CD5555"      # Subdued red for error states and missing files
COLOR_INFO = "#5A88B5"       # Subdued blue for informational badges

# Borders & Dividers
BORDER_SUBTLE = "#2C2D35"    # Default subtle card border and divider
BORDER_LIGHT = "#3B3D47"     # Active / focused borders

# ---------------------------------------------------------------------------
# Typography Tokens
# ---------------------------------------------------------------------------

FONT_FAMILY = "Segoe UI"
FONT_HERO = (FONT_FAMILY, 18, "bold")
FONT_TITLE = (FONT_FAMILY, 15, "bold")
FONT_HEADING = (FONT_FAMILY, 12, "bold")
FONT_SUBHEADING = (FONT_FAMILY, 11, "bold")
FONT_BODY = (FONT_FAMILY, 10)
FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
FONT_CAPTION = (FONT_FAMILY, 9)
FONT_CAPTION_BOLD = (FONT_FAMILY, 9, "bold")
FONT_BADGE = (FONT_FAMILY, 8, "bold")
FONT_MONO = ("Consolas", 9)

# ---------------------------------------------------------------------------
# Style Application
# ---------------------------------------------------------------------------

def apply_theme(root: tk.Tk) -> ttk.Style:
    """Configures ttk styles and root Tk options with Dark Sengoku-Tech tokens."""
    style = ttk.Style(root)
    style.theme_use("clam")

    # Global widget defaults
    style.configure(
        ".",
        background=BG_MAIN,
        foreground=TEXT_PRIMARY,
        fieldbackground=BG_INPUT,
        bordercolor=BORDER_SUBTLE,
        lightcolor=BORDER_SUBTLE,
        darkcolor=BORDER_SUBTLE,
        troughcolor=BG_CARD,
        font=FONT_BODY,
    )

    # Base Frames
    style.configure("TFrame", background=BG_MAIN)
    style.configure("Sidebar.TFrame", background=BG_SIDEBAR)
    style.configure("Card.TFrame", background=BG_CARD)
    style.configure("Elevated.TFrame", background=BG_ELEVATED)
    style.configure("Panel.TFrame", background=BG_CARD)

    # Labels
    style.configure("TLabel", background=BG_MAIN, foreground=TEXT_PRIMARY)
    style.configure("Sidebar.TLabel", background=BG_SIDEBAR, foreground=TEXT_PRIMARY)
    style.configure("SidebarMuted.TLabel", background=BG_SIDEBAR, foreground=TEXT_SECONDARY, font=FONT_CAPTION)
    style.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY)
    style.configure("CardSecondary.TLabel", background=BG_CARD, foreground=TEXT_SECONDARY, font=FONT_BODY)
    style.configure("CardMuted.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=FONT_CAPTION)
    style.configure("CardHeading.TLabel", background=BG_CARD, foreground=ACCENT_GOLD, font=FONT_HEADING)
    style.configure("PageTitle.TLabel", background=BG_MAIN, foreground=TEXT_PRIMARY, font=FONT_TITLE)
    style.configure("PageSubtitle.TLabel", background=BG_MAIN, foreground=TEXT_SECONDARY, font=FONT_BODY)

    # Badges
    style.configure("BadgeGold.TLabel", background=ACCENT_GOLD_MUTED, foreground=ACCENT_GOLD, font=FONT_BADGE, padding=(6, 2))
    style.configure("BadgeSuccess.TLabel", background="#223927", foreground=COLOR_SUCCESS, font=FONT_BADGE, padding=(6, 2))
    style.configure("BadgeWarning.TLabel", background="#3F2F18", foreground=COLOR_WARNING, font=FONT_BADGE, padding=(6, 2))
    style.configure("BadgeError.TLabel", background="#3B1C1C", foreground=COLOR_ERROR, font=FONT_BADGE, padding=(6, 2))
    style.configure("BadgeMuted.TLabel", background=BG_ELEVATED, foreground=TEXT_SECONDARY, font=FONT_BADGE, padding=(6, 2))

    # Standard Buttons
    style.configure(
        "TButton",
        background=BG_ELEVATED,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
        padding=(10, 5),
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("pressed", BG_INPUT), ("active", "#363840"), ("disabled", BG_MAIN)],
        foreground=[("disabled", TEXT_MUTED), ("active", TEXT_PRIMARY)],
        bordercolor=[("active", ACCENT_GOLD), ("disabled", BORDER_SUBTLE)],
    )

    # Small Buttons
    style.configure("Small.TButton", font=FONT_CAPTION, padding=(8, 4))
    style.map(
        "Small.TButton",
        background=[("pressed", BG_INPUT), ("active", "#363840"), ("disabled", BG_MAIN)],
        foreground=[("disabled", TEXT_MUTED), ("active", TEXT_PRIMARY)],
    )

    # Primary Action (Crimson Launch Button)
    style.configure(
        "Primary.TButton",
        background=ACCENT_CRIMSON,
        foreground="#FFFFFF",
        font=FONT_HEADING,
        padding=(14, 10),
        borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[("pressed", ACCENT_CRIMSON_ACTIVE), ("active", ACCENT_CRIMSON_HOVER), ("disabled", "#44201E")],
        foreground=[("disabled", TEXT_MUTED)],
    )

    # Stop Button
    style.configure(
        "Stop.TButton",
        background="#2B1E1E",
        foreground=COLOR_ERROR,
        font=FONT_BODY_BOLD,
        padding=(10, 8),
    )
    style.map(
        "Stop.TButton",
        background=[("pressed", "#1E1515"), ("active", "#3A2222"), ("disabled", BG_CARD)],
        foreground=[("disabled", TEXT_MUTED)],
    )

    # Accent Gold Button
    style.configure(
        "Gold.TButton",
        background=ACCENT_GOLD_MUTED,
        foreground=ACCENT_GOLD,
        font=FONT_BODY_BOLD,
        padding=(10, 5),
    )
    style.map(
        "Gold.TButton",
        background=[("pressed", "#2E2616"), ("active", "#4A3F28"), ("disabled", BG_CARD)],
        foreground=[("disabled", TEXT_MUTED), ("active", ACCENT_GOLD_HOVER)],
    )

    # Radiobuttons & Checkbuttons
    style.configure("TRadiobutton", background=BG_CARD, foreground=TEXT_PRIMARY, font=FONT_BODY)
    style.map("TRadiobutton", background=[("active", BG_CARD)], foreground=[("active", ACCENT_GOLD)])
    style.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_PRIMARY, font=FONT_BODY)
    style.map("TCheckbutton", background=[("active", BG_CARD)], foreground=[("active", ACCENT_GOLD)])

    # Text Entry & Combobox
    style.configure("TEntry", fieldbackground=BG_INPUT, foreground=TEXT_PRIMARY, insertcolor=ACCENT_GOLD, bordercolor=BORDER_SUBTLE)
    style.map("TEntry", bordercolor=[("focus", ACCENT_GOLD)])

    style.configure(
        "TCombobox",
        fieldbackground=BG_INPUT,
        background=BG_ELEVATED,
        foreground=TEXT_PRIMARY,
        arrowcolor=ACCENT_GOLD,
        bordercolor=BORDER_SUBTLE,
        selectbackground=BG_ELEVATED,
        selectforeground=TEXT_PRIMARY,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", BG_INPUT)],
        foreground=[("readonly", TEXT_PRIMARY)],
        bordercolor=[("focus", ACCENT_GOLD)],
    )

    # Progressbar
    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT_GOLD,
        troughcolor=BG_ELEVATED,
        bordercolor=BORDER_SUBTLE,
        lightcolor=ACCENT_GOLD_HOVER,
        darkcolor=ACCENT_GOLD,
    )

    # Tk Listbox options for comboboxes and popups
    root.option_add("*TCombobox*Listbox.background", BG_DROPDOWN_LIST)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT_INVERSE)
    root.option_add("*TCombobox*Listbox.borderWidth", 1)
    root.option_add("*TCombobox*Listbox.relief", "solid")

    return style
