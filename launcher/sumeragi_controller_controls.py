#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Sumeragi Native+ Controller Button Remapping Subsystem.

Provides per-game logical controller button remapping for Sengoku Basara 4 Sumeragi,
connecting the launcher's user preferences to the native runtime's SPARTAN_PAD_MAP
input pipeline while strictly preserving SDL device-level hardware mappings.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Runtime Actions & Default Bindings
# ---------------------------------------------------------------------------

LOGICAL_ACTIONS: List[Tuple[str, str, str, str, str, str]] = [
    # (action_id, default_source, label_en, label_id, desc_en, desc_id)
    ("cross", "a", "Cross / Jump", "Cross / Lompat", "Jump / confirm in menus", "Lompat / konfirmasi menu"),
    ("circle", "b", "Circle / Basara", "Circle / Basara", "Basara Art / cancel in menus", "Jurus Basara / batal"),
    ("square", "x", "Square / Attack", "Square / Serangan Normal", "Normal attack combo string", "Serangan berantai normal"),
    ("triangle", "y", "Triangle / Skill", "Triangle / Jurus Karakter", "Character special skill move", "Skill khusus karakter"),
    ("l1", "leftshoulder", "L1 / Guard", "L1 / Tangkis & Bertahan", "Guard, parry, and evasion stance", "Menangkis / bertahan"),
    ("r1", "rightshoulder", "R1 / Secondary Skill", "R1 / Skill Sekunder", "Secondary special skill move", "Skill sekunder karakter"),
    ("l3", "leftstick", "L3 / Left Stick Click", "L3 / Tekan Stick Kiri", "Camera reset / target lock", "Reset kamera / kunci target"),
    ("r3", "rightstick", "R3 / Right Stick Click", "R3 / Tekan Stick Kanan", "Taunt / Style activation", "Mengejek musuh (Taunt)"),
    ("options", "start", "Options / Pause", "Options / Jeda Menu", "In-game pause menu", "Menu jeda game"),
    ("touchpad_right", "back", "Touchpad / Map Menu", "Touchpad / Menu Peta", "Battlefield map / status screen", "Peta medan tempur"),
    ("touchpad_left", "None", "Touchpad Left / Photo", "Touchpad Kiri / Mode Foto", "Photo mode trigger", "Pemicu mode foto"),
    ("up", "dpup", "D-Pad Up", "D-Pad Atas", "Tactical prompt / ally orders", "Perintah rekan / navigasi"),
    ("down", "dpdown", "D-Pad Down", "D-Pad Bawah", "Tactical prompt / ally orders", "Perintah rekan / navigasi"),
    ("left", "dpleft", "D-Pad Left", "D-Pad Kiri", "Tactical prompt / ally orders", "Perintah rekan / navigasi"),
    ("right", "dpright", "D-Pad Right", "D-Pad Kanan", "Tactical prompt / ally orders", "Perintah rekan / navigasi"),
]

DEFAULT_PAD_CONTROLS: Dict[str, str] = {
    action: default for action, default, *_ in LOGICAL_ACTIONS
}

VALID_ACTION_NAMES: Set[str] = {action for action, *_ in LOGICAL_ACTIONS}

# All valid SDL3 canonical button strings recognized by runtime_pad.c
VALID_SDL_BUTTONS: Set[str] = {
    "a",
    "b",
    "x",
    "y",
    "leftshoulder",
    "rightshoulder",
    "leftstick",
    "rightstick",
    "start",
    "back",
    "guide",
    "dpup",
    "dpdown",
    "dpleft",
    "dpright",
    "touchpad",
    "misc1",
    "paddle1",
    "paddle2",
    "paddle3",
    "paddle4",
    "None",
}

# ---------------------------------------------------------------------------
# Button Labels for Various Controller Layouts
# ---------------------------------------------------------------------------

