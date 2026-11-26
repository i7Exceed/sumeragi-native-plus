#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed (based on Basara 4 PC by Razz).
"""Sumeragi Native+ Launcher - Modular Application Shell.

Runs Sengoku Basara 4 Sumeragi (PS4, CUSA01159) on the native PC runtime in bin\\ (sumeragi-core.exe / basara4-core.exe),
a fork of SpartanPort. Free software under the GNU GPL v2 or later; credits and licenses are in NOTICE.md.

Everything lives next to this program:
  bin\\   the runtime (sumeragi-core.exe / basara4-core.exe) and its DLLs
  game\\  the game dump (the folder with eboot.bin); another folder can be chosen
  update\\ optional extracted PS4 update directory (e.g. v1.02)
  dlc\\   optional extracted add-on content folders (auto-detected)
  out\\   the prepared game image, made automatically from eboot.bin
  user\\  saves, shader cache, settings, logs
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure launcher and scripts are in sys.path
LAUNCHER_DIR = Path(__file__).resolve().parent
ROOT = (Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__)).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(LAUNCHER_DIR) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_DIR))

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageTk
except ImportError:
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageTk = None

# Modular subsystem imports and re-exports for complete backward compatibility
import sumeragi_patches as patches_module
import sumeragi_cheats as cheats_module
from sumeragi_config import ACTION_DESCRIPTIONS, DEFAULT_PC_KEYMAP
from sumeragi_config import (
    ANCIENT_INI,
    ANISO,
    DEFAULT_PC_KEYMAP,
    check_commit_limit_mb,
    AUDIO_LOG,
    AUDIO_WAV,
    AUTHOR,
    AUTHOR_URL,
    AVAILABLE_SDL_BUTTONS,
    BG,
    BIN,
    BRAND,
    CONFIG,
    CORE,
    DEFAULTS,
    DISPLAY_MODES,
    FG,
    FPS_LIMITS,
    FROZEN,
    GOLD,
    INI,
    LOG,
    MAPPING,
    MUTED,
    NO_WINDOW,
    OLD_INI,
    OUT,
    PANEL,
    PIPELINE,
    PREPARE_LOG,
    RAZZ,
    RED,
    RESOLUTIONS,
    ROOT,
    SCRIPTS,
    STAMP,
    TAGLINE,
    TROPHY_FILTERS,
    UPSCALERS,
    USER,
    VERSION,
    WAV_WARNING,
    WINDOW_ICON,
    find_dlc,
    find_game,
    load_config,
    read_ini,
    resolve_enabled_mods,
    resolve_mod_path,
    save_config,
    write_ini,
)
from sumeragi_crash import (
    CRASH_GUIDES,
    CRASH_SIGNATURES,
    SumeragiCrashDialog,
    analyze_crash_log,
)
from sumeragi_gpu import (
    SYSTEM_GPUS,
    VULKAN,
    enumerate_vulkan_gpus,
    game_gpu_id,
    resolve_spartan_gpu_id,
    vulkan_problem,
    vulkan_warning,
)
import sumeragi_i18n as i18n
from sumeragi_i18n import t
from sumeragi_pages import PAGES, PagesMixin
from sumeragi_pipeline import (
    file_sha256,
    format_size,
    image_ready,
    input_files_stamp,
    prepare_image,
    run_script_mode,
    wav_captures,
)
import sumeragi_theme as theme

# Auxiliary game packages
import dlc
import game_update
from patches import find_sfo, game_app_ver, game_title_id
import sumeragi_controller_controls as controls_module
from sumeragi_controller_controls import (
    ControllerControlsWindow,
    build_pad_map_spec,
    validate_controls,
)
import sumeragi_native_trophies as trophies_module
from sumeragi_native_trophies import TrophiesWindow
import sumeragi_patches as patches_module
import sumeragi_cheats as cheats_module
from sumeragi_config import ACTION_DESCRIPTIONS, DEFAULT_PC_KEYMAP

# CLI Hook for helper scripts
if len(sys.argv) > 2 and sys.argv[1] == "--run-script":
    run_script_mode()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main Application Shell
# ---------------------------------------------------------------------------


def build_mod_entries(
    cfg: Dict[str, Any],
    mods_dir: Optional[str | Path] = None,
    extra_mods: Optional[List[str]] = None,
    base: Optional[str | Path] = None,
    update: Optional[str | Path] = None,
    out: Optional[str | Path] = None,
) -> List[Dict[str, Any]]:
    """Builds the ordered mod list for the Mod Manager UI, preserving enabled_mods order."""
    active_mods_dir = str(mods_dir if mods_dir is not None else (cfg.get("mods_dir") or (ROOT / "mods")))
    extras = list(extra_mods if extra_mods is not None else cfg.get("extra_mods", []))
    enabled_paths = [
        resolve_mod_path(entry, active_mods_dir)
        for entry in (cfg.get("enabled_mods") or [])
        if isinstance(entry, str) and entry.strip()
    ]
    combined_extras = list(extras)
    for ep in enabled_paths:
        combined_extras.append(str(ep))

    discovered = game_update.discover_mods(
        active_mods_dir,
        extra_mods=combined_extras,
        base=base,
        update=update,
        out=out,
    )
    by_key: Dict[str, Dict[str, Any]] = {}
    for item in discovered:
        key = os.path.normcase(os.path.normpath(str(item["path"])))
        by_key[key] = dict(item, enabled=False)

    ordered: List[Dict[str, Any]] = []
    used_keys: Set[str] = set()
    for ep in enabled_paths:
        resolved = ep.resolve() if ep.exists() else ep
        key = os.path.normcase(os.path.normpath(str(resolved)))
        if key in used_keys:
            continue
        if key in by_key:
            entry = by_key[key]
            entry["enabled"] = True
            ordered.append(entry)
            used_keys.add(key)

    for item in discovered:
        key = os.path.normcase(os.path.normpath(str(item["path"])))
        if key not in used_keys:
            ordered.append(by_key[key])
            used_keys.add(key)
    return ordered


def move_mod_entry(entries: List[Dict[str, Any]], index: int, delta: int) -> bool:
    """Moves a mod entry up (-1) or down (+1) in the list."""
    target = index + delta
    if not (0 <= index < len(entries) and 0 <= target < len(entries)):
        return False
    entries[index], entries[target] = entries[target], entries[index]
    return True


class Launcher(PagesMixin, tk.Tk):
    """Modern Dark Sengoku-Tech Desktop Launcher for Sumeragi Native+."""

    def __init__(self, play_now: bool = False):
        super().__init__()
        self.cfg = load_config()
        self.proc: Optional[subprocess.Popen] = None
        self.busy = False
        self.pending: Any = None
        self.play_now = play_now
        self.update_view: Optional[Path] = None
        self.user_stopped = False
        self.current_page = "home"
        self.page_frames: Dict[str, tk.Frame] = {}
        self.nav_buttons: Dict[str, tk.Widget] = {}

        self._cleanup_leftover_views()
        self.title(f"{BRAND}  ·  {TAGLINE}")
        self.geometry("1100x700")
        self.minsize(980, 600)
        self.configure(bg=theme.BG_MAIN)

        # Set application icon
        icon = LAUNCHER_DIR / "sumeragi.ico"
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

        # Apply Dark Sengoku-Tech theme
        theme.apply_theme(self)

        # Subscribe to dynamic language changes
        i18n.on_language_change(self._on_language_changed)

        # Embedded Trophy System State
        self.current_trophies: List[Dict[str, Any]] = []
        self.trophy_icons_raw: Dict[int, bytes] = {}
        self.trophy_photo_cache: Dict[str, Any] = {}
        self.tr_filter_key = "all"
        try:
            trophies_module.sync_trophy_texts_file(USER, language=self.cfg.get("language", "en"))
        except Exception:
            pass

        # Embedded Controller Remapping State
        self.ctrl_controls: Dict[str, str] = dict(controls_module.DEFAULT_PAD_CONTROLS)
        if self.cfg.get("pad_controls"):
            self.ctrl_controls.update(controls_module.validate_controls(self.cfg.get("pad_controls", {})))
        self.ctrl_style_var = tk.StringVar(value=(self.cfg.get("pad_style") or "playstation").capitalize())
        self.input_mode_var = tk.StringVar(value=self.cfg.get("input_mode", "controller"))
        self.ctrl_capture_helper: Any = None
        self.ctrl_capturing_action: Optional[str] = None
        self.ctrl_capture_timer: Any = None
        self.ctrl_row_combos: Dict[str, ttk.Combobox] = {}
        self.ctrl_row_combo_vars: Dict[str, tk.StringVar] = {}
        self.ctrl_row_cap_btns: Dict[str, ttk.Button] = {}
        self.ctrl_row_title_lbls: Dict[str, tk.Label] = {}
        self.ctrl_row_desc_lbls: Dict[str, tk.Label] = {}

        # Setup art & build shell
        self._art()
        self._build_shell()
        self._load_ini_into_ui()
        self._refresh_all_statuses()

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(500, self._poll)

        if play_now:
            self.iconify()
            self.after(300, self.on_play)
        else:
            self.after(700, self._check_wav_leftovers)

    # -----------------------------------------------------------------------
    # Artwork & Assets
    # -----------------------------------------------------------------------

    def _art(self):
        self.cover = self.bg_img = None
        game_path = self.cfg.get("game")
        if Image is None or ImageTk is None or ImageEnhance is None or ImageFilter is None or not game_path:
            return

        update_path = self.cfg.get("update_dir")
        sys_dir = None
        if update_path:
            for cand in (Path(update_path) / "sce_sys", Path(update_path) / "SCE_SYS"):
                if (cand / "icon0.png").is_file():
                    sys_dir = cand
                    break
        if not sys_dir:
            for cand in (Path(game_path) / "sce_sys", Path(game_path) / "SCE_SYS"):
                if (cand / "icon0.png").is_file():
                    sys_dir = cand
                    break
        if not sys_dir:
            sys_dir = Path(game_path) / "sce_sys"

        try:
            icon_file = sys_dir / "icon0.png"
            if icon_file.is_file():
                self.cover = ImageTk.PhotoImage(Image.open(icon_file).convert("RGB").resize((160, 160)), master=self)
        except Exception:
            self.cover = None

    # -----------------------------------------------------------------------
    # Shell & Navigation Structure
    # -----------------------------------------------------------------------

    def _build_shell(self):
        # Master layout container
        self.shell = tk.Frame(self, bg=theme.BG_MAIN)
        self.shell.pack(fill="both", expand=True)

        # Left Sidebar (Fixed 230px)
        self.sidebar = tk.Frame(self.shell, bg=theme.BG_SIDEBAR, width=230)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Right Content Area
        self.content_container = tk.Frame(self.shell, bg=theme.BG_MAIN)
        self.content_container.pack(side="right", fill="both", expand=True)

        # Build Sidebar Contents
        self._build_sidebar()

        # Build Content Pages
        self._build_pages()

        # Show initial page
        self.show_page("home")

    def _build_sidebar(self):
        # Top Brand & Title
        header_box = tk.Frame(self.sidebar, bg=theme.BG_SIDEBAR, padx=16, pady=18)
        header_box.pack(fill="x")

        brand_lbl = tk.Label(header_box, text=BRAND.upper(), bg=theme.BG_SIDEBAR, fg=theme.ACCENT_GOLD, font=("Georgia", 13, "bold"))
        brand_lbl.pack(anchor="w")

        self.tagline_lbl = tk.Label(header_box, text=t("app.tagline"), bg=theme.BG_SIDEBAR, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION)
        self.tagline_lbl.pack(anchor="w", pady=(2, 0))

        # Thin divider
        tk.Frame(self.sidebar, bg=theme.BORDER_SUBTLE, height=1).pack(fill="x", padx=14, pady=(0, 12))

        # Navigation Menu List
        self.nav_menu_frame = tk.Frame(self.sidebar, bg=theme.BG_SIDEBAR)
        self.nav_menu_frame.pack(fill="x", padx=10)

        nav_items = [
            ("home", "🏠", "nav.home"),
            ("game_files", "📁", "nav.game_files"),
            ("updates", "🔄", "nav.updates"),
            ("dlc", "📦", "nav.dlc"),
            ("trophies", "🏆", "nav.trophies"),
            ("controls", "🎮", "nav.controls"),
            ("settings", "⚙️", "nav.settings"),
            ("diagnostics", "📋", "nav.diagnostics"),
        ]

        self.nav_items_meta = nav_items

        for page_id, icon, key in nav_items:
            btn = self._create_nav_button(page_id, icon, t(key))
            btn.pack(fill="x", pady=2)
            self.nav_buttons[page_id] = btn

        # Bottom Sidebar Footer
        footer = tk.Frame(self.sidebar, bg=theme.BG_SIDEBAR, padx=14, pady=14)
        footer.pack(side="bottom", fill="x")

        tk.Frame(self.sidebar, bg=theme.BORDER_SUBTLE, height=1).pack(side="bottom", fill="x", padx=14, pady=(0, 8))

        self.sidebar_target_lbl = tk.Label(footer, text=t("app.target"), bg=theme.BG_SIDEBAR, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION)
        self.sidebar_target_lbl.pack(anchor="w")

        self.sidebar_ver_lbl = tk.Label(footer, text=f"v{VERSION}  ·  CUSA01159", bg=theme.BG_SIDEBAR, fg=theme.TEXT_MUTED, font=theme.FONT_BADGE)
        self.sidebar_ver_lbl.pack(anchor="w", pady=(1, 6))

        self.btn_credits = ttk.Button(footer, text=t("app.credits"), style="Small.TButton", command=self.show_credits)
        self.btn_credits.pack(fill="x")

    def _create_nav_button(self, page_id: str, icon: str, label_text: str) -> tk.Frame:
        """Creates a modern sidebar button with an active accent indicator."""
        frame = tk.Frame(self.nav_menu_frame, bg=theme.BG_SIDEBAR, cursor="hand2")
        frame.columnconfigure(1, weight=1)

        # Left indicator bar
        bar = tk.Frame(frame, bg=theme.BG_SIDEBAR, width=3)
        bar.pack(side="left", fill="y")

        lbl = tk.Label(
            frame,
            text=f"  {icon}  {label_text}",
            bg=theme.BG_SIDEBAR,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY,
            anchor="w",
            padx=8,
            pady=8,
        )
        lbl.pack(side="left", fill="both", expand=True)

        def on_click(_event=None):
            self.show_page(page_id)

        def on_enter(_event=None):
            if self.current_page != page_id:
                frame.configure(bg=theme.BG_ELEVATED)
                lbl.configure(bg=theme.BG_ELEVATED, fg=theme.TEXT_PRIMARY)

        def on_leave(_event=None):
            if self.current_page != page_id:
                frame.configure(bg=theme.BG_SIDEBAR)
                lbl.configure(bg=theme.BG_SIDEBAR, fg=theme.TEXT_SECONDARY)

        for w in (frame, lbl):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        frame._bar = bar  # type: ignore[attr-defined]
        frame._lbl = lbl  # type: ignore[attr-defined]
        frame._icon = icon  # type: ignore[attr-defined]
        frame._key = next(k for pid, _, k in self.nav_items_meta if pid == page_id)  # type: ignore[attr-defined]
        return frame

    def show_page(self, page_id: str):
        """Switches the active content view without destroying widgets."""
        if page_id not in self.page_frames:
            return

        self.current_page = page_id

        # Update sidebar active states
        for pid, frame in self.nav_buttons.items():
            if pid == page_id:
                frame.configure(bg=theme.BG_CARD)
                frame._bar.configure(bg=theme.ACCENT_GOLD)  # type: ignore[attr-defined]
                frame._lbl.configure(bg=theme.BG_CARD, fg=theme.ACCENT_GOLD_HOVER, font=theme.FONT_BODY_BOLD)  # type: ignore[attr-defined]
            else:
                frame.configure(bg=theme.BG_SIDEBAR)
                frame._bar.configure(bg=theme.BG_SIDEBAR)  # type: ignore[attr-defined]
                frame._lbl.configure(bg=theme.BG_SIDEBAR, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)  # type: ignore[attr-defined]

        # Hide other page frames and display active
        for pid, pframe in self.page_frames.items():
            if pid == page_id:
                pframe.pack(fill="both", expand=True)
                if hasattr(pframe, "on_show"):
                    pframe.on_show()
            else:
                pframe.pack_forget()

    # -----------------------------------------------------------------------
    # Backend Launch Lifecycle & Environment Construction
    # -----------------------------------------------------------------------

    def _cleanup_leftover_views(self):
        view_roots = [OUT]
        game = self.cfg.get("game") if hasattr(self, "cfg") else None
        if game:
            try:
                view_roots.append(Path(game).resolve().parent / ".sumeragi-overlay")
            except OSError:
                pass
        for root_dir in view_roots:
            if not root_dir.is_dir():
                continue
            for item in list(root_dir.iterdir()):
                if item.is_dir() and item.name.startswith("game-update-"):
                    try:
                        game_update.remove_view(item)
                    except Exception:
                        pass

    def _ini(self):
        if not INI.exists():
            if OLD_INI.exists():
                try:
                    shutil.copy2(OLD_INI, INI)
                except OSError:
                    pass
            elif ANCIENT_INI.exists():
                try:
                    shutil.copy2(ANCIENT_INI, INI)
                except OSError:
                    pass
        return INI

    def _load_ini_into_ui(self):
        ini = read_ini(self._ini())
        mode = ini.get("display_mode", self.cfg.get("display_mode", "borderless"))
        if mode in {k for _, k in DISPLAY_MODES}:
            self.mode_var.set(mode)
        if "vsync" in ini:
            self.vsync_var.set(ini["vsync"] == "1")
        if "rcas" in ini:
            self.rcas_var.set(ini["rcas"] == "1")
        res = ini.get("render_resolution", self.cfg.get("resolution", "native"))
        self.res_var.set(next((n for n, v in RESOLUTIONS if v == res), RESOLUTIONS[0][0]))
        fsr = ini.get("fsr1")
        up = ("fsr1" if fsr == "1" else "off") if fsr is not None else self.cfg.get("upscale", "off")
        self.up_var.set(next((n for n, v in UPSCALERS if v == up), UPSCALERS[0][0]))
        fps = int(self.cfg.get("fps_limit", 60))
        self.fps_var.set(next((n for n, v in FPS_LIMITS if v == fps), FPS_LIMITS[0][0]))
        an = int(ini["anisotropy"]) if ini.get("anisotropy", "").isdigit() else self.cfg.get("anisotropy", 0)
        self.aniso_var.set(next((n for n, v in ANISO if v == an), "Off"))
        saved_gpu = self.cfg.get("gpu_index", -1)
        self.gpu_var.set(next((name for idx, name, _ in SYSTEM_GPUS if idx == saved_gpu), SYSTEM_GPUS[0][1]))

    def _audio_toggled(self):
        if not self.audio_var.get():
            self.wav_var.set(False)

    def _wav_toggled(self):
        if not self.wav_var.get():
            return
        if messagebox.askyesno(t("dialog.wav_warning_title"), t("dialog.wav_warning_msg"), icon="warning", default="no", parent=self):
            self.audio_var.set(True)
        else:
            self.wav_var.set(False)

    def _check_wav_leftovers(self):
        files, total = wav_captures()
        if not files or total < 50 * 2**20:
            return
        if messagebox.askyesno(
            t("dialog.wav_leftover_title"),
            t("dialog.wav_leftover_msg", size=format_size(total), count=len(files)),
            default="no",
            parent=self,
        ):
            for f in files:
                try:
                    f.unlink()
                except OSError:
                    pass

    def _pad_text(self):
        """Kept for backward compatibility with existing tests."""
        self._refresh_home_status()
        self._refresh_controls_page()

    def _collect(self):
        name_to_code = {v: k for k, v in i18n.SUPPORTED_LANGUAGES.items()}
        current_lang = name_to_code.get(self.lang_var.get(), self.cfg.get("language", "en"))
        self.cfg["language"] = current_lang
        self.cfg.update(
            game=self.game_var.get().strip() if hasattr(self, "game_var") else self.cfg.get("game", ""),
            update_dir=self.update_var.get().strip() if hasattr(self, "update_var") else self.cfg.get("update_dir", ""),
            dlc_dir=self.dlc_var.get().strip() if hasattr(self, "dlc_var") else self.cfg.get("dlc_dir", ""),
            display_mode=self.mode_var.get(),
            vsync=self.vsync_var.get(),
            rcas=self.rcas_var.get(),
            fps_limit=dict(FPS_LIMITS)[self.fps_var.get()],
            resolution=dict(RESOLUTIONS)[self.res_var.get()],
            upscale=dict(UPSCALERS)[self.up_var.get()],
            anisotropy=dict(ANISO)[self.aniso_var.get()],
            audio_log=self.audio_var.get(),
            audio_wav=self.audio_var.get() and self.wav_var.get(),
            input_mode=self.input_mode_var.get() if hasattr(self, "input_mode_var") else self.cfg.get("input_mode", "controller"),
        )
        if hasattr(self, "gpu_var"):
            selected_gpu_name = self.gpu_var.get()
            selected_gpu_idx = next((idx for idx, name, _ in SYSTEM_GPUS if name == selected_gpu_name), -1)
            self.cfg["gpu_index"] = selected_gpu_idx
        save_config(self.cfg)
        write_ini(
            self._ini(),
            {
                "display_mode": self.cfg["display_mode"],
                "vsync": int(self.cfg["vsync"]),
                "fps_limit": self.cfg["fps_limit"],
                "rcas": int(self.cfg["rcas"]),
                "anisotropy": self.cfg["anisotropy"],
                "render_resolution": self.cfg["resolution"],
                "fsr1": int(self.cfg["upscale"] == "fsr1"),
                "gpu_id": self.cfg.get("gpu_index", -1),
            },
        )

    def _env(self):
        env = os.environ.copy()
        env.pop("SPARTAN_PAD_MAP", None)  # Prevent inherited environment variable leakage
        env["PATH"] = str(BIN) + os.pathsep + env.get("PATH", "")
        env["SPARTAN_USER_DIR"] = str(USER.resolve())
        env["SPARTAN_GPU_USER_DIR"] = str(USER.resolve())
        env["SPARTAN_CONFIG"] = str(self._ini())
        env["SPARTAN_WINDOW_TITLE"] = f"Sengoku Basara 4 Sumeragi - {BRAND} by {AUTHOR}"
        if WINDOW_ICON.exists():
            env["SPARTAN_WINDOW_ICON"] = str(WINDOW_ICON)
        if MAPPING.exists():
            env["SDL_GAMECONTROLLERCONFIG_FILE"] = str(MAPPING)
        pad_spec = build_pad_map_spec(self.cfg.get("pad_controls"))
        if pad_spec:
            env["SPARTAN_PAD_MAP"] = pad_spec
        if self.cfg.get("audio_log"):
            env["SPARTAN_AUDIO_DEBUG"] = str(USER.resolve() / "audio_debug.log")
        if self.cfg.get("audio_log") and self.cfg.get("audio_wav"):
            env["SPARTAN_AUDIO_WAV_DIR"] = str(USER.resolve() / "audio_wav")
        if self.cfg.get("fps_limit", 60) != 60:
            env["SPARTAN_VBLANK_HZ"] = "0"
            env["SPARTAN_FPS_LIMIT"] = str(self.cfg["fps_limit"])
        gpu_id_str = resolve_spartan_gpu_id(self.cfg.get("gpu_index", -1))
        if gpu_id_str is not None:
            env["SPARTAN_GPU_ID"] = gpu_id_str
        else:
            env.pop("SPARTAN_GPU_ID", None)

        # Dynamic memory commit scaling for 8GB RAM / commit limits (prevent Error 1455)
        avail_mb = check_commit_limit_mb()
        if avail_mb is not None and avail_mb < 3200:
            env["SPARTAN_DMEM_MB"] = "2048"
        elif avail_mb is not None and avail_mb < 4608:
            env["SPARTAN_DMEM_MB"] = "2560"

        # Keyboard & Mouse Control Mapping
        user_keymap = dict(DEFAULT_PC_KEYMAP)
        user_keymap.update(self.cfg.get("keymap", {}))
        spec_parts = [f"{btn}={src}" for btn, src in user_keymap.items() if src]
        if spec_parts:
            env["SPARTAN_KEY_MAP"] = ",".join(spec_parts)

        # Native Mouse Look & Camera
        if self.cfg.get("mouse_camera", True):
            env["SPARTAN_MOUSE_LOCK"] = "1"
            env["SPARTAN_MOUSE_AIM_STYLE"] = "0"
            sens = int(self.cfg.get("mouse_sens", 100))
            env["SPARTAN_MOUSE_AIM_SENSITIVITY"] = str(sens)

        # Input Mode: "controller" (standard) or "kbm_coop" (2P hybrid)
        env["SPARTAN_INPUT_MODE"] = str(self.cfg.get("input_mode", "controller"))

        # Internal 3D render resolution scaling for potato PCs (sub-1080p only)
        res = self.cfg.get("resolution", "native")
        w, h = patches_module.RESOLUTION_SIZES.get(res, (1920, 1080))
        if w < 1920 and h < 1080:
            env["SPARTAN_RENDER_RES"] = f"{w}x{h}"
        else:
            env.pop("SPARTAN_RENDER_RES", None)

        # Render debug trace opt-in
        if self.cfg.get("render_trace"):
            env["SPARTAN_RENDER_TRACE"] = "1"

        return env

    def on_play(self):
        if self.busy or self.proc:
            return
        self.user_stopped = False

        # Vulkan Compatibility Verification
        gpu_id = game_gpu_id(self.cfg.get("gpu_index", -1), SYSTEM_GPUS)
        problem = vulkan_problem(VULKAN, gpu_id)
        if problem:
            self._deiconify()
            title, msg = vulkan_warning(problem, VULKAN, gpu_id)
            if not messagebox.askyesno(title, msg, icon="warning", default="no", parent=self):
                return
        self._collect()
        try:
            trophies_module.sync_trophy_texts_file(USER, language=self.cfg.get("language", "en"))
        except Exception:
            pass
        game = Path(self.cfg["game"]) if self.cfg["game"] else None
        update_dir = Path(self.cfg["update_dir"]) if self.cfg.get("update_dir") else None
        dlc_dir = Path(self.cfg["dlc_dir"]) if self.cfg.get("dlc_dir") else None
        enabled_mods = resolve_enabled_mods(self.cfg)

        exe = BIN / "sumeragi-core.exe"
        if not exe.is_file():
            exe = CORE
        if not exe.is_file():
            for cand in (
                ROOT / "bin" / "sumeragi-core.exe",
                ROOT / "bin" / "basara4-core.exe",
                ROOT / "out" / "sumeragi-core.exe",
                ROOT / "out" / "basara4-core.exe",
                ROOT / "out" / "gpu" / "basara4-core.exe",
            ):
                if cand.is_file():
                    exe = cand
                    break

        try:
            game_update.validate_game(game, update_dir, mods=enabled_mods, out=OUT)
            if dlc_dir:
                base_title = game_title_id(game) or "CUSA01159"
                dlc.discover_addons(dlc_dir, title_id=base_title)
        except (ValueError, OSError) as error:
            self._deiconify()
            messagebox.showerror(t("dialog.error_title"), t("dialog.game_invalid", reason=str(error)), parent=self)
            return

        if not exe.is_file():
            self._deiconify()
            messagebox.showerror(t("dialog.error_title"), t("dialog.runtime_missing", path=str(exe)), parent=self)
            return

        self.busy = True
        self.play.config(state="disabled")
        self.pending = None
        threading.Thread(
            target=self._prepare_then_launch,
            args=(game, update_dir, exe, dlc_dir, enabled_mods),
            daemon=True,
        ).start()
        self.after(200, self._wait_prepare)

    def _progress(self, text: str):
        self.pending_text = text

    def _prepare_then_launch(
        self,
        game: Optional[Path],
        update_dir: Optional[Path],
        exe: Path,
        dlc_dir: Optional[Path] = None,
        mods: Optional[List[Path]] = None,
    ):
        self.pending_text = t("home.game_starting")
        error = None
        view = None
        effective_game = game
        active_mods = list(mods) if mods is not None else resolve_enabled_mods(self.cfg)

        if (update_dir or active_mods) and game:
            self.pending_text = t("home.preparing_overlay")
            try:
                view = game_update.create_view(game, update_dir, OUT, mods=active_mods)
                effective_game = view
            except (ValueError, OSError) as err:
                self.pending = (str(err), None, None, [], "", None)
                return

        try:
            if effective_game and not image_ready(effective_game):
                error = prepare_image(effective_game, self._progress)
            patch_args, notice = [], ""
            if not error:
                try:
                    res_setting = self.cfg.get("resolution", "native")
                    cheats_setting = self.cfg.get("cheats", ())
                    game_ver = game_app_ver(effective_game) if effective_game else None
                    unlimited = (self.cfg.get("fps_limit", 60) != 60)
                    writes, notes = patches_module.build(
                        OUT / "eboot.elf",
                        OUT / "patches.bin",
                        unlimited=unlimited,
                        cheats=cheats_setting,
                        game_version=game_ver,
                        resolution=res_setting,
                    )
                    if writes:
                        patch_args = ["--patches", str(OUT / "patches.bin")]
                    elif unlimited:
                        self.cfg["fps_limit"] = 60
                        notice = "Frame limiter not found in this eboot.bin: staying at 60.  "
                except Exception as ex:
                    patch_args = []

            addon_args = []
            if not error and dlc_dir and effective_game:
                self.pending_text = "Discovering add-on DLCs…"
                base_title = game_title_id(effective_game) or "CUSA01159"
                addons = dlc.generate_manifest(dlc_dir, OUT, title_id=base_title)
                if addons:
                    addon_args = ["--addons", str(OUT / "addons.bin")]
            elif not error and not dlc_dir:
                stale_addons = OUT / "addons.bin"
                if stale_addons.is_file():
                    try:
                        stale_addons.unlink()
                    except OSError:
                        pass

            if error and view:
                try:
                    game_update.remove_view(view)
                except Exception:
                    pass
                view = None
            self.pending = (error, effective_game, exe, patch_args + addon_args, notice, view)
        except BaseException as ex:
            if view:
                try:
                    game_update.remove_view(view)
                except Exception:
                    pass
                view = None
            self.pending = (str(ex), None, None, [], "", None)

    def _wait_prepare(self):
        if self.pending is None:
            self.status.config(text=getattr(self, "pending_text", t("home.game_starting")))
            self.after(200, self._wait_prepare)
            return

        error, effective_game, exe, patch_args, notice, view = self.pending
        self.busy = False

        if error:
            self.play.config(state="normal")
            self._deiconify()
            self.status.config(text=error, fg=theme.COLOR_ERROR)
            messagebox.showerror(t("dialog.error_title"), t("dialog.prepare_failed", reason=error), parent=self)
            return

        self.update_view = view
        if self.cfg["fps_limit"] == 60:
            self.fps_var.set(FPS_LIMITS[0][0])
        USER.mkdir(parents=True, exist_ok=True)
        if effective_game:
            self._make_window_icon(effective_game)

        if self.cfg.get("audio_log") and AUDIO_LOG.exists():
            try:
                os.replace(AUDIO_LOG, AUDIO_LOG.with_name("audio_debug.previous.log"))
            except OSError:
                pass

        if self.cfg.get("audio_log") and self.cfg.get("audio_wav"):
            AUDIO_WAV.mkdir(parents=True, exist_ok=True)
            for old in AUDIO_WAV.glob("*.wav"):
                try:
                    old.unlink()
                except OSError:
                    pass

        log = open(LOG, "wb")
        self.proc = subprocess.Popen(
            [
                str(exe),
                str(OUT / "boot-linked.bin"),
                "--content-profile",
                str(OUT / "content.bin"),
                "--app0",
                str(effective_game),
                "--user",
                str(USER),
                "--no-game-hooks",
                "--cheats",
            ]
            + patch_args,
            env=self._env(),
            cwd=str(USER),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW,
        )

        if self.cfg.get("audio_wav"):
            self.cfg["audio_wav"] = False
            save_config(self.cfg)
            self.wav_var.set(False)

        self.stop.config(state="normal")
        self.status.config(text=notice + t("home.game_running"), fg=theme.COLOR_SUCCESS)
        self._refresh_all_statuses()

    def _make_window_icon(self, game: Path):
        if Image is None or WINDOW_ICON.exists():
            return
        icon_path = Path(game) / "sce_sys" / "icon0.png"
        if not icon_path.is_file():
            try:
                sfo = find_sfo(game)
                if sfo.is_file():
                    cand = sfo.parent / "icon0.png"
                    if cand.is_file():
                        icon_path = cand
            except Exception:
                pass
        try:
            Image.open(icon_path).convert("RGBA").resize((128, 128)).save(WINDOW_ICON, format="BMP")
        except OSError:
            pass

    def show_credits(self):
        notice = ROOT / "NOTICE.md"
        try:
            text = notice.read_text(encoding="utf-8")
        except OSError:
            text = "Credits are in NOTICE.md."

        win = tk.Toplevel(self)
        win.title(f"{BRAND} - {t('app.credits')}")
        win.configure(bg=theme.BG_MAIN)
        win.geometry("640x480")

        box = tk.Text(win, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, wrap="word", relief="flat", padx=14, pady=12, font=theme.FONT_BODY)
        box.insert("1.0", text)
        box.config(state="disabled")
        box.pack(fill="both", expand=True, padx=12, pady=12)

    def _deiconify(self):
        self.deiconify()

    def on_stop(self):
        self.user_stopped = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                pass
        if getattr(self, "update_view", None):
            try:
                game_update.remove_view(self.update_view)
            except Exception:
                pass
            self.update_view = None

    def _poll(self):
        if self.proc and self.proc.poll() is not None:
            code = self.proc.returncode
            self.proc = None
            if getattr(self, "update_view", None):
                try:
                    game_update.remove_view(self.update_view)
                except Exception:
                    pass
                self.update_view = None

            self.play.config(state="normal")
            self.stop.config(state="disabled")

            was_manual_stop = getattr(self, "user_stopped", False)
            self.user_stopped = False

            if self.play_now:
                if code not in (0, None) and not was_manual_stop:
                    self._show_crash_dialog(code)
                self.destroy()
                return

            if code in (0, None) or was_manual_stop:
                self.status.config(text=t("home.game_closed"), fg=theme.ACCENT_GOLD)
            else:
                self.status.config(text=t("home.game_exited_code", code=f"{code & 0xFFFFFFFF:#x}"), fg=theme.COLOR_ERROR)
                self._show_crash_dialog(code)
            self._load_ini_into_ui()
        self.after(500, self._poll)

    def _show_crash_dialog(self, exit_code: int):
        try:
            self._deiconify()
            SumeragiCrashDialog(self, exit_code, LOG)
        except Exception as e:
            messagebox.showerror(t("dialog.error_title"), f"Crash reporter error: {e}", parent=self)

    # -----------------------------------------------------------------------
    # Controller Mappers & Utility Windows
    # -----------------------------------------------------------------------

    def map_pad(self, extra):
        candidates = [
            BIN / "sumeragi-pad-mapper.exe",
            BIN / "basara4-pad-mapper.exe",
            ROOT / "out" / "sumeragi-pad-mapper.exe",
            ROOT / "out" / "basara4-pad-mapper.exe",
        ]
        exe = next((c for c in candidates if c.is_file()), None)
        if not exe:
            messagebox.showerror(t("dialog.error_title"), t("dialog.device_mapper_missing", path=str(candidates[0])), parent=self)
            return

        USER.mkdir(parents=True, exist_ok=True)
        messagebox.showinfo(BRAND, t("dialog.device_map_prompt"), parent=self)
        try:
            cmd = f'start "" "{exe}" {extra}'
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.SubprocessError as error:
            messagebox.showerror(t("dialog.error_title"), str(error), parent=self)

    def reset_map(self):
        if messagebox.askyesno(BRAND, t("dialog.device_reset_confirm"), parent=self):
            if MAPPING.exists():
                MAPPING.unlink()
            self._refresh_all_statuses()

    def open_log(self):
        self.show_page("diagnostics")

    def open_audio_log(self):
        self.show_page("diagnostics")
        self._switch_log("audio")

    def open_saves(self):
        p = USER / "savedata"
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(p)

    def open_trophies(self):
        self.show_page("trophies")

    def open_controller_controls(self):
        self.show_page("controls")

    def _save_input_mode(self):
        self.cfg["input_mode"] = self.input_mode_var.get()
        save_config(self.cfg)

    def open_dlc_manager(self):
        self.show_page("dlc")

    def open_mods_manager(self):
        window = tk.Toplevel(self)
        window.title(f"{BRAND} — {t('mods.title')}")
        window.configure(bg=theme.BG_MAIN)
        window.geometry("760x560")
        window.minsize(680, 480)
        window.transient(self)
        window.grab_set()

        root_frame = tk.Frame(window, bg=theme.BG_CARD, padx=18, pady=16, bd=1, relief="solid")
        root_frame.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(root_frame, text=t("mods.title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING).pack(anchor="w")
        tk.Label(root_frame, text=t("mods.subtitle"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY, wraplength=700, justify="left").pack(anchor="w", pady=(2, 8))

        # Mods root folder row
        dir_row = tk.Frame(root_frame, bg=theme.BG_CARD)
        dir_row.pack(fill="x", pady=(0, 8))
        dir_row.columnconfigure(1, weight=1)

        tk.Label(dir_row, text=t("mods.root_label"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY_BOLD).grid(row=0, column=0, sticky="w", padx=(0, 8))
        mods_dir_var = tk.StringVar(value=self.cfg.get("mods_dir") or str(ROOT / "mods"))
        ttk.Entry(dir_row, textvariable=mods_dir_var).grid(row=0, column=1, sticky="ew", padx=(0, 6))

        extra_mods: List[str] = list(self.cfg.get("extra_mods", []))
        game_path = self.cfg.get("game") or None
        update_path = self.cfg.get("update_dir") or None
        entries: List[Dict[str, Any]] = build_mod_entries(
            self.cfg,
            mods_dir=mods_dir_var.get(),
            extra_mods=extra_mods,
            base=game_path,
            update=update_path,
            out=OUT,
        )

        # Overlay priority hint + count summary
        hint_row = tk.Frame(root_frame, bg=theme.BG_ELEVATED, bd=1, relief="solid", padx=10, pady=6)
        hint_row.pack(fill="x", pady=(0, 8))
        tk.Label(hint_row, text=f"ℹ️ {t('mods.order_hint')}", bg=theme.BG_ELEVATED, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION).pack(side="left")
        summary_lbl = tk.Label(hint_row, text="", bg=theme.ACCENT_GOLD_MUTED, fg=theme.ACCENT_GOLD, font=theme.FONT_BADGE, padx=8, pady=2)
        summary_lbl.pack(side="right")

        # Scrollable list container
        list_outer = tk.Frame(root_frame, bg=theme.BG_INPUT, bd=1, relief="solid")
        list_outer.pack(fill="both", expand=True, pady=(0, 10))

        canvas = tk.Canvas(list_outer, bg=theme.BG_INPUT, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        list_inner = tk.Frame(canvas, bg=theme.BG_INPUT)
        list_inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_win = canvas.create_window((0, 0), window=list_inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_win, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar.pack(side="right", fill="y", pady=6)

        row_vars: List[tk.BooleanVar] = []

        def update_summary():
            enabled_count = sum(1 for item in entries if item["enabled"])
            summary_lbl.config(text=t("mods.count_summary", enabled=enabled_count, total=len(entries)))

        def render_list():
            for child_w in list_inner.winfo_children():
                child_w.destroy()
            row_vars.clear()
            update_summary()

            if not entries:
                empty_box = tk.Frame(list_inner, bg=theme.BG_INPUT, pady=36)
                empty_box.pack(fill="both", expand=True)
                tk.Label(empty_box, text=t("mods.empty_title"), bg=theme.BG_INPUT, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING).pack()
                tk.Label(empty_box, text=t("mods.empty_desc"), bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY, wraplength=540, justify="center").pack(pady=(6, 0))
                return

            enabled_rank = 0
            show_reorder = len(entries) > 1
            for idx, item in enumerate(entries):
                if item["enabled"]:
                    enabled_rank += 1
                    rank_text = f"#{enabled_rank}"
                    rank_bg, rank_fg = theme.ACCENT_GOLD_MUTED, theme.ACCENT_GOLD
                else:
                    rank_text = "—"
                    rank_bg, rank_fg = theme.BG_ELEVATED, theme.TEXT_MUTED

                row = tk.Frame(list_inner, bg=theme.BG_CARD, bd=1, relief="solid", padx=10, pady=8)
                row.pack(fill="x", pady=3, padx=2)
                row.columnconfigure(2, weight=1)

                tk.Label(row, text=rank_text, bg=rank_bg, fg=rank_fg, font=theme.FONT_BADGE, width=4, pady=3).grid(row=0, column=0, rowspan=2, padx=(0, 8), sticky="w")

                var = tk.BooleanVar(value=bool(item["enabled"]))
                row_vars.append(var)

                def on_toggle(i=idx, v=var):
                    entries[i]["enabled"] = bool(v.get())
                    render_list()

                ttk.Checkbutton(row, variable=var, command=on_toggle).grid(row=0, column=1, rowspan=2, padx=(0, 6), sticky="w")

                title_line = tk.Frame(row, bg=theme.BG_CARD)
                title_line.grid(row=0, column=2, sticky="w")
                tk.Label(title_line, text=item["name"], bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY_BOLD).pack(side="left")

                meta_bits = []
                if item.get("version"):
                    meta_bits.append(f"v{item['version']}")
                if item.get("author"):
                    meta_bits.append(item["author"])
                if meta_bits:
                    tk.Label(title_line, text="  ·  " + " · ".join(meta_bits), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION).pack(side="left")

                if item.get("is_external"):
                    tk.Label(title_line, text=t("mods.badge_external"), bg="#1e293b", fg="#93c5fd", font=theme.FONT_BADGE, padx=6, pady=1).pack(side="left", padx=(8, 0))
                if not item.get("valid", True):
                    tk.Label(title_line, text=t("mods.badge_invalid"), bg="#3B1C1C", fg=theme.COLOR_ERROR, font=theme.FONT_BADGE, padx=6, pady=1).pack(side="left", padx=(8, 0))

                sub_text = item.get("error") if not item.get("valid", True) else (item.get("description") or str(item["path"]))
                sub_fg = theme.COLOR_ERROR if not item.get("valid", True) else theme.TEXT_MUTED
                tk.Label(row, text=sub_text, bg=theme.BG_CARD, fg=sub_fg, font=theme.FONT_CAPTION, anchor="w", justify="left", wraplength=440).grid(row=1, column=2, sticky="w")

                ctrl_box = tk.Frame(row, bg=theme.BG_CARD)
                ctrl_box.grid(row=0, column=3, rowspan=2, padx=(8, 0), sticky="e")

                if show_reorder:
                    up_btn = ttk.Button(
                        ctrl_box,
                        text=t("mods.btn_up"),
                        style="Small.TButton",
                        width=3,
                        command=lambda i=idx: (move_mod_entry(entries, i, -1), render_list()),
                    )
                    if idx == 0:
                        up_btn.state(["disabled"])
                    up_btn.pack(side="left", padx=(0, 3))

                    dn_btn = ttk.Button(
                        ctrl_box,
                        text=t("mods.btn_down"),
                        style="Small.TButton",
                        width=3,
                        command=lambda i=idx: (move_mod_entry(entries, i, 1), render_list()),
                    )
                    if idx == len(entries) - 1:
                        dn_btn.state(["disabled"])
                    dn_btn.pack(side="left", padx=(0, 3))

                if item.get("is_external"):
                    def remove_external(i=idx):
                        removed = entries.pop(i)
                        rem_key = os.path.normcase(os.path.normpath(str(removed["path"])))
                        extra_mods[:] = [
                            x for x in extra_mods
                            if os.path.normcase(os.path.normpath(str(Path(x).resolve() if Path(x).exists() else Path(x)))) != rem_key
                        ]
                        render_list()

                    ttk.Button(ctrl_box, text=t("mods.btn_remove"), style="Small.TButton", width=3, command=remove_external).pack(side="left")

        def refresh_mods():
            current_enabled = [str(item["path"]) for item in entries if item["enabled"]]
            temp_cfg = dict(self.cfg)
            temp_cfg["mods_dir"] = mods_dir_var.get().strip() or str(ROOT / "mods")
            temp_cfg["enabled_mods"] = current_enabled
            temp_cfg["extra_mods"] = extra_mods
            entries[:] = build_mod_entries(
                temp_cfg,
                mods_dir=temp_cfg["mods_dir"],
                extra_mods=extra_mods,
                base=game_path,
                update=update_path,
                out=OUT,
            )
            render_list()

        def browse_mods_root():
            picked = filedialog.askdirectory(initialdir=mods_dir_var.get() or str(ROOT), title=t("mods.select_root_title"), parent=window)
            if picked:
                mods_dir_var.set(os.path.normpath(picked))
                refresh_mods()

        def open_mods_folder():
            p = Path(mods_dir_var.get().strip() or (ROOT / "mods"))
            p.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(p)

        def add_mod_path(picked: str | Path) -> bool:
            try:
                resolved = game_update.validate_mod(picked, base=game_path, update=update_path, out=OUT)
            except (ValueError, OSError) as err:
                messagebox.showerror(t("mods.invalid_title"), str(err), parent=window)
                return False
            key = os.path.normcase(os.path.normpath(str(resolved)))
            for item in entries:
                if os.path.normcase(os.path.normpath(str(item["path"]))) == key:
                    item["enabled"] = True
                    item["valid"] = True
                    item["error"] = None
                    render_list()
                    return True
            root_mods = Path(mods_dir_var.get().strip() or (ROOT / "mods"))
            if resolved.parent != (root_mods.resolve() if root_mods.exists() else root_mods):
                extra_mods.append(str(resolved))
            meta = game_update.read_mod_metadata(resolved)
            entries.append({
                "path": resolved,
                "name": meta["name"],
                "folder_name": resolved.name,
                "order": meta["order"],
                "description": meta["description"],
                "author": meta["author"],
                "version": meta["version"],
                "has_manifest": meta["has_manifest"],
                "valid": True,
                "error": None,
                "is_external": resolved.parent != (root_mods.resolve() if root_mods.exists() else root_mods),
                "enabled": True,
            })
            render_list()
            return True

        def browse_add_mod():
            picked = filedialog.askdirectory(initialdir=mods_dir_var.get() or str(ROOT), title=t("mods.select_folder_title"), parent=window)
            if picked:
                add_mod_path(picked)

        ttk.Button(dir_row, text=t("common.browse"), style="Small.TButton", command=browse_mods_root).grid(row=0, column=2, padx=(0, 4))
        ttk.Button(dir_row, text=t("mods.btn_open_folder"), style="Small.TButton", command=open_mods_folder).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(dir_row, text=t("common.refresh"), style="Small.TButton", command=refresh_mods).grid(row=0, column=4)

        bottom_bar = tk.Frame(root_frame, bg=theme.BG_CARD)
        bottom_bar.pack(fill="x")

        ttk.Button(bottom_bar, text=t("mods.btn_add"), style="Small.TButton", command=browse_add_mod).pack(side="left")

        def save_and_close():
            self.cfg["mods_dir"] = mods_dir_var.get().strip() or str(ROOT / "mods")
            self.cfg["extra_mods"] = list(dict.fromkeys(extra_mods))
            self.cfg["enabled_mods"] = [str(item["path"]) for item in entries if item["enabled"]]
            save_config(self.cfg)
            self._refresh_all_statuses()
            window.destroy()

        ttk.Button(bottom_bar, text=t("common.cancel"), style="Small.TButton", command=window.destroy).pack(side="right")
        ttk.Button(bottom_bar, text=t("common.save_apply"), style="Primary.TButton", command=save_and_close).pack(side="right", padx=(0, 8))

        render_list()
        window._mod_state = {  # type: ignore[attr-defined]
            "entries": entries,
            "mods_dir_var": mods_dir_var,
            "extra_mods": extra_mods,
            "render_list": render_list,
            "refresh_mods": refresh_mods,
            "add_mod_path": add_mod_path,
            "save": save_and_close,
        }
        return window

    def open_captures(self):
        p = USER / "captures"
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(p)

    def open_cheats_manager(self):
        try:
            current = cheats_module.normalize_selection(self.cfg.get("cheats", []))
        except ValueError as error:
            messagebox.showerror("Invalid cheat settings", str(error), parent=self)
            return

        window = tk.Toplevel(self)
        window.title(f"{BRAND} — Cheats (GoldHEN)")
        window.configure(bg=theme.BG_MAIN)
        window.geometry("640x430")
        window.minsize(580, 390)
        window.transient(self)
        window.grab_set()

        frame = tk.Frame(window, bg=theme.BG_CARD, padx=20, pady=18, bd=1, relief="solid")
        frame.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(frame, text="GoldHEN cheats · CUSA01159 · update 01.02",
                 bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING).pack(anchor="w")
        tk.Label(frame, text=f"Cheat codes by {cheats_module.AUTHOR}. These are applied on the next game launch.",
                 bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY).pack(anchor="w", pady=(4, 12))

        selected = set(current)
        toggles = {}
        for cheat_id, cheat in cheats_module.CHEATS.items():
            var = tk.BooleanVar(value=cheat_id in selected)
            toggles[cheat_id] = var
            ttk.Checkbutton(
                frame, text=f"{cheats_module.CHEATS[cheat_id]['name']}  ·  by {cheats_module.AUTHOR}",
                variable=var).pack(anchor="w", pady=4)

        tk.Label(frame, text="Cave dan hook tiap cheat dipisahkan agar semuanya bisa aktif bersamaan.",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_CAPTION).pack(anchor="w", pady=(6, 0))

        source_row = tk.Frame(frame, bg=theme.BG_CARD)
        source_row.pack(fill="x", pady=(10, 0))
        tk.Label(source_row, text="Source: GoldHEN Cheat Repository (GPL-3.0)",
                 bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_CAPTION).pack(side="left")

        def open_source():
            import webbrowser
            webbrowser.open(cheats_module.SOURCE_URL)

        ttk.Button(source_row, text="View source", style="Small.TButton", command=open_source).pack(side="right")

        buttons = tk.Frame(frame, bg=theme.BG_CARD)
        buttons.pack(fill="x", side="bottom", pady=(16, 0))

        def save():
            choices = [cheat_id for cheat_id, var in toggles.items() if var.get()]
            try:
                cheats_module.validate_selection(choices)
                previous = self.cfg.get("cheats", [])
                self.cfg["cheats"] = choices
                try:
                    save_config(self.cfg)
                except OSError:
                    self.cfg["cheats"] = previous
                    raise
            except (OSError, ValueError) as error:
                messagebox.showerror("Cannot save cheats", str(error), parent=window)
                return
            window.destroy()

        ttk.Button(buttons, text="Cancel", style="Small.TButton", command=window.destroy).pack(side="right")
        ttk.Button(buttons, text="Save cheats", style="Primary.TButton", command=save).pack(side="right", padx=(0, 8))

    def open_keymap_ui(self):
        win = tk.Toplevel(self)
        win.title("Keyboard & Mouse Controls — Custom Keymap")
        win.configure(bg=theme.BG_MAIN)
        win.geometry("740x620")
        win.minsize(680, 520)
        win.transient(self)
        win.grab_set()

        cur_map = dict(DEFAULT_PC_KEYMAP)
        cur_map.update(self.cfg.get("keymap", {}))
        mouse_cam_var = tk.BooleanVar(value=self.cfg.get("mouse_camera", True))
        mouse_sens_var = tk.IntVar(value=self.cfg.get("mouse_sens", 100))

        top_frame = tk.Frame(win, bg=theme.BG_CARD, padx=14, pady=12, bd=1, relief="solid")
        top_frame.pack(fill="x", padx=14, pady=(12, 6))

        tk.Label(top_frame, text="⚙️ Pengaturan Kontrol Keyboard & Mouse", bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING).pack(anchor="w")
        tk.Label(top_frame, text="Klik tombol untuk mengubah pemetaan. Tekan tombol Keyboard atau Mouse untuk mengikat.", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY).pack(anchor="w", pady=(2, 0))

        mouse_bar = tk.Frame(top_frame, bg=theme.BG_CARD)
        mouse_bar.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(mouse_bar, text="Aktifkan Kamera Mouse (Mouse Look)", variable=mouse_cam_var).pack(side="left")

        sens_frame = tk.Frame(mouse_bar, bg=theme.BG_CARD)
        sens_frame.pack(side="right")
        tk.Label(sens_frame, text="Sensitivitas: ", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY).pack(side="left")
        sens_lbl = tk.Label(sens_frame, text=f"{mouse_sens_var.get()}%", bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_BODY_BOLD, width=5)
        sens_lbl.pack(side="right")
        def on_sens_scroll(val):
            sens_lbl.config(text=f"{int(float(val))}%")
        scale = ttk.Scale(sens_frame, from_=20, to=300, variable=mouse_sens_var, command=on_sens_scroll, length=120)
        scale.pack(side="left", padx=6)

        body_container = tk.Frame(win, bg=theme.BG_MAIN)
        body_container.pack(fill="both", expand=True, padx=14, pady=6)

        canvas = tk.Canvas(body_container, bg=theme.BG_MAIN, highlightthickness=0)
        scrollbar = ttk.Scrollbar(body_container, orient="vertical", command=canvas.yview)
        scroll_content = tk.Frame(canvas, bg=theme.BG_MAIN)

        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            if getattr(event, "delta", 0):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        win.bind("<MouseWheel>", _on_mousewheel)
        win.bind("<Button-4>", _on_mousewheel)
        win.bind("<Button-5>", _on_mousewheel)

        btn_widgets = {}
        active_listening = [None]

        def format_binding_display(key_str):
            if not key_str:
                return "None"
            return key_str.upper() if len(key_str) <= 3 else key_str

        def finish_listen(action_name, new_key):
            if active_listening[0] == action_name:
                active_listening[0] = None
                cur_map[action_name] = new_key
                btn = btn_widgets.get(action_name)
                if btn:
                    btn.config(text=format_binding_display(new_key), bg="#2c2824", fg=theme.ACCENT_GOLD)
                win.unbind("<Key>")
                win.unbind("<Button-1>")
                win.unbind("<Button-2>")
                win.unbind("<Button-3>")

        def start_listen(action_name):
            if active_listening[0]:
                old_action = active_listening[0]
                old_btn = btn_widgets.get(old_action)
                if old_btn:
                    old_btn.config(text=format_binding_display(cur_map.get(old_action, "")), bg="#2c2824", fg=theme.ACCENT_GOLD)
            active_listening[0] = action_name
            btn = btn_widgets.get(action_name)
            if btn:
                btn.config(text="[ TEKAN TOMBOL... ]", bg=theme.ACCENT_CRIMSON, fg="#fff")

            def on_key_event(event):
                keysym = event.keysym
                key_map_table = {
                    "Return": "Return", "Escape": "Escape", "space": "Space",
                    "BackSpace": "Backspace", "Tab": "Tab", "Shift_L": "Left Shift",
                    "Shift_R": "Right Shift", "Control_L": "Left Ctrl", "Control_R": "Right Ctrl",
                    "Alt_L": "Left Alt", "Alt_R": "Right Alt", "Caps_Lock": "CapsLock",
                    "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
                    "comma": "Comma", "equal": "Equals", "period": "Period",
                    "slash": "Slash", "semicolon": "Semicolon", "minus": "Minus"
                }
                mapped_name = key_map_table.get(keysym, keysym.capitalize() if len(keysym) > 1 else keysym.upper())
                finish_listen(action_name, mapped_name)
                return "break"

            def on_mouse_event(btn_num):
                name_map = {1: "Mouse Left", 2: "Mouse Middle", 3: "Mouse Right"}
                finish_listen(action_name, name_map.get(btn_num, f"Mouse {btn_num}"))
                return "break"

            win.bind("<Key>", on_key_event)
            win.focus_set()
            win.bind("<Button-1>", lambda e: on_mouse_event(1))
            win.bind("<Button-2>", lambda e: on_mouse_event(2))
            win.bind("<Button-3>", lambda e: on_mouse_event(3))

        for row_idx, (action_key, action_label, ps_button_label) in enumerate(ACTION_DESCRIPTIONS):
            item_frame = tk.Frame(scroll_content, bg=theme.BG_CARD, padx=12, pady=7, highlightbackground="#25211d", highlightthickness=1)
            item_frame.pack(fill="x", pady=2, padx=4)

            lbl_text = f"{action_label}"
            tk.Label(item_frame, text=lbl_text, bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY_BOLD, anchor="w").pack(side="left", padx=(4, 0))
            tk.Label(item_frame, text=f"({ps_button_label})", bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_CAPTION, anchor="w").pack(side="left", padx=8)

            val = cur_map.get(action_key, "")
            key_btn = tk.Button(
                item_frame,
                text=format_binding_display(val),
                bg="#2c2824",
                fg=theme.ACCENT_GOLD,
                activebackground=theme.ACCENT_CRIMSON,
                activeforeground="#fff",
                font=("Consolas", 10, "bold"),
                width=16,
                relief="flat",
                bd=0,
                padx=8,
                pady=4,
                cursor="hand2",
                command=lambda a=action_key: start_listen(a)
            )
            key_btn.pack(side="right")
            btn_widgets[action_key] = key_btn

        notice_frame = tk.Frame(scroll_content, bg=theme.BG_CARD, padx=12, pady=6)
        notice_frame.pack(fill="x", pady=(8, 4), padx=4)
        tk.Label(
            notice_frame,
            text="ℹ️ Pergerakan Karakter otomatis terikat pada W, A, S, D (Standar PC). Kamera mouse mengontrol analog kanan.",
            bg=theme.BG_CARD,
            fg=theme.TEXT_MUTED,
            font=theme.FONT_CAPTION
        ).pack(anchor="w")

        bottom_bar = tk.Frame(win, bg=theme.BG_MAIN, padx=12, pady=12)
        bottom_bar.pack(fill="x")

        def reset_defaults():
            cur_map.clear()
            cur_map.update(DEFAULT_PC_KEYMAP)
            mouse_cam_var.set(True)
            mouse_sens_var.set(100)
            sens_lbl.config(text="100%")
            for k, b in btn_widgets.items():
                b.config(text=format_binding_display(cur_map.get(k, "")), bg="#2c2824", fg=theme.ACCENT_GOLD)
            messagebox.showinfo("Reset Preset", "Pengaturan kontrol berhasil dikembalikan ke Preset Default PC!", parent=win)

        def save_and_close():
            self.cfg["keymap"] = cur_map
            self.cfg["mouse_camera"] = mouse_cam_var.get()
            self.cfg["mouse_sens"] = int(mouse_sens_var.get())
            save_config(self.cfg)
            win.destroy()
            messagebox.showinfo("Tersimpan", "Pengaturan kontrol Keyboard & Mouse berhasil disimpan!", parent=self)

        ttk.Button(bottom_bar, text="🔄 Reset ke Default PC", style="Small.TButton", command=reset_defaults).pack(side="left", padx=4)
        ttk.Button(bottom_bar, text="Batal", style="Small.TButton", command=win.destroy).pack(side="right", padx=4)
        ttk.Button(bottom_bar, text="💾 Simpan Pengaturan", style="Primary.TButton", command=save_and_close).pack(side="right", padx=4)

    def _close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(BRAND, t("dialog.stop_confirm_msg"), parent=self):
                return
            self.on_stop()
        if getattr(self, "update_view", None):
            try:
                game_update.remove_view(self.update_view)
            except Exception:
                pass
            self.update_view = None
        self.destroy()


def main():
    play_now = len(sys.argv) > 1 and sys.argv[1] == "--play"
    app = Launcher(play_now=play_now)
    app.mainloop()


if __name__ == "__main__":
    main()