BUTTON_LABELS: Dict[str, Dict[str, str]] = {
    "playstation": {
        "a": "✕ Cross (South / Bawah)",
        "b": "○ Circle (East / Kanan)",
        "x": "□ Square (West / Kiri)",
        "y": "△ Triangle (North / Atas)",
        "leftshoulder": "L1 (Left Bumper)",
        "rightshoulder": "R1 (Right Bumper)",
        "leftstick": "L3 (Left Stick Click)",
        "rightstick": "R3 (Right Stick Click)",
        "start": "Options (Start)",
        "back": "Share / Touchpad (Back)",
        "guide": "PS Button",
        "touchpad": "Touchpad Click",
        "dpup": "D-Pad Up (Atas)",
        "dpdown": "D-Pad Down (Bawah)",
        "dpleft": "D-Pad Left (Kiri)",
        "dpright": "D-Pad Right (Kanan)",
        "misc1": "Mic / Mute",
        "paddle1": "Paddle 1 (Back Right)",
        "paddle2": "Paddle 2 (Back Left)",
        "paddle3": "Paddle 3 (Back Right Low)",
        "paddle4": "Paddle 4 (Back Left Low)",
        "None": "— None (Unassigned) —",
    },
    "xbox": {
        "a": "A (South / Bawah)",
        "b": "B (East / Kanan)",
        "x": "X (West / Kiri)",
        "y": "Y (North / Atas)",
        "leftshoulder": "LB (Left Bumper)",
        "rightshoulder": "RB (Right Bumper)",
        "leftstick": "LS (Left Stick Click)",
        "rightstick": "RS (Right Stick Click)",
        "start": "Menu (Start)",
        "back": "View (Back)",
        "guide": "Xbox Button",
        "touchpad": "Touchpad / Extra",
        "dpup": "D-Pad Up (Atas)",
        "dpdown": "D-Pad Down (Bawah)",
        "dpleft": "D-Pad Left (Kiri)",
        "dpright": "D-Pad Right (Kanan)",
        "misc1": "Share",
        "paddle1": "Paddle 1 (P1)",
        "paddle2": "Paddle 2 (P2)",
        "paddle3": "Paddle 3 (P3)",
        "paddle4": "Paddle 4 (P4)",
        "None": "— None (Unassigned) —",
    },
    "nintendo": {
        "a": "B (South / Bawah)",
        "b": "A (East / Kanan)",
        "x": "Y (West / Kiri)",
        "y": "X (North / Atas)",
        "leftshoulder": "L (Left Bumper)",
        "rightshoulder": "R (Right Bumper)",
        "leftstick": "Left Stick Click",
        "rightstick": "Right Stick Click",
        "start": "+ (Plus / Start)",
        "back": "- (Minus / Select)",
        "guide": "Home",
        "touchpad": "Touchpad / Extra",
        "dpup": "D-Pad Up (Atas)",
        "dpdown": "D-Pad Down (Bawah)",
        "dpleft": "D-Pad Left (Kiri)",
        "dpright": "D-Pad Right (Kanan)",
        "misc1": "Capture",
        "paddle1": "Paddle 1",
        "paddle2": "Paddle 2",
        "paddle3": "Paddle 3",
        "paddle4": "Paddle 4",
        "None": "— None (Unassigned) —",
    },
}

UI_TEXTS = {
    "en": {
        "title": "Controller Controls & Button Remapping",
        "header": "CONTROLLER BUTTON REMAPPING",
        "subtitle": "Remap logical game actions to your preferred controller buttons.",
        "layout_prompt": "Button Label Style:",
        "note_analog": (
            "ℹ️  Note: Analog Sticks (movement/camera) and Triggers (L2 / R2) operate on analog "
            "hardware axes and cannot be digitally swapped. Changes take effect on the next game launch."
        ),
        "col_action": "Game Action",
        "col_binding": "Assigned Button",
        "col_capture": "Capture",
        "col_reset": "Reset",
        "btn_capture": "🎮 Press Button",
        "btn_capturing": "Listening... (Esc to cancel)",
        "btn_reset_action": "↺ Reset",
        "btn_reset_all": "↺ Reset All to Default",
        "btn_save": "💾 Save & Apply",
        "btn_cancel": "Cancel",
        "swapped_notice": "Swapped '{}' with '{}' to prevent duplicate inputs.",
        "confirm_reset_title": "Reset All Controls",
        "confirm_reset_msg": "Are you sure you want to reset all controller bindings to default?",
        "saved_title": "Controls Saved",
        "saved_msg": "Controller button remapping has been saved successfully.",
    },
    "id": {
        "title": "Pengaturan Kontrol & Pemetaan Tombol",
        "header": "PEMETAAN TOMBOL CONTROLLER",
        "subtitle": "Atur tombol aksi game ke tombol stik/controller sesuai kenyamanan Anda.",
        "layout_prompt": "Gaya Label Tombol:",
        "note_analog": (
            "ℹ️  Catatan: Analog Stick (gerakan/kamera) dan Trigger (L2 / R2) berjalan pada channel "
            "analog hardware dan tidak diubah di sini. Pengaturan berlaku saat game berikutnya dijalankan."
        ),
        "col_action": "Aksi Game",
        "col_binding": "Tombol Controller",
        "col_capture": "Deteksi",
        "col_reset": "Reset",
        "btn_capture": "🎮 Tekan Tombol",
        "btn_capturing": "Mendeteksi... (Esc batal)",
        "btn_reset_action": "↺ Reset",
        "btn_reset_all": "↺ Reset Semua ke Default",
        "btn_save": "💾 Simpan & Terapkan",
        "btn_cancel": "Batal",
        "swapped_notice": "Menukar '{}' dengan '{}' untuk mencegah tombol ganda.",
        "confirm_reset_title": "Reset Semua Tombol",
        "confirm_reset_msg": "Apakah Anda yakin ingin mengembalikan seluruh pemetaan tombol ke default?",
        "saved_title": "Pengaturan Disimpan",
        "saved_msg": "Pemetaan tombol controller berhasil disimpan.",
    },
}

# ---------------------------------------------------------------------------
# Pure Helpers & Specification Builder
# ---------------------------------------------------------------------------

def get_default_controls() -> Dict[str, str]:
    """Returns a fresh dictionary of all default logical pad controls."""
    return dict(DEFAULT_PAD_CONTROLS)


def validate_controls(mapping: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Validates and cleanses a pad_controls dictionary.

    Rejects unknown actions, unsupported SDL buttons, and returns canonical lowercase tokens.
    """
    if not isinstance(mapping, dict):
        return {}

    cleaned: Dict[str, str] = {}
    for action, button in mapping.items():
        if not isinstance(action, str) or not isinstance(button, str):
            continue
        act_clean = action.strip().lower()
        btn_clean = button.strip()
        # Handle 'None' case-insensitively
        if btn_clean.lower() == "none":
            btn_token = "None"
        else:
            btn_token = btn_clean.lower()

        if act_clean in VALID_ACTION_NAMES and btn_token in VALID_SDL_BUTTONS:
            cleaned[act_clean] = btn_token

    return cleaned


def diff_controls(
    current: Dict[str, str], defaults: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Returns only the button assignments that differ from defaults."""
    base = defaults or DEFAULT_PAD_CONTROLS
    diff: Dict[str, str] = {}
    for action, btn in current.items():
        if action in base and base[action] != btn:
            diff[action] = btn
    return diff


def build_pad_map_spec(mapping: Optional[Dict[str, str]]) -> str:
    """Builds the SPARTAN_PAD_MAP environment specification string (e.g. 'cross=b,circle=a').

    Returns an empty string if all bindings are at default or invalid.
    """
    if not mapping:
        return ""

    valid = validate_controls(mapping)
    changes = diff_controls(valid)
    if not changes:
        return ""

    # Sort deterministically by action list order
    action_order = {action: idx for idx, (action, *_) in enumerate(LOGICAL_ACTIONS)}
    ordered = sorted(changes.items(), key=lambda pair: action_order.get(pair[0], 99))
    return ",".join(f"{act}={btn}" for act, btn in ordered)


def bind_button(
    controls: Dict[str, str],
    target_action: str,
    new_source: str,
    swap_duplicates: bool = True,
) -> Optional[str]:
    """Assigns new_source to target_action.

    If swap_duplicates is True and new_source is already bound elsewhere (and not 'None'),
    swaps the old action with target_action's previous binding. Returns the swapped action ID if any.
    """
    if target_action not in VALID_ACTION_NAMES or new_source not in VALID_SDL_BUTTONS:
        return None

    old_source = controls.get(target_action, DEFAULT_PAD_CONTROLS.get(target_action, "None"))
    swapped_action: Optional[str] = None

    if swap_duplicates and new_source != "None":
        for other_action, other_source in list(controls.items()):
            if other_action != target_action and other_source == new_source:
                controls[other_action] = old_source
                swapped_action = other_action
                break

    controls[target_action] = new_source
    return swapped_action


def reset_button(controls: Dict[str, str], target_action: str) -> None:
    """Resets a single action back to its default binding."""
    if target_action in DEFAULT_PAD_CONTROLS:
        controls[target_action] = DEFAULT_PAD_CONTROLS[target_action]


def reset_all_controls(controls: Dict[str, str]) -> None:
    """Resets all actions back to their default bindings."""
    controls.clear()
    controls.update(DEFAULT_PAD_CONTROLS)


def format_button_label(sdl_name: str, style: str = "playstation") -> str:
    """Returns a user-friendly button name according to the specified controller style."""
    palette = BUTTON_LABELS.get(style.lower(), BUTTON_LABELS["playstation"])
    return palette.get(sdl_name, sdl_name)


# ---------------------------------------------------------------------------
# SDL3 Gamepad Hardware Capture Helper
# ---------------------------------------------------------------------------

class SDL3CaptureHelper:
    """Optional helper using bin/SDL3.dll to capture real button presses from a connected controller."""

    def __init__(self, bin_dir: Optional[Path] = None):
        self.dll = None
        self.active_pad = None
        self._init_sdl(bin_dir)

    def _init_sdl(self, bin_dir: Optional[Path]):
        cand_dirs = [bin_dir, Path("bin"), Path(__file__).resolve().parent.parent / "bin"]
        dll_path = None
        for d in cand_dirs:
            if d and (d / "SDL3.dll").is_file():
                dll_path = d / "SDL3.dll"
                break

        if not dll_path:
            return

        try:
            self.dll = ctypes.CDLL(str(dll_path.resolve()))
            self.dll.SDL_Init(0x00002000)  # SDL_INIT_GAMEPAD
            self.dll.SDL_OpenGamepad.restype = ctypes.c_void_p
            self.dll.SDL_OpenGamepad.argtypes = [ctypes.c_uint32]
            self.dll.SDL_CloseGamepad.argtypes = [ctypes.c_void_p]
            self.dll.SDL_GetGamepadButton.restype = ctypes.c_bool
            self.dll.SDL_GetGamepadButton.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self.dll.SDL_GetGamepadStringForButton.restype = ctypes.c_char_p
            self.dll.SDL_GetGamepadStringForButton.argtypes = [ctypes.c_int]
            self.dll.SDL_GetGamepads.restype = ctypes.POINTER(ctypes.c_uint32)
        except Exception:
            self.dll = None

    def poll_pressed_button(self) -> Optional[str]:
        """Polls connected controllers. Returns canonical SDL button token if pressed, else None."""
        if not self.dll:
            return None

        try:
            self.dll.SDL_UpdateJoysticks()
            count = ctypes.c_int(0)
            ids = self.dll.SDL_GetGamepads(ctypes.byref(count))
            if not ids or count.value <= 0:
                return None

            pad = self.dll.SDL_OpenGamepad(ids[0])
            if not pad:
                return None

            detected = None
            for b in range(21):
                if self.dll.SDL_GetGamepadButton(pad, b):
                    raw_str = self.dll.SDL_GetGamepadStringForButton(b)
                    if raw_str:
                        detected = raw_str.decode("utf-8", errors="ignore")
                        break

            self.dll.SDL_CloseGamepad(pad)
            return detected
        except Exception:
            return None

    def close(self):
        # We leave SDL cleanup to process exit to avoid interfering with runtime
        pass


# ---------------------------------------------------------------------------
# Controller Controls GUI Window
# ---------------------------------------------------------------------------

class ControllerControlsWindow(tk.Toplevel):
    """Tkinter window for viewing, customizing, capturing, and saving controller bindings."""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        current_controls: Optional[Dict[str, str]] = None,
        pad_style: str = "playstation",
        language: str = "en",
        on_save_callback: Optional[Callable[[Dict[str, str], str], None]] = None,
        bin_dir: Optional[Path] = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.on_save_callback = on_save_callback
        self.lang = "id" if (language or "en").lower().startswith("id") else "en"
        self.pad_style = pad_style if pad_style in BUTTON_LABELS else "playstation"

        # Working copy of controls: start with defaults, overlay current user settings
        self.controls: Dict[str, str] = get_default_controls()
        if current_controls:
            self.controls.update(validate_controls(current_controls))

        self.capture_helper = SDL3CaptureHelper(bin_dir)
        self.capturing_action: Optional[str] = None
        self.row_widgets: Dict[str, Dict[str, tk.Widget]] = {}

        # Colors matching Sumeragi dark theme
        self.bg = "#12100e"
        self.panel = "#1c1916"
        self.card_bg = "#221e1a"
        self.fg = "#eadfcb"
        self.muted = "#8d8374"
        self.gold = "#c9a24a"
        self.gold_bright = "#f3cc69"
        self.btn_bg = "#2a251f"

        self.configure(bg=self.bg)
        self.minsize(720, 560)
        self.geometry("780x640")
        self._center()

        self._build_ui()
        self.bind("<Escape>", self._on_escape)

    def _t(self, key: str) -> str:
        return UI_TEXTS[self.lang].get(key, key)

    def _center(self):
        self.update_idletasks()
        try:
            pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
            px, py = self.parent.winfo_rootx(), self.parent.winfo_rooty()
            w, h = 780, 640
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.geometry("780x640")

    def _build_ui(self):
        for widget in self.winfo_children():
            widget.destroy()

        self.title(self._t("title"))

        # Top Bar
        top = tk.Frame(self, bg=self.panel, padx=16, pady=12)
        top.pack(fill="x", side="top")

        # Row 1: Header + Language
        r1 = tk.Frame(top, bg=self.panel)
        r1.pack(fill="x", pady=(0, 4))
        tk.Label(
            r1,
            text=f"🎮  {self._t('header')}",
            bg=self.panel,
            fg=self.gold,
            font=("Georgia", 13, "bold"),
        ).pack(side="left")

        lang_btn = tk.Button(
            r1,
            text=f"🌐 {'ID' if self.lang == 'en' else 'EN'}",
            bg=self.btn_bg,
            fg=self.fg,
            activebackground="#3d362e",
            activeforeground=self.gold,
            bd=0,
            padx=8,
            pady=3,
            font=("Segoe UI", 8, "bold"),
            command=self._toggle_language,
        )
        lang_btn.pack(side="right")

        # Row 2: Subtitle + Style selector
        r2 = tk.Frame(top, bg=self.panel)
        r2.pack(fill="x", pady=(0, 6))
        tk.Label(
            r2,
            text=self._t("subtitle"),
            bg=self.panel,
            fg=self.muted,
            font=("Segoe UI", 9),
        ).pack(side="left")

        style_frame = tk.Frame(r2, bg=self.panel)
        style_frame.pack(side="right")
        tk.Label(
            style_frame,
            text=self._t("layout_prompt"),
            bg=self.panel,
            fg=self.fg,
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=(0, 6))

        self.style_var = tk.StringVar(value=self.pad_style.capitalize())
        style_combo = ttk.Combobox(
            style_frame,
            textvariable=self.style_var,
            values=["PlayStation", "Xbox", "Nintendo"],
            state="readonly",
            width=12,
        )
        style_combo.pack(side="left")
        style_combo.bind("<<ComboboxSelected>>", self._on_style_changed)

        # Notice Banner regarding Analog Axis limitations
        banner = tk.Frame(self, bg="#271c14", padx=12, pady=8, bd=1, relief="ridge")
        banner.pack(fill="x", padx=16, pady=(10, 6))
        tk.Label(
            banner,
            text=self._t("note_analog"),
            bg="#271c14",
            fg="#e5b87c",
            wraplength=730,
            justify="left",
            font=("Segoe UI", 8, "italic"),
        ).pack(anchor="w")

        # Scrollable table container
        table_container = tk.Frame(self, bg=self.bg)
        table_container.pack(fill="both", expand=True, padx=16, pady=4)

        canvas = tk.Canvas(table_container, bg=self.bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=self.bg)

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        self.canvas_window = canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self.canvas_window, width=e.width),
        )

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Populate Action Rows
        self.row_widgets.clear()
        for idx, (action_id, default_btn, lbl_en, lbl_id, desc_en, desc_id) in enumerate(LOGICAL_ACTIONS):
            label_text = lbl_id if self.lang == "id" else lbl_en
            desc_text = desc_id if self.lang == "id" else desc_en
            self._create_action_row(idx, action_id, default_btn, label_text, desc_text)

        # Bottom Bar
        bottom = tk.Frame(self, bg=self.panel, padx=16, pady=12)
        bottom.pack(fill="x", side="bottom")

        btn_reset_all = tk.Button(
            bottom,
            text=self._t("btn_reset_all"),
            bg="#362a22",
            fg="#f0a89d",
            activebackground="#4a362a",
            activeforeground="#ffb4a6",
            bd=0,
            padx=12,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            command=self._on_reset_all,
        )
        btn_reset_all.pack(side="left")

        btn_save = tk.Button(
            bottom,
            text=self._t("btn_save"),
            bg=self.gold,
            fg="#14120f",
            activebackground=self.gold_bright,
            activeforeground="#14120f",
            bd=0,
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            command=self._on_save,
        )
        btn_save.pack(side="right", padx=(8, 0))

        btn_cancel = tk.Button(
            bottom,
            text=self._t("btn_cancel"),
            bg=self.btn_bg,
            fg=self.fg,
            activebackground="#3d362e",
            activeforeground=self.fg,
            bd=0,
            padx=12,
            pady=6,
            font=("Segoe UI", 9),
            command=self.destroy,
        )
        btn_cancel.pack(side="right")

    def _create_action_row(
        self,
        idx: int,
        action_id: str,
        default_btn: str,
        label_text: str,
        desc_text: str,
    ):
        card = tk.Frame(
            self.scroll_frame,
            bg=self.card_bg,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground="#2f2923",
        )
        card.pack(fill="x", pady=2)
        card.columnconfigure(0, weight=2)
        card.columnconfigure(1, weight=3)

        # Left: Action info
        left_box = tk.Frame(card, bg=self.card_bg)
        left_box.grid(row=0, column=0, sticky="w")
        tk.Label(
            left_box,
            text=label_text,
            bg=self.card_bg,
            fg=self.gold_bright,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            left_box,
            text=desc_text,
            bg=self.card_bg,
            fg=self.muted,
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        # Right: Binding Dropdown + Capture Button + Reset Button
        right_box = tk.Frame(card, bg=self.card_bg)
        right_box.grid(row=0, column=1, sticky="e")

        # Dropdown values
        available_buttons = [
            "a", "b", "x", "y", "leftshoulder", "rightshoulder",
            "leftstick", "rightstick", "start", "back", "guide",
            "dpup", "dpdown", "dpleft", "dpright", "touchpad",
            "misc1", "paddle1", "paddle2", "paddle3", "paddle4", "None",
        ]
        display_choices = [
            format_button_label(btn, self.pad_style) for btn in available_buttons
        ]

        current_btn = self.controls.get(action_id, default_btn)
        combo_var = tk.StringVar(value=format_button_label(current_btn, self.pad_style))

        combo = ttk.Combobox(
            right_box,
            textvariable=combo_var,
            values=display_choices,
            state="readonly",
            width=24,
        )
        combo.pack(side="left", padx=(0, 6))

        # Handle user choosing an item from dropdown
        def on_combo_select(event=None):
            sel_text = combo_var.get()
            # Resolve display text back to canonical SDL token
            for btn_token in available_buttons:
                if format_button_label(btn_token, self.pad_style) == sel_text:
                    swapped = bind_button(self.controls, action_id, btn_token, swap_duplicates=True)
                    if swapped:
                        self._refresh_row(swapped)
                    self._refresh_row(action_id)
                    break

        combo.bind("<<ComboboxSelected>>", on_combo_select)

        # Capture Button
        cap_btn = tk.Button(
            right_box,
            text=self._t("btn_capture"),
            bg="#2c2620",
            fg=self.fg,
            activebackground="#3e352c",
            activeforeground=self.gold,
            bd=0,
            padx=8,
            pady=3,
            font=("Segoe UI", 8),
            command=lambda: self._start_capture(action_id),
        )
        cap_btn.pack(side="left", padx=(0, 4))

        # Reset row button
        reset_btn = tk.Button(
            right_box,
            text=self._t("btn_reset_action"),
            bg="#241f1a",
            fg=self.muted,
            activebackground="#332b24",
            activeforeground=self.fg,
            bd=0,
            padx=6,
            pady=3,
            font=("Segoe UI", 8),
            command=lambda: self._reset_action(action_id),
        )
        reset_btn.pack(side="left")

        self.row_widgets[action_id] = {
            "card": card,
            "combo": combo,
            "combo_var": combo_var,
            "cap_btn": cap_btn,
            "available_buttons": available_buttons,
        }

    def _refresh_row(self, action_id: str):
        if action_id not in self.row_widgets:
            return
        w = self.row_widgets[action_id]
        current_btn = self.controls.get(action_id, DEFAULT_PAD_CONTROLS.get(action_id, "None"))
        w["combo_var"].set(format_button_label(current_btn, self.pad_style))

        # Highlight card if customized
        is_custom = current_btn != DEFAULT_PAD_CONTROLS.get(action_id)
        border_col = self.gold if is_custom else "#2f2923"
        w["card"].configure(highlightbackground=border_col)

    def _refresh_all_rows(self):
        for action_id in self.row_widgets:
            self._refresh_row(action_id)

    def _start_capture(self, action_id: str):
        if self.capturing_action:
            self._stop_capture()

        self.capturing_action = action_id
        if action_id in self.row_widgets:
            btn = self.row_widgets[action_id]["cap_btn"]
            btn.configure(
                text=self._t("btn_capturing"),
                bg=self.gold,
                fg="#14120f",
                font=("Segoe UI", 8, "bold"),
            )
        self._poll_capture()

    def _poll_capture(self):
        if not self.capturing_action:
            return

        detected = self.capture_helper.poll_pressed_button()
        if detected:
            action_id = self.capturing_action
            swapped = bind_button(self.controls, action_id, detected, swap_duplicates=True)
            self._stop_capture()
            if swapped:
                self._refresh_row(swapped)
            self._refresh_row(action_id)
            return

        # Poll again in 35ms
        self.after(35, self._poll_capture)

    def _stop_capture(self):
        if not self.capturing_action:
            return
        action_id = self.capturing_action
        self.capturing_action = None
        if action_id in self.row_widgets:
            btn = self.row_widgets[action_id]["cap_btn"]
            btn.configure(
                text=self._t("btn_capture"),
                bg="#2c2620",
                fg=self.fg,
                font=("Segoe UI", 8),
            )

    def _reset_action(self, action_id: str):
        self._stop_capture()
        reset_button(self.controls, action_id)
        self._refresh_row(action_id)

    def _on_reset_all(self):
        self._stop_capture()
        if messagebox.askyesno(
            self._t("confirm_reset_title"),
            self._t("confirm_reset_msg"),
            parent=self,
        ):
            reset_all_controls(self.controls)
            self._refresh_all_rows()

    def _on_style_changed(self, event=None):
        self.pad_style = self.style_var.get().lower()
        self._stop_capture()
        # Re-build UI to update combo display strings
        self._build_ui()
        self._refresh_all_rows()

    def _toggle_language(self):
        self._stop_capture()
        self.lang = "id" if self.lang == "en" else "en"
        self._build_ui()
        self._refresh_all_rows()

    def _on_escape(self, event=None):
        if self.capturing_action:
            self._stop_capture()
        else:
            self.destroy()

    def _on_save(self):
        self._stop_capture()
        clean_controls = validate_controls(self.controls)
        if self.on_save_callback:
            try:
                self.on_save_callback(clean_controls, self.pad_style)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings: {e}", parent=self)
                return

        messagebox.showinfo(self._t("saved_title"), self._t("saved_msg"), parent=self)
        self.destroy()
