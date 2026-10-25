"""Sumeragi Native+ Launcher - by i7Exceed (based on Basara 4 PC by Razz).

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

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent.parent
BIN, OUT, USER, SCRIPTS = ROOT / "bin", ROOT / "out", ROOT / "user", ROOT / "scripts"
CONFIG = USER / "launcher.json"
INI = USER / "sumeragi.ini"
OLD_INI = USER / "basara4.ini"
ANCIENT_INI = USER / "spartanport.ini"
WINDOW_ICON = USER / "window_icon.bmp"
CORE = BIN / "sumeragi-core.exe" if (BIN / "sumeragi-core.exe").is_file() else BIN / "basara4-core.exe"
VERSION = "1.0.3"
BRAND = "Sumeragi Native+"
TAGLINE = "The Sumeragi Experience, Evolved."
AUTHOR = "i7Exceed"
AUTHOR_URL = "https://github.com/i7Exceed"
LOG = USER / "last_run.log"
PREPARE_LOG = USER / "prepare.log"
MAPPING = USER / "gamepad_mapping.txt"
AUDIO_LOG = USER / "audio_debug.log"
AUDIO_WAV = USER / "audio_wav"  # SPARTAN_AUDIO_WAV_DIR: float WAV capture of the mix and of long voices
STAMP = OUT / "prepared.json"
WAV_WARNING = (
    "WAV capture saves the final mix and every long voice as uncompressed audio in user\\audio_wav: "
    "about 70 MB per minute, up to 3 GB for one session.\n\n"
    "Use it only to find an audio problem, and delete the files afterwards.\n\n"
    "It applies to the next game start only and switches itself off after that. "
    "It also turns on the audio debug log. Turn it on?"
)
PIPELINE = [
    ("prepare.py", []),
    ("link_libc.py", []),
    ("link_modules.py", []),
    ("content_profile.py", ["--sku", "full"]),
]
NO_WINDOW = 0x08000000


def wav_captures():
    """The audio captures an earlier session left in user\\audio_wav: (files, total bytes)."""
    files = sorted(AUDIO_WAV.glob("*.wav")) if AUDIO_WAV.is_dir() else []
    total = 0
    for f in files:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return files, total


def format_size(n):
    return f"{n / 2**30:.1f} GB" if n >= 2**30 else f"{n / 2**20:.0f} MB"


def run_script_mode():
    """`launcher.exe --run-script NAME args...`: runs one of the preparation scripts in this process."""
    script = SCRIPTS / sys.argv[2]
    sys.path.insert(0, str(SCRIPTS))
    sys.argv = [str(script)] + sys.argv[3:]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exit_:
        code = exit_.code
        sys.exit(code if isinstance(code, int) else (0 if code is None else 1))


if len(sys.argv) > 2 and sys.argv[1] == "--run-script":
    run_script_mode()
    sys.exit(0)

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox, ttk  # noqa: E402

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageTk  # type: ignore[import-not-found, import-untyped]
except ImportError:
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageTk = None

# Ensure launcher and scripts are in sys.path
LAUNCHER_DIR = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(LAUNCHER_DIR) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_DIR))

import game_update  # noqa: E402
from patches import find_sfo, game_title_id, game_app_ver  # noqa: E402
import dlc  # noqa: E402
import sumeragi_patches as patches_module  # noqa: E402
import sumeragi_native_trophies as trophies_module  # noqa: E402
from sumeragi_native_trophies import TrophiesWindow  # noqa: E402
import sumeragi_controller_controls as controls_module  # noqa: E402
from sumeragi_controller_controls import ControllerControlsWindow, build_pad_map_spec, validate_controls  # noqa: E402
import sumeragi_theme as theme  # noqa: E402
import sumeragi_i18n as i18n  # noqa: E402
from sumeragi_i18n import t  # noqa: E402

# Configuration Defaults & Options
DEFAULTS = {
    "game": "",
    "update_dir": "",
    "dlc_dir": "",
    "display_mode": "borderless",
    "vsync": True,
    "fps_limit": 60,
    "rcas": False,
    "anisotropy": 0,
    "resolution": "native",
    "upscale": "off",
    "audio_log": False,
    "audio_wav": False,
    "pad_controls": {},
    "pad_style": "playstation",
    "language": "en",
}

DISPLAY_MODES = [
    ("Windowed", "windowed"),
    ("Borderless fullscreen", "borderless"),
    ("Exclusive fullscreen", "fullscreen"),
]
FPS_LIMITS = [
    ("60 (game default)", 60),
    ("90", 90),
    ("120", 120),
    ("144", 144),
    ("165", 165),
    ("240", 240),
    ("Unlimited", 0),
]
RESOLUTIONS = [
    ("1920 x 1080  (native)", "native"),
    ("1280 x 720", "720p"),
    ("1600 x 900", "900p"),
    ("2560 x 1440", "1440p"),
    ("3200 x 1800", "1800p"),
    ("3840 x 2160  (4K)", "4K"),
]
UPSCALERS = [("Off  (plain scaling)", "off"), ("FSR 1  (sharper)", "fsr1")]
ANISO = [("Off", 0), ("2x", 2), ("4x", 4), ("8x", 8), ("16x", 16)]
AVAILABLE_SDL_BUTTONS = [
    "a", "b", "x", "y", "leftshoulder", "rightshoulder",
    "leftstick", "rightstick", "start", "back", "guide",
    "dpup", "dpdown", "dpleft", "dpright", "touchpad",
    "misc1", "paddle1", "paddle2", "paddle3", "paddle4", "None",
]
TROPHY_FILTERS = [
    ("all", "trophies.filter_all"),
    ("unlocked", "trophies.filter_unlocked"),
    ("locked", "trophies.filter_locked"),
]

# Backward-compatibility color constants
BG = theme.BG_MAIN
PANEL = theme.BG_CARD
FG = theme.TEXT_PRIMARY
MUTED = theme.TEXT_SECONDARY
GOLD = theme.ACCENT_GOLD
RED = theme.ACCENT_CRIMSON
RAZZ = "#E0526A"


def find_game():
    """The first folder under game\\ that holds an eboot.bin."""
    base = ROOT / "game"
    if (base / "eboot.bin").is_file():
        return str(base)
    for child in sorted(base.iterdir()) if base.is_dir() else []:
        if (child / "eboot.bin").is_file():
            return str(child)
    return ""


def find_dlc():
    """The default dlc\\ folder if it exists next to the launcher."""
    base = ROOT / "dlc"
    if (base / "CUSA01159").is_dir():
        return str(base)
    return ""


def load_config():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        pass
    if not cfg["game"] or not (Path(cfg["game"]) / "eboot.bin").is_file():
        cfg["game"] = find_game()
    if not cfg.get("dlc_dir") or not Path(cfg["dlc_dir"]).is_dir():
        found = find_dlc()
        if found:
            cfg["dlc_dir"] = found
    # Ensure language is initialized
    lang = cfg.get("language") or cfg.get("lang") or "en"
    if lang not in i18n.SUPPORTED_LANGUAGES:
        lang = "en"
    cfg["language"] = lang
    i18n.set_language(lang, notify=False)
    return cfg


def save_config(cfg):
    USER.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def read_ini(path):
    values = {}
    try:
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.strip().split("=", 1)
                values[key] = value
    except OSError:
        pass
    return values


def write_ini(path, updates):
    """Update only the given keys; every other line the runtime wrote stays as it was."""
    path = Path(path)
    lines, seen = [], set()
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key = line.split("=", 1)[0] if "=" in line else None
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                lines.append(line)
    except OSError:
        pass
    lines += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def input_files_stamp(game):
    """Computes a dictionary of sha256 hashes of all input files affecting the prepared image."""
    game = Path(game)
    stamp = {}
    eboot = game / "eboot.bin"
    if eboot.is_file():
        stamp["eboot_sha256"] = file_sha256(eboot)
    try:
        sfo_path = find_sfo(game)
    except Exception:
        sfo_path = game / "sce_sys/param.sfo"
    if sfo_path.is_file():
        stamp["sfo_sha256"] = file_sha256(sfo_path)
    module_dir = game / "sce_module"
    if module_dir.is_dir():
        mod_hashes = {}
        for prx in sorted(module_dir.glob("*.prx")):
            if prx.is_file():
                mod_hashes[prx.name.casefold()] = file_sha256(prx)
        stamp["modules"] = mod_hashes
    return stamp


def image_ready(game):
    """Whether out\\ holds an image made from this effective game's current inputs."""
    try:
        if not STAMP.is_file():
            return False
        stamp = json.loads(STAMP.read_text(encoding="utf-8-sig"))
        current = input_files_stamp(game)
        if not current.get("eboot_sha256") or stamp.get("eboot_sha256") != current.get("eboot_sha256"):
            return False
        if current.get("sfo_sha256") and stamp.get("sfo_sha256") != current.get("sfo_sha256"):
            return False
        if current.get("modules") and stamp.get("modules") != current.get("modules"):
            return False
        required_outputs = ("boot-linked.bin", "content.bin", "eboot.elf", "boot.bin")
        return all((OUT / name).is_file() for name in required_outputs)
    except (OSError, ValueError):
        return False


def prepare_image(game, progress):
    """Runs the preparation scripts on the game's eboot.bin. Returns an error text or None."""
    OUT.mkdir(parents=True, exist_ok=True)
    USER.mkdir(parents=True, exist_ok=True)
    with open(PREPARE_LOG, "w", encoding="utf-8", errors="replace") as log:
        for index, (name, extra) in enumerate(PIPELINE, 1):
            progress(f"Preparing the game image ({index}/{len(PIPELINE)}): {name[:-3]}…")
            script = [sys.executable, "--run-script", name] if FROZEN else [sys.executable, str(SCRIPTS / name)]
            result = subprocess.run(
                script + [str(game), "--out", str(OUT)] + extra,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=NO_WINDOW,
            )
            if result.returncode:
                return f"{name} failed (exit {result.returncode}). See user\\prepare.log"
    stamp_data = input_files_stamp(game)
    stamp_data["game"] = str(game)
    STAMP.write_text(json.dumps(stamp_data, indent=2), encoding="utf-8")
    return None


# ---------------------------------------------------------------------------
# Redesigned Application Shell & Pages
# ---------------------------------------------------------------------------

PAGES = ("home", "game_files", "updates", "dlc", "trophies", "controls", "settings", "diagnostics")


class Launcher(tk.Tk):
    """Modern Dark Sengoku-Tech Desktop Launcher for Sumeragi Native+."""

    def __init__(self, play_now=False):
        super().__init__()
        self.cfg = load_config()
        self.proc = None
        self.busy = False
        self.pending = None
        self.play_now = play_now
        self.update_view = None
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
        self.ctrl_capture_helper = None
        self.ctrl_capturing_action: Optional[str] = None
        self.ctrl_capture_timer = None
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
                self.cover = ImageTk.PhotoImage(Image.open(icon_file).convert("RGB").resize((160, 160)))
        except OSError:
            pass

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
    # Page Builders
    # -----------------------------------------------------------------------

    def _build_pages(self):
        self._build_home_page()
        self._build_game_files_page()
        self._build_updates_page()
        self._build_dlc_page()
        self._build_trophies_page()
        self._build_controls_page()
        self._build_settings_page()
        self._build_diagnostics_page()

    # ---- 1. HOME PAGE ----
    def _build_home_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["home"] = page

        # Hero Banner Card
        hero = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid")
        hero.pack(fill="x", pady=(0, 16))

        hero_inner = tk.Frame(hero, bg=theme.BG_CARD, padx=20, pady=20)
        hero_inner.pack(fill="both", expand=True)

        # Left cover art
        cover_frame = tk.Frame(hero_inner, bg="#2A241C", bd=1, relief="solid")
        cover_frame.pack(side="left", padx=(0, 20))

        if self.cover:
            self.home_cover_lbl = tk.Label(cover_frame, image=self.cover, bd=0, bg=theme.BG_CARD)
        else:
            self.home_cover_lbl = tk.Label(cover_frame, text="BASARA 4\nSUMERAGI", width=16, height=8, bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_BODY_BOLD)
        self.home_cover_lbl.pack(padx=2, pady=2)

        # Right hero details
        hero_details = tk.Frame(hero_inner, bg=theme.BG_CARD)
        hero_details.pack(side="left", fill="both", expand=True)

        self.home_hero_title = tk.Label(hero_details, text=t("home.hero_title"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_HERO)
        self.home_hero_title.pack(anchor="w")

        self.home_hero_subtitle = tk.Label(hero_details, text=t("home.hero_subtitle"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY, wraplength=480, justify="left")
        self.home_hero_subtitle.pack(anchor="w", pady=(4, 12))

        # Launch Button Row
        btn_box = tk.Frame(hero_details, bg=theme.BG_CARD)
        btn_box.pack(anchor="w", pady=(0, 8))

        self.play = ttk.Button(btn_box, text=t("home.launch_game"), style="Primary.TButton", command=self.on_play)
        self.play.pack(side="left", padx=(0, 10))

        self.stop = ttk.Button(btn_box, text=t("home.stop_game"), style="Stop.TButton", command=self.on_stop, state="disabled")
        self.stop.pack(side="left")

        # Status text
        self.status = tk.Label(hero_details, text=t("common.ready"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_BODY)
        self.status.pack(anchor="w")

        # Quick Status Cards Grid
        grid_frame = tk.Frame(page, bg=theme.BG_MAIN)
        grid_frame.pack(fill="both", expand=True)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        # Status Card 1: Game Files
        self.card_game = self._create_status_card(grid_frame, "📁", "home.card_game_title", "game_files")
        self.card_game.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))

        # Status Card 2: Updates
        self.card_update = self._create_status_card(grid_frame, "🔄", "home.card_update_title", "updates")
        self.card_update.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))

        # Status Card 3: DLC
        self.card_dlc = self._create_status_card(grid_frame, "📦", "home.card_dlc_title", "dlc")
        self.card_dlc.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))

        # Status Card 4: Controller
        self.card_controls = self._create_status_card(grid_frame, "🎮", "home.card_controls_title", "controls")
        self.card_controls.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(8, 0))

        # Status Card 5: Trophies (spanning full width)
        self.card_trophies = self._create_status_card(grid_frame, "🏆", "home.card_trophies_title", "trophies")
        self.card_trophies.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))

        page.on_show = self._refresh_home_status  # type: ignore[attr-defined]

    def _create_status_card(self, parent: tk.Frame, icon: str, title_key: str, target_page: str) -> tk.Frame:
        card = tk.Frame(parent, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        card.columnconfigure(1, weight=1)

        icon_lbl = tk.Label(card, text=icon, bg=theme.BG_CARD, font=("Segoe UI", 16))
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="w")

        title_lbl = tk.Label(card, text=t(title_key), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        title_lbl.grid(row=0, column=1, sticky="w")

        val_lbl = tk.Label(card, text=t("common.loading"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION, wraplength=280, justify="left")
        val_lbl.grid(row=1, column=1, sticky="w")

        btn = ttk.Button(card, text=t("common.manage"), style="Small.TButton", command=lambda: self.show_page(target_page))
        btn.grid(row=0, column=2, rowspan=2, padx=(10, 0), sticky="e")

        card._title_key = title_key  # type: ignore[attr-defined]
        card._title_lbl = title_lbl  # type: ignore[attr-defined]
        card._val_lbl = val_lbl  # type: ignore[attr-defined]
        card._btn = btn  # type: ignore[attr-defined]
        return card

    # ---- 2. GAME FILES PAGE ----
    def _build_game_files_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["game_files"] = page

        # Header
        self.gf_title = tk.Label(page, text=t("game_files.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.gf_title.pack(anchor="w")
        self.gf_subtitle = tk.Label(page, text=t("game_files.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.gf_subtitle.pack(anchor="w", pady=(2, 16))

        # Card 1: Directory selection
        c1 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c1.pack(fill="x", pady=(0, 14))
        c1.columnconfigure(1, weight=1)

        self.gf_path_lbl = tk.Label(c1, text=t("game_files.path_label"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.gf_path_lbl.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self.game_var = tk.StringVar(value=self.cfg.get("game", ""))
        self.game_var.trace_add("write", lambda *_: self._refresh_all_statuses())

        self.gf_entry = ttk.Entry(c1, textvariable=self.game_var)
        self.gf_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        btn_box = tk.Frame(c1, bg=theme.BG_CARD)
        btn_box.grid(row=1, column=2, padx=(8, 0), sticky="e")
        self.gf_browse_btn = ttk.Button(btn_box, text=t("common.browse"), style="Small.TButton", command=self._browse)
        self.gf_browse_btn.pack(side="left", padx=(0, 4))
        self.gf_open_btn = ttk.Button(btn_box, text=t("common.open_folder"), style="Small.TButton", command=lambda: self._open_dir(self.game_var.get()))
        self.gf_open_btn.pack(side="left")

        self.gf_hint = tk.Label(c1, text=t("game_files.path_hint"), bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_CAPTION)
        self.gf_hint.grid(row=2, column=0, columnspan=3, sticky="w")

        # Card 2: Inspection Details
        c2 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c2.pack(fill="x", pady=(0, 14))
        c2.columnconfigure(1, weight=1)

        self.gf_insp_title = tk.Label(c2, text=t("game_files.inspection_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.gf_insp_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.gf_meta_lbl = tk.Label(c2, text="", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY, justify="left")
        self.gf_meta_lbl.grid(row=1, column=0, columnspan=2, sticky="w")

        # Card 3: Image Status & Re-prepare
        c3 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c3.pack(fill="x")
        c3.columnconfigure(0, weight=1)

        self.gf_img_title = tk.Label(c3, text=t("game_files.image_status_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.gf_img_title.pack(anchor="w", pady=(0, 6))

        self.image_label = tk.Label(c3, text="", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY, justify="left", wraplength=700)
        self.image_label.pack(anchor="w", pady=(0, 8))

        self.gf_reprep_btn = ttk.Button(c3, text=t("game_files.reprepare_btn"), style="Small.TButton", command=self._force_reprepare)
        self.gf_reprep_btn.pack(anchor="w")

        page.on_show = self._refresh_game_files_page  # type: ignore[attr-defined]

    # ---- 3. UPDATES PAGE ----
    def _build_updates_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["updates"] = page

        # Header
        self.up_title = tk.Label(page, text=t("updates.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.up_title.pack(anchor="w")
        self.up_subtitle = tk.Label(page, text=t("updates.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.up_subtitle.pack(anchor="w", pady=(2, 16))

        # Card 1: Directory Selection
        c1 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c1.pack(fill="x", pady=(0, 14))
        c1.columnconfigure(1, weight=1)

        self.up_path_lbl = tk.Label(c1, text=t("updates.path_label"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.up_path_lbl.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self.update_var = tk.StringVar(value=self.cfg.get("update_dir", ""))
        self.update_var.trace_add("write", lambda *_: self._refresh_all_statuses())

        self.up_entry = ttk.Entry(c1, textvariable=self.update_var)
        self.up_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        btn_box = tk.Frame(c1, bg=theme.BG_CARD)
        btn_box.grid(row=1, column=2, padx=(8, 0), sticky="e")
        self.up_browse_btn = ttk.Button(btn_box, text=t("common.browse"), style="Small.TButton", command=self._browse_update)
        self.up_browse_btn.pack(side="left", padx=(0, 4))
        self.up_clear_btn = ttk.Button(btn_box, text=t("common.clear"), style="Small.TButton", command=self._clear_update)
        self.up_clear_btn.pack(side="left", padx=(0, 4))
        self.up_open_btn = ttk.Button(btn_box, text=t("common.open_folder"), style="Small.TButton", command=lambda: self._open_dir(self.update_var.get()))
        self.up_open_btn.pack(side="left")

        self.up_hint = tk.Label(c1, text=t("updates.path_hint"), bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_CAPTION)
        self.up_hint.grid(row=2, column=0, columnspan=3, sticky="w")

        # Card 2: Update Status & Virtual Overlay Pipeline
        c2 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c2.pack(fill="x")

        self.up_overlay_title = tk.Label(c2, text=t("updates.overlay_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.up_overlay_title.pack(anchor="w", pady=(0, 6))

        self.up_status_lbl = tk.Label(c2, text="", bg=theme.BG_CARD, fg=theme.COLOR_SUCCESS, font=theme.FONT_BODY_BOLD)
        self.up_status_lbl.pack(anchor="w", pady=(0, 6))

        self.up_overlay_desc = tk.Label(c2, text=t("updates.overlay_desc"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY, justify="left", wraplength=700)
        self.up_overlay_desc.pack(anchor="w")

        page.on_show = self._refresh_updates_page  # type: ignore[attr-defined]

    # ---- 4. DLC PAGE ----
    def _build_dlc_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["dlc"] = page

        # Header
        self.dlc_title = tk.Label(page, text=t("dlc.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.dlc_title.pack(anchor="w")
        self.dlc_subtitle = tk.Label(page, text=t("dlc.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.dlc_subtitle.pack(anchor="w", pady=(2, 16))

        # Card 1: Directory selection
        c1 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c1.pack(fill="x", pady=(0, 14))
        c1.columnconfigure(1, weight=1)

        self.dlc_path_lbl = tk.Label(c1, text=t("dlc.path_label"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.dlc_path_lbl.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self.dlc_var = tk.StringVar(value=self.cfg.get("dlc_dir", ""))
        self.dlc_var.trace_add("write", lambda *_: self._refresh_all_statuses())

        self.dlc_entry = ttk.Entry(c1, textvariable=self.dlc_var)
        self.dlc_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        btn_box = tk.Frame(c1, bg=theme.BG_CARD)
        btn_box.grid(row=1, column=2, padx=(8, 0), sticky="e")
        self.dlc_browse_btn = ttk.Button(btn_box, text=t("common.browse"), style="Small.TButton", command=self._browse_dlc)
        self.dlc_browse_btn.pack(side="left", padx=(0, 4))
        self.dlc_clear_btn = ttk.Button(btn_box, text=t("common.clear"), style="Small.TButton", command=self._clear_dlc)
        self.dlc_clear_btn.pack(side="left", padx=(0, 4))
        self.dlc_open_btn = ttk.Button(btn_box, text=t("common.open_folder"), style="Small.TButton", command=lambda: self._open_dir(self.dlc_var.get()))
        self.dlc_open_btn.pack(side="left")

        self.dlc_hint = tk.Label(c1, text=t("dlc.path_hint"), bg=theme.BG_CARD, fg=theme.TEXT_MUTED, font=theme.FONT_CAPTION)
        self.dlc_hint.grid(row=2, column=0, columnspan=3, sticky="w")

        # Card 2: Detected Content Packages / Empty State
        c2 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=14)
        c2.pack(fill="both", expand=True)

        header_row = tk.Frame(c2, bg=theme.BG_CARD)
        header_row.pack(fill="x", pady=(0, 8))
        self.dlc_manifest_title = tk.Label(header_row, text=t("dlc.manifest_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.dlc_manifest_title.pack(side="left")
        self.dlc_count_badge = tk.Label(header_row, text="", bg=theme.ACCENT_GOLD_MUTED, fg=theme.ACCENT_GOLD, font=theme.FONT_BADGE, padx=8, pady=2)
        self.dlc_count_badge.pack(side="right")

        # Content Textbox / List
        self.dlc_text = tk.Text(c2, bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY, font=theme.FONT_MONO, relief="flat", padx=10, pady=10, height=12)
        self.dlc_text.pack(fill="both", expand=True)

        page.on_show = self._refresh_dlc_page  # type: ignore[attr-defined]

    # ---- 5. TROPHIES PAGE ----
    def _build_trophies_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["trophies"] = page

        # Header
        self.tr_title = tk.Label(page, text=t("trophies.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.tr_title.pack(anchor="w")
        self.tr_subtitle = tk.Label(page, text=t("trophies.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.tr_subtitle.pack(anchor="w", pady=(2, 12))

        # Progress Card
        prog_card = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=12)
        prog_card.pack(fill="x", pady=(0, 10))
        prog_card.columnconfigure(0, weight=1)

        top_row = tk.Frame(prog_card, bg=theme.BG_CARD)
        top_row.pack(fill="x", pady=(0, 6))

        self.tr_prog_header = tk.Label(top_row, text=t("trophies.progress_header"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.tr_prog_header.pack(side="left")

        self.tr_prog_summary = tk.Label(top_row, text="", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY_BOLD)
        self.tr_prog_summary.pack(side="right")

        self.tr_progressbar = ttk.Progressbar(prog_card, style="Horizontal.TProgressbar", maximum=100)
        self.tr_progressbar.pack(fill="x", pady=(0, 8))

        # Tier Breakdown Badges
        tier_row = tk.Frame(prog_card, bg=theme.BG_CARD)
        tier_row.pack(fill="x", pady=(0, 8))

        self.tr_badge_plat = tk.Label(tier_row, text="🏆 Platinum: -", bg="#1e293b", fg="#93c5fd", font=theme.FONT_BADGE, padx=8, pady=3)
        self.tr_badge_plat.pack(side="left", padx=(0, 6))

        self.tr_badge_gold = tk.Label(tier_row, text="🥇 Gold: -", bg="#3b2910", fg="#fbbf24", font=theme.FONT_BADGE, padx=8, pady=3)
        self.tr_badge_gold.pack(side="left", padx=(0, 6))

        self.tr_badge_silver = tk.Label(tier_row, text="🥈 Silver: -", bg="#334155", fg="#cbd5e1", font=theme.FONT_BADGE, padx=8, pady=3)
        self.tr_badge_silver.pack(side="left", padx=(0, 6))

        self.tr_badge_bronze = tk.Label(tier_row, text="🥉 Bronze: -", bg="#3b1d11", fg="#f97316", font=theme.FONT_BADGE, padx=8, pady=3)
        self.tr_badge_bronze.pack(side="left")

        # Controls & Filter Row
        ctrl_row = tk.Frame(prog_card, bg=theme.BG_CARD)
        ctrl_row.pack(fill="x")

        self.tr_filter_key = "all"
        self.tr_filter_var = tk.StringVar(value=t("trophies.filter_all"))
        self.tr_filter_combo = ttk.Combobox(ctrl_row, textvariable=self.tr_filter_var, state="readonly", width=16)
        self.tr_filter_combo.pack(side="left", padx=(0, 8))
        self._update_trophy_filter_options()
        self.tr_filter_combo.bind("<<ComboboxSelected>>", self._on_trophy_filter_selected)

        self.tr_refresh_btn = ttk.Button(ctrl_row, text=t("common.refresh"), style="Small.TButton", command=self._refresh_trophies_page)
        self.tr_refresh_btn.pack(side="left", padx=(0, 6))

        self.tr_reset_btn = ttk.Button(ctrl_row, text=t("trophies.reset_btn"), style="Small.TButton", command=self._reset_trophies)
        self.tr_reset_btn.pack(side="left", padx=(0, 6))

        self.tr_folder_btn = ttk.Button(ctrl_row, text=t("trophies.open_folder_btn"), style="Small.TButton", command=self._open_trophy_folder)
        self.tr_folder_btn.pack(side="left", padx=(0, 6))

        self.tr_texts_btn = ttk.Button(ctrl_row, text=t("trophies.custom_texts_btn"), style="Small.TButton", command=self._edit_trophy_texts)
        self.tr_texts_btn.pack(side="left")

        # Scrollable Trophy List Card
        list_card = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid")
        list_card.pack(fill="both", expand=True)

        self.tr_canvas = tk.Canvas(list_card, bg=theme.BG_CARD, bd=0, highlightthickness=0)
        self.tr_scrollbar = ttk.Scrollbar(list_card, orient="vertical", command=self.tr_canvas.yview)
        self.tr_inner_frame = tk.Frame(self.tr_canvas, bg=theme.BG_CARD)

        self.tr_canvas.configure(xscrollcommand=None, yscrollcommand=self.tr_scrollbar.set)
        self.tr_canvas_win = self.tr_canvas.create_window((0, 0), window=self.tr_inner_frame, anchor="nw")

        self.tr_canvas.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self.tr_scrollbar.pack(side="right", fill="y", pady=8)

        def _on_frame_configure(_e):
            self.tr_canvas.configure(scrollregion=self.tr_canvas.bbox("all"))

        def _on_canvas_configure(e):
            self.tr_canvas.itemconfig(self.tr_canvas_win, width=e.width)

        self.tr_inner_frame.bind("<Configure>", _on_frame_configure)
        self.tr_canvas.bind("<Configure>", _on_canvas_configure)

        page.on_show = self._refresh_trophies_page  # type: ignore[attr-defined]

    # ---- 6. CONTROLS PAGE ----
    def _build_controls_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["controls"] = page

        # Header
        self.ctrl_title = tk.Label(page, text=t("controls.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.ctrl_title.pack(anchor="w")
        self.ctrl_subtitle = tk.Label(page, text=t("controls.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.ctrl_subtitle.pack(anchor="w", pady=(2, 10))

        # Card 1: Device Hardware Mapping
        c1 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=10)
        c1.pack(fill="x", pady=(0, 10))

        self.ctrl_hw_title = tk.Label(c1, text=t("controls.hw_section_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.ctrl_hw_title.pack(anchor="w", pady=(0, 2))

        self.ctrl_hw_desc = tk.Label(c1, text=t("controls.hw_section_desc"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION)
        self.ctrl_hw_desc.pack(anchor="w", pady=(0, 4))

        self.ctrl_hw_status = tk.Label(c1, text="", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY_BOLD)
        self.ctrl_hw_status.pack(anchor="w", pady=(0, 6))

        hw_btn_box = tk.Frame(c1, bg=theme.BG_CARD)
        hw_btn_box.pack(anchor="w")

        self.ctrl_btn_map_device = ttk.Button(hw_btn_box, text=t("controls.btn_map_device"), style="Small.TButton", command=lambda: self.map_pad([]))
        self.ctrl_btn_map_device.pack(side="left", padx=(0, 6))

        self.ctrl_btn_map_sticks = ttk.Button(hw_btn_box, text=t("controls.btn_map_sticks"), style="Small.TButton", command=lambda: self.map_pad(["--sticks"]))
        self.ctrl_btn_map_sticks.pack(side="left", padx=(0, 6))

        self.ctrl_btn_reset_device = ttk.Button(hw_btn_box, text=t("controls.btn_reset_device"), style="Small.TButton", command=self.reset_map)
        self.ctrl_btn_reset_device.pack(side="left")

        # Card 2: In-Game Button Remapping (Embedded Table)
        c2 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=10)
        c2.pack(fill="both", expand=True)

        # Header of Card 2 with Style Selector
        top_row = tk.Frame(c2, bg=theme.BG_CARD)
        top_row.pack(fill="x", pady=(0, 4))

        self.ctrl_remap_title = tk.Label(top_row, text=t("controls.remap_section_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.ctrl_remap_title.pack(side="left")

        style_box = tk.Frame(top_row, bg=theme.BG_CARD)
        style_box.pack(side="right")

        self.ctrl_style_lbl = tk.Label(style_box, text=t("controls.style_label"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION)
        self.ctrl_style_lbl.pack(side="left", padx=(0, 6))

        self.ctrl_style_combo = ttk.Combobox(
            style_box,
            textvariable=self.ctrl_style_var,
            values=["PlayStation", "Xbox", "Nintendo"],
            state="readonly",
            width=12,
        )
        self.ctrl_style_combo.pack(side="left")
        self.ctrl_style_combo.bind("<<ComboboxSelected>>", self._on_ctrl_style_changed)

        self.ctrl_remap_desc = tk.Label(c2, text=t("controls.remap_section_desc"), bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION, wraplength=700, justify="left")
        self.ctrl_remap_desc.pack(anchor="w", pady=(0, 6))

        # Notice banner for analog sticks
        notice_box = tk.Frame(c2, bg=theme.BG_ELEVATED, bd=1, relief="solid", padx=10, pady=6)
        notice_box.pack(fill="x", pady=(0, 8))

        self.ctrl_notice_title = tk.Label(notice_box, text=f"ℹ️ {t('controls.analog_notice_title')}", bg=theme.BG_ELEVATED, fg=theme.ACCENT_GOLD, font=theme.FONT_CAPTION_BOLD)
        self.ctrl_notice_title.pack(anchor="w")

        self.ctrl_notice_desc = tk.Label(notice_box, text=t("controls.analog_notice_desc"), bg=theme.BG_ELEVATED, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION, wraplength=720, justify="left")
        self.ctrl_notice_desc.pack(anchor="w", pady=(1, 0))

        # Scrollable table container
        table_container = tk.Frame(c2, bg=theme.BG_CARD)
        table_container.pack(fill="both", expand=True, pady=(0, 8))

        self.ctrl_canvas = tk.Canvas(table_container, bg=theme.BG_CARD, bd=0, highlightthickness=0)
        self.ctrl_scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.ctrl_canvas.yview)
        self.ctrl_inner_frame = tk.Frame(self.ctrl_canvas, bg=theme.BG_CARD)

        self.ctrl_canvas.configure(yscrollcommand=self.ctrl_scrollbar.set)
        self.ctrl_canvas_win = self.ctrl_canvas.create_window((0, 0), window=self.ctrl_inner_frame, anchor="nw")

        self.ctrl_canvas.pack(side="left", fill="both", expand=True)
        self.ctrl_scrollbar.pack(side="right", fill="y")

        def _on_ctrl_frame_configure(_e):
            self.ctrl_canvas.configure(scrollregion=self.ctrl_canvas.bbox("all"))

        def _on_ctrl_canvas_configure(e):
            self.ctrl_canvas.itemconfig(self.ctrl_canvas_win, width=e.width)

        self.ctrl_inner_frame.bind("<Configure>", _on_ctrl_frame_configure)
        self.ctrl_canvas.bind("<Configure>", _on_ctrl_canvas_configure)

        # Build Action Rows
        self._build_ctrl_action_rows()

        # Bottom Action & Status Bar
        bottom_bar = tk.Frame(c2, bg=theme.BG_CARD)
        bottom_bar.pack(fill="x", pady=(4, 0))

        self.ctrl_reset_all_btn = ttk.Button(bottom_bar, text=t("controls.btn_reset_all"), style="Small.TButton", command=self._on_ctrl_reset_all)
        self.ctrl_reset_all_btn.pack(side="left")

        self.ctrl_status_lbl = tk.Label(bottom_bar, text="", bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_CAPTION)
        self.ctrl_status_lbl.pack(side="left", padx=12)

        self.ctrl_save_btn = ttk.Button(bottom_bar, text=t("controls.btn_save"), style="Primary.TButton", command=self._on_ctrl_save)
        self.ctrl_save_btn.pack(side="right")

        self.bind("<Escape>", self._on_ctrl_escape)
        page.on_show = self._refresh_controls_page  # type: ignore[attr-defined]

    # ---- 7. SETTINGS PAGE ----
    def _build_settings_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["settings"] = page

        # Header
        self.set_title = tk.Label(page, text=t("settings.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.set_title.pack(anchor="w")
        self.set_subtitle = tk.Label(page, text=t("settings.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.set_subtitle.pack(anchor="w", pady=(2, 14))

        # Card 1: Language & General
        c1 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=12)
        c1.pack(fill="x", pady=(0, 12))
        c1.columnconfigure(1, weight=1)

        self.set_grp_gen = tk.Label(c1, text=t("settings.group_general"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.set_grp_gen.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.set_lang_lbl = tk.Label(c1, text=t("settings.language_label"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY)
        self.set_lang_lbl.grid(row=1, column=0, sticky="w", padx=(0, 16))

        self.lang_var = tk.StringVar(value=i18n.SUPPORTED_LANGUAGES.get(self.cfg.get("language", "en"), "English"))
        self.lang_combo = ttk.Combobox(c1, textvariable=self.lang_var, state="readonly", width=20, values=list(i18n.SUPPORTED_LANGUAGES.values()))
        self.lang_combo.grid(row=1, column=1, sticky="w")
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_combo_selected)

        # Card 2: Graphics & Display
        c2 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=12)
        c2.pack(fill="x", pady=(0, 12))
        c2.columnconfigure(1, weight=1)
        c2.columnconfigure(3, weight=1)

        self.set_grp_gfx = tk.Label(c2, text=t("settings.group_graphics"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.set_grp_gfx.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        # Display mode
        self.mode_var = tk.StringVar(value=self.cfg.get("display_mode", "borderless"))
        modes_box = tk.Frame(c2, bg=theme.BG_CARD)
        modes_box.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        for label, val in DISPLAY_MODES:
            ttk.Radiobutton(modes_box, text=label, value=val, variable=self.mode_var).pack(side="left", padx=(0, 16))

        # Resolution, Upscale, FPS Limit, Anisotropy
        self.set_res_lbl = tk.Label(c2, text=t("settings.window_size_label"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY)
        self.set_res_lbl.grid(row=2, column=0, sticky="w", pady=4)
        self.res_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.res_var, state="readonly", width=18, values=[n for n, _ in RESOLUTIONS]).grid(row=2, column=1, sticky="ew", padx=(6, 16), pady=4)

        self.set_up_lbl = tk.Label(c2, text=t("settings.upscale_label"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY)
        self.set_up_lbl.grid(row=2, column=2, sticky="w", pady=4)
        self.up_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.up_var, state="readonly", width=18, values=[n for n, _ in UPSCALERS]).grid(row=2, column=3, sticky="ew", padx=(6, 0), pady=4)

        self.set_fps_lbl = tk.Label(c2, text=t("settings.fps_limit_label"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY)
        self.set_fps_lbl.grid(row=3, column=0, sticky="w", pady=4)
        self.fps_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.fps_var, state="readonly", width=18, values=[n for n, _ in FPS_LIMITS]).grid(row=3, column=1, sticky="ew", padx=(6, 16), pady=4)

        self.set_aniso_lbl = tk.Label(c2, text=t("settings.aniso_label"), bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY)
        self.set_aniso_lbl.grid(row=3, column=2, sticky="w", pady=4)
        self.aniso_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.aniso_var, state="readonly", width=18, values=[n for n, _ in ANISO]).grid(row=3, column=3, sticky="ew", padx=(6, 0), pady=4)

        # Checkboxes
        chk_box = tk.Frame(c2, bg=theme.BG_CARD)
        chk_box.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.vsync_var = tk.BooleanVar(value=self.cfg.get("vsync", True))
        self.rcas_var = tk.BooleanVar(value=self.cfg.get("rcas", False))
        ttk.Checkbutton(chk_box, text="VSync", variable=self.vsync_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(chk_box, text="Sharpening (RCAS)", variable=self.rcas_var).pack(side="left")

        # Card 3: Audio & Diagnostics
        c3 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=12)
        c3.pack(fill="x", pady=(0, 14))

        self.set_grp_audio = tk.Label(c3, text=t("settings.group_audio"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_HEADING)
        self.set_grp_audio.pack(anchor="w", pady=(0, 8))

        self.audio_var = tk.BooleanVar(value=self.cfg.get("audio_log", False))
        self.wav_var = tk.BooleanVar(value=False)

        audio_chk_box = tk.Frame(c3, bg=theme.BG_CARD)
        audio_chk_box.pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(audio_chk_box, text="Audio debug log", variable=self.audio_var, command=self._audio_toggled).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(audio_chk_box, text="+ WAV capture", variable=self.wav_var, command=self._wav_toggled).pack(side="left")

        util_box = tk.Frame(c3, bg=theme.BG_CARD)
        util_box.pack(anchor="w")
        self.set_btn_saves = ttk.Button(util_box, text=t("settings.open_saves_btn"), style="Small.TButton", command=self.open_saves)
        self.set_btn_saves.pack(side="left", padx=(0, 6))
        self.set_btn_user = ttk.Button(util_box, text=t("settings.open_user_btn"), style="Small.TButton", command=lambda: self._open_dir(str(USER)))
        self.set_btn_user.pack(side="left")

        # Save Button
        save_box = tk.Frame(page, bg=theme.BG_MAIN)
        save_box.pack(anchor="w")
        self.set_save_btn = ttk.Button(save_box, text=t("settings.save_btn"), style="Primary.TButton", command=self._save_settings)
        self.set_save_btn.pack(side="left")

        page.on_show = self._refresh_settings_page  # type: ignore[attr-defined]

    # ---- 8. DIAGNOSTICS PAGE ----
    def _build_diagnostics_page(self):
        page = tk.Frame(self.content_container, bg=theme.BG_MAIN, padx=24, pady=20)
        self.page_frames["diagnostics"] = page

        # Header
        self.diag_title = tk.Label(page, text=t("diagnostics.title"), bg=theme.BG_MAIN, fg=theme.TEXT_PRIMARY, font=theme.FONT_TITLE)
        self.diag_title.pack(anchor="w")
        self.diag_subtitle = tk.Label(page, text=t("diagnostics.subtitle"), bg=theme.BG_MAIN, fg=theme.TEXT_SECONDARY, font=theme.FONT_BODY)
        self.diag_subtitle.pack(anchor="w", pady=(2, 14))

        # Log selector tabs
        tab_row = tk.Frame(page, bg=theme.BG_MAIN)
        tab_row.pack(fill="x", pady=(0, 8))

        self.diag_active_log = "last_run"

        self.diag_btn_run = ttk.Button(tab_row, text=t("diagnostics.tab_last_run"), style="Small.TButton", command=lambda: self._switch_log("last_run"))
        self.diag_btn_run.pack(side="left", padx=(0, 4))

        self.diag_btn_prep = ttk.Button(tab_row, text=t("diagnostics.tab_prepare"), style="Small.TButton", command=lambda: self._switch_log("prepare"))
        self.diag_btn_prep.pack(side="left", padx=(0, 4))

        self.diag_btn_aud = ttk.Button(tab_row, text=t("diagnostics.tab_audio"), style="Small.TButton", command=lambda: self._switch_log("audio"))
        self.diag_btn_aud.pack(side="left", padx=(0, 10))

        self.diag_btn_open = ttk.Button(tab_row, text=t("diagnostics.btn_open_external"), style="Small.TButton", command=self._open_active_log)
        self.diag_btn_open.pack(side="right")

        self.diag_btn_copy = ttk.Button(tab_row, text=t("diagnostics.btn_copy"), style="Small.TButton", command=self._copy_log)
        self.diag_btn_copy.pack(side="right", padx=(0, 4))

        # Log viewer Card
        c1 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid")
        c1.pack(fill="both", expand=True, pady=(0, 12))

        self.log_text = tk.Text(c1, bg=theme.BG_INPUT, fg=theme.TEXT_PRIMARY, font=theme.FONT_MONO, relief="flat", padx=12, pady=10)
        log_scroll = ttk.Scrollbar(c1, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # Environment Info Box
        c2 = tk.Frame(page, bg=theme.BG_CARD, bd=1, relief="solid", padx=14, pady=10)
        c2.pack(fill="x")

        self.diag_env_title = tk.Label(c2, text=t("diagnostics.env_title"), bg=theme.BG_CARD, fg=theme.ACCENT_GOLD, font=theme.FONT_BODY_BOLD)
        self.diag_env_title.pack(anchor="w")

        self.diag_env_lbl = tk.Label(c2, text="", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION, justify="left")
        self.diag_env_lbl.pack(anchor="w", pady=(2, 0))

        page.on_show = self._refresh_diagnostics_page  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # Dynamic i18n UI Refresh
    # -----------------------------------------------------------------------

    def _on_lang_combo_selected(self, _e=None):
        name_to_code = {v: k for k, v in i18n.SUPPORTED_LANGUAGES.items()}
        selected_code = name_to_code.get(self.lang_var.get(), "en")
        if selected_code != self.cfg.get("language"):
            self.cfg["language"] = selected_code
            save_config(self.cfg)
            i18n.set_language(selected_code)

    def _on_language_changed(self, _new_lang: str):
        """Immediately refreshes all visible text across the shell and active page."""
        self.tagline_lbl.config(text=t("app.tagline"))
        self.sidebar_target_lbl.config(text=t("app.target"))
        self.btn_credits.config(text=t("app.credits"))

        # Refresh sidebar navigation item labels
        for pid, frame in self.nav_buttons.items():
            key = frame._key  # type: ignore[attr-defined]
            icon = frame._icon  # type: ignore[attr-defined]
            frame._lbl.config(text=f"  {icon}  {t(key)}")  # type: ignore[attr-defined]

        # Refresh Home
        self.home_hero_title.config(text=t("home.hero_title"))
        self.home_hero_subtitle.config(text=t("home.hero_subtitle"))
        self.play.config(text=t("home.launch_game"))
        self.stop.config(text=t("home.stop_game"))
        for card in (self.card_game, self.card_update, self.card_dlc, self.card_controls, self.card_trophies):
            card._title_lbl.config(text=t(card._title_key))  # type: ignore[attr-defined]
            card._btn.config(text=t("common.manage"))  # type: ignore[attr-defined]

        # Refresh Game Files
        self.gf_title.config(text=t("game_files.title"))
        self.gf_subtitle.config(text=t("game_files.subtitle"))
        self.gf_path_lbl.config(text=t("game_files.path_label"))
        self.gf_hint.config(text=t("game_files.path_hint"))
        self.gf_browse_btn.config(text=t("common.browse"))
        self.gf_open_btn.config(text=t("common.open_folder"))
        self.gf_insp_title.config(text=t("game_files.inspection_title"))
        self.gf_img_title.config(text=t("game_files.image_status_title"))
        self.gf_reprep_btn.config(text=t("game_files.reprepare_btn"))

        # Refresh Updates
        self.up_title.config(text=t("updates.title"))
        self.up_subtitle.config(text=t("updates.subtitle"))
        self.up_path_lbl.config(text=t("updates.path_label"))
        self.up_hint.config(text=t("updates.path_hint"))
        self.up_browse_btn.config(text=t("common.browse"))
        self.up_clear_btn.config(text=t("common.clear"))
        self.up_open_btn.config(text=t("common.open_folder"))
        self.up_overlay_title.config(text=t("updates.overlay_title"))
        self.up_overlay_desc.config(text=t("updates.overlay_desc"))

        # Refresh DLC
        self.dlc_title.config(text=t("dlc.title"))
        self.dlc_subtitle.config(text=t("dlc.subtitle"))
        self.dlc_path_lbl.config(text=t("dlc.path_label"))
        self.dlc_hint.config(text=t("dlc.path_hint"))
        self.dlc_browse_btn.config(text=t("common.browse"))
        self.dlc_clear_btn.config(text=t("common.clear"))
        self.dlc_open_btn.config(text=t("common.open_folder"))
        self.dlc_manifest_title.config(text=t("dlc.manifest_title"))

        # Refresh Trophies
        self.tr_title.config(text=t("trophies.title"))
        self.tr_subtitle.config(text=t("trophies.subtitle"))
        self.tr_prog_header.config(text=t("trophies.progress_header"))
        self.tr_refresh_btn.config(text=t("common.refresh"))
        self.tr_reset_btn.config(text=t("trophies.reset_btn"))
        self.tr_folder_btn.config(text=t("trophies.open_folder_btn"))
        self.tr_texts_btn.config(text=t("trophies.custom_texts_btn"))
        self._update_trophy_filter_options()
        try:
            trophies_module.sync_trophy_texts_file(USER, language=_new_lang)
        except Exception:
            pass
        self._refresh_trophies_page()

        # Refresh Controls
        self.ctrl_title.config(text=t("controls.title"))
        self.ctrl_subtitle.config(text=t("controls.subtitle"))
        self.ctrl_hw_title.config(text=t("controls.hw_section_title"))
        self.ctrl_hw_desc.config(text=t("controls.hw_section_desc"))
        self.ctrl_btn_map_device.config(text=t("controls.btn_map_device"))
        self.ctrl_btn_map_sticks.config(text=t("controls.btn_map_sticks"))
        self.ctrl_btn_reset_device.config(text=t("controls.btn_reset_device"))
        self.ctrl_remap_title.config(text=t("controls.remap_section_title"))
        self.ctrl_remap_desc.config(text=t("controls.remap_section_desc"))
        self.ctrl_style_lbl.config(text=t("controls.style_label"))
        self.ctrl_notice_title.config(text=f"ℹ️ {t('controls.analog_notice_title')}")
        self.ctrl_notice_desc.config(text=t("controls.analog_notice_desc"))
        self.ctrl_reset_all_btn.config(text=t("controls.btn_reset_all"))
        self.ctrl_save_btn.config(text=t("controls.btn_save"))
        self._build_ctrl_action_rows()
        self._refresh_controls_page()

        # Refresh Settings
        self.set_title.config(text=t("settings.title"))
        self.set_subtitle.config(text=t("settings.subtitle"))
        self.set_grp_gen.config(text=t("settings.group_general"))
        self.set_lang_lbl.config(text=t("settings.language_label"))
        self.set_grp_gfx.config(text=t("settings.group_graphics"))
        self.set_res_lbl.config(text=t("settings.window_size_label"))
        self.set_up_lbl.config(text=t("settings.upscale_label"))
        self.set_fps_lbl.config(text=t("settings.fps_limit_label"))
        self.set_aniso_lbl.config(text=t("settings.aniso_label"))
        self.set_grp_audio.config(text=t("settings.group_audio"))
        self.set_btn_saves.config(text=t("settings.open_saves_btn"))
        self.set_btn_user.config(text=t("settings.open_user_btn"))
        self.set_save_btn.config(text=t("settings.save_btn"))

        # Refresh Diagnostics
        self.diag_title.config(text=t("diagnostics.title"))
        self.diag_subtitle.config(text=t("diagnostics.subtitle"))
        self.diag_btn_run.config(text=t("diagnostics.tab_last_run"))
        self.diag_btn_prep.config(text=t("diagnostics.tab_prepare"))
        self.diag_btn_aud.config(text=t("diagnostics.tab_audio"))
        self.diag_btn_open.config(text=t("diagnostics.btn_open_external"))
        self.diag_btn_copy.config(text=t("diagnostics.btn_copy"))
        self.diag_env_title.config(text=t("diagnostics.env_title"))

        self._refresh_all_statuses()

    # -----------------------------------------------------------------------
    # Status Refreshers
    # -----------------------------------------------------------------------

    def _refresh_all_statuses(self):
        self._refresh_image_label()
        self._refresh_home_status()
        self._refresh_game_files_page()
        self._refresh_updates_page()
        self._refresh_dlc_page()
        self._refresh_controls_page()

    def _refresh_home_status(self):
        game = self.game_var.get().strip() if hasattr(self, "game_var") else self.cfg.get("game", "")
        update_dir = self.update_var.get().strip() if hasattr(self, "update_var") else self.cfg.get("update_dir", "")
        dlc_dir = self.dlc_var.get().strip() if hasattr(self, "dlc_var") else self.cfg.get("dlc_dir", "")

        # 1. Game Card
        if not game or not (Path(game) / "eboot.bin").is_file():
            self.card_game._val_lbl.config(text=t("home.card_game_missing"), fg=theme.COLOR_ERROR)  # type: ignore[attr-defined]
        elif image_ready(game):
            ver = game_app_ver(game) or "1.00"
            self.card_game._val_lbl.config(text=t("home.card_game_ready", version=ver), fg=theme.COLOR_SUCCESS)  # type: ignore[attr-defined]
        else:
            self.card_game._val_lbl.config(text=t("home.card_game_not_ready"), fg=theme.COLOR_WARNING)  # type: ignore[attr-defined]

        # 2. Update Card
        if update_dir and (Path(update_dir) / "eboot.bin").is_file():
            uver = game_app_ver(update_dir) or "1.02"
            self.card_update._val_lbl.config(text=t("home.card_update_active", version=uver), fg=theme.COLOR_SUCCESS)  # type: ignore[attr-defined]
        else:
            self.card_update._val_lbl.config(text=t("home.card_update_none"), fg=theme.TEXT_SECONDARY)  # type: ignore[attr-defined]

        # 3. DLC Card
        dlc_count = 0
        if dlc_dir and Path(dlc_dir).is_dir():
            try:
                base_title = game_title_id(game) or "CUSA01159"
                dlc_count = len(dlc.discover_addons(dlc_dir, title_id=base_title))
            except Exception:
                pass
        if dlc_count > 0:
            self.card_dlc._val_lbl.config(text=t("home.card_dlc_active", count=dlc_count), fg=theme.COLOR_SUCCESS)  # type: ignore[attr-defined]
        else:
            self.card_dlc._val_lbl.config(text=t("home.card_dlc_none"), fg=theme.TEXT_SECONDARY)  # type: ignore[attr-defined]

        # 4. Controller Card
        pad_spec = build_pad_map_spec(self.cfg.get("pad_controls"))
        if pad_spec:
            count = len(pad_spec.split(","))
            self.card_controls._val_lbl.config(text=t("home.card_controls_custom", count=count), fg=theme.ACCENT_GOLD)  # type: ignore[attr-defined]
        elif MAPPING.exists():
            self.card_controls._val_lbl.config(text=t("home.card_controls_hw_custom"), fg=theme.COLOR_SUCCESS)  # type: ignore[attr-defined]
        else:
            self.card_controls._val_lbl.config(text=t("home.card_controls_default"), fg=theme.TEXT_SECONDARY)  # type: ignore[attr-defined]

        # 5. Trophies Card
        trp_path = trophies_module.resolve_trophy_package(game, update_dir)
        if trp_path and trp_path.is_file():
            unlocked = trophies_module.read_unlocked_trophies(USER / "trophies.dat")
            count = len(unlocked)
            pct = (count / 43.0) * 100.0
            self.card_trophies._val_lbl.config(text=t("home.card_trophies_progress", unlocked=count, total=43, percent=f"{pct:.1f}"), fg=theme.ACCENT_GOLD)  # type: ignore[attr-defined]
        else:
            self.card_trophies._val_lbl.config(text=t("trophies.no_package"), fg=theme.TEXT_MUTED)  # type: ignore[attr-defined]

    def _refresh_image_label(self):
        """Kept for backward compatibility with existing tests and UI."""
        game = self.game_var.get().strip() if hasattr(self, "game_var") else self.cfg.get("game", "")
        update_dir = self.update_var.get().strip() if hasattr(self, "update_var") else self.cfg.get("update_dir", "")
        dlc_dir = self.dlc_var.get().strip() if hasattr(self, "dlc_var") else self.cfg.get("dlc_dir", "")

        base_ver = game_app_ver(game) if game and Path(game).is_dir() else None
        base_title = game_title_id(game) if game and Path(game).is_dir() else None
        update_ver = game_app_ver(update_dir) if update_dir and Path(update_dir).is_dir() else None
        update_title = game_title_id(update_dir) if update_dir and Path(update_dir).is_dir() else None

        title_id = update_title or base_title or "CUSA01159"
        effective_ver = update_ver or base_ver
        ver_tag = f" (v{effective_ver})" if effective_ver else ""

        if not game or not (Path(game) / "eboot.bin").is_file():
            text = "No eboot.bin in this folder."
        elif update_dir and not (Path(update_dir) / "eboot.bin").is_file():
            text = "No eboot.bin in the update folder."
        elif update_title and base_title and update_title != base_title:
            text = f"Title ID mismatch: base is {base_title}, update is {update_title}."
        elif image_ready(game):
            parts = [f"Game image ready: v{base_ver or '?'}" if update_ver else f"Game image ready{ver_tag}"]
            if update_ver:
                parts.append(f"update v{update_ver}")
            text = " + ".join(parts) + "."
        else:
            text = f"The game image{ver_tag} is made on the first start (about a minute); again if game files change."

        if hasattr(self, "image_label"):
            self.image_label.config(text=text)

    def _refresh_game_files_page(self):
        game = self.game_var.get().strip()
        if not game or not Path(game).is_dir():
            self.gf_meta_lbl.config(text=t("home.card_game_missing"), fg=theme.COLOR_ERROR)
            return

        lines = []
        try:
            sfo = find_sfo(game)
            tid = game_title_id(game)
            ver = game_app_ver(game)
            eboot = (Path(game) / "eboot.bin").is_file()
            modules = len(list((Path(game) / "sce_module").glob("*.prx"))) if (Path(game) / "sce_module").is_dir() else 0

            lines.append(f"{t('game_files.title_id')}: {tid or 'Unknown'}")
            lines.append(f"{t('game_files.app_ver')}: {ver or 'Unknown'}")
            lines.append(f"{t('game_files.eboot_status')}: {'Valid' if eboot else 'Missing'}")
            lines.append(f"{t('game_files.modules_status')}: {modules} PRX module(s) found")
            self.gf_meta_lbl.config(text="\n".join(lines), fg=theme.TEXT_PRIMARY)
        except Exception as e:
            self.gf_meta_lbl.config(text=f"Inspection error: {e}", fg=theme.COLOR_ERROR)

    def _refresh_updates_page(self):
        update_dir = self.update_var.get().strip()
        if not update_dir or not Path(update_dir).is_dir():
            base_ver = game_app_ver(self.game_var.get().strip()) or "1.00"
            self.up_status_lbl.config(text=t("updates.status_none", version=base_ver), fg=theme.TEXT_SECONDARY)
            return

        uver = game_app_ver(update_dir) or "Unknown"
        self.up_status_lbl.config(text=t("updates.status_active", version=uver), fg=theme.COLOR_SUCCESS)

    def _refresh_dlc_page(self):
        dlc_dir = self.dlc_var.get().strip()
        self.dlc_text.config(state="normal")
        self.dlc_text.delete("1.0", "end")

        if not dlc_dir or not Path(dlc_dir).is_dir():
            self.dlc_count_badge.config(text=t("dlc.count_badge", count=0))
            self.dlc_text.insert("1.0", f"{t('dlc.empty_state_title')}\n\n{t('dlc.empty_state_desc')}")
            self.dlc_text.config(state="disabled")
            return

        try:
            base_title = game_title_id(self.game_var.get().strip()) or "CUSA01159"
            addons = dlc.discover_addons(dlc_dir, title_id=base_title)
            self.dlc_count_badge.config(text=t("dlc.count_badge", count=len(addons)))

            header = f"{'ENTITLEMENT ID':<24} | {'FOLDER':<28} | {'STATUS'}\n"
            divider = "-" * 70 + "\n"
            self.dlc_text.insert("end", header + divider)

            for item in addons:
                ent = item.get("entitlement_id", "UNKNOWN")
                folder = item.get("folder", "")
                self.dlc_text.insert("end", f"{ent:<24} | {folder:<28} | Ready\n")
        except Exception as e:
            self.dlc_count_badge.config(text=t("common.error"))
            self.dlc_text.insert("1.0", f"DLC Discovery Error:\n{e}")

        self.dlc_text.config(state="disabled")

    def _open_trophy_folder(self):
        game = self.game_var.get().strip() if hasattr(self, "game_var") else self.cfg.get("game", "")
        update_dir = self.update_var.get().strip() if hasattr(self, "update_var") else self.cfg.get("update_dir", "")
        trp = trophies_module.resolve_trophy_package(game, update_dir)
        target = trp.parent if trp and trp.parent.is_dir() else USER
        target.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(target)
        except Exception:
            pass

    def _update_trophy_filter_options(self):
        labels = [t(k) for _, k in TROPHY_FILTERS]
        self.tr_filter_combo["values"] = labels
        cur_code = getattr(self, "tr_filter_key", "all")
        for code, k in TROPHY_FILTERS:
            if code == cur_code:
                self.tr_filter_var.set(t(k))
                break

    def _on_trophy_filter_selected(self, _e=None):
        selected_text = self.tr_filter_var.get()
        for code, k in TROPHY_FILTERS:
            if t(k) == selected_text or code == selected_text:
                self.tr_filter_key = code
                break
        self._render_trophy_list()

    def _edit_trophy_texts(self):
        target = trophies_module.sync_trophy_texts_file(USER, language=i18n.get_language())
        if target.is_file():
            try:
                os.startfile(target)
            except Exception:
                pass

    def _refresh_trophies_page(self):
        game = self.game_var.get().strip() if hasattr(self, "game_var") else self.cfg.get("game", "")
        update_dir = self.update_var.get().strip() if hasattr(self, "update_var") else self.cfg.get("update_dir", "")
        trp_path = trophies_module.resolve_trophy_package(game, update_dir)

        self.trophy_icons_raw = {}
        if trp_path and trp_path.is_file():
            try:
                self.trophy_icons_raw = trophies_module.read_trp_icons(trp_path)
            except Exception:
                self.trophy_icons_raw = {}

        total_count = len(self.trophy_icons_raw) or trophies_module.DEFAULT_TROPHY_COUNT
        trophy_ids = sorted(self.trophy_icons_raw.keys()) if self.trophy_icons_raw else list(range(total_count))

        user_labels, user_texts = trophies_module.load_trophy_texts(
            USER, language=i18n.get_language(), include_defaults=True
        )
        if not user_texts:
            user_texts = trophies_module.get_default_trophy_texts(i18n.get_language())

        self.current_trophies = []
        for tr_id in trophy_ids:
            name, desc = user_texts.get(tr_id, (f"Trophy #{tr_id}", ""))
            icon_bytes = self.trophy_icons_raw.get(tr_id, b"")
            tier = trophies_module.trophy_tier(icon_bytes, tr_id)
            if not tier or tier == "unknown":
                if tr_id == 0:
                    tier = "platinum"
                elif tr_id <= 2:
                    tier = "gold"
                elif tr_id <= 12:
                    tier = "silver"
                else:
                    tier = "bronze"

            self.current_trophies.append({
                "id": tr_id,
                "name": name,
                "description": desc,
                "tier": tier,
                "icon": icon_bytes,
            })

        self._render_trophy_list()

    def _render_trophy_list(self):
        for widget in self.tr_inner_frame.winfo_children():
            widget.destroy()

        unlocked_set = trophies_module.read_unlocked_trophies(USER / "trophies.dat")
        total = len(self.current_trophies) or trophies_module.DEFAULT_TROPHY_COUNT
        unlocked_count = len([t for t in self.current_trophies if t["id"] in unlocked_set])
        pct = (unlocked_count / float(total)) * 100.0 if total > 0 else 0.0

        self.tr_prog_summary.config(text=t("trophies.progress_summary", unlocked=unlocked_count, total=total, percent=f"{pct:.1f}"))
        self.tr_progressbar.configure(value=pct)

        # Tier breakdown counts
        tier_counts = {"platinum": [0, 0], "gold": [0, 0], "silver": [0, 0], "bronze": [0, 0]}
        for tr in self.current_trophies:
            tr_tier = tr["tier"]
            if tr_tier not in tier_counts:
                tr_tier = "bronze"
            tier_counts[tr_tier][1] += 1
            if tr["id"] in unlocked_set:
                tier_counts[tr_tier][0] += 1

        self.tr_badge_plat.config(text=f"🏆 {t('trophies.cat_platinum')}: {tier_counts['platinum'][0]}/{tier_counts['platinum'][1]}")
        self.tr_badge_gold.config(text=f"🥇 {t('trophies.cat_gold')}: {tier_counts['gold'][0]}/{tier_counts['gold'][1]}")
        self.tr_badge_silver.config(text=f"🥈 {t('trophies.cat_silver')}: {tier_counts['silver'][0]}/{tier_counts['silver'][1]}")
        self.tr_badge_bronze.config(text=f"🥉 {t('trophies.cat_bronze')}: {tier_counts['bronze'][0]}/{tier_counts['bronze'][1]}")

        filter_val = getattr(self, "tr_filter_key", "all")

        for tr in self.current_trophies:
            is_unlocked = tr["id"] in unlocked_set
            if filter_val == "unlocked" and not is_unlocked:
                continue
            if filter_val == "locked" and is_unlocked:
                continue

            row = tk.Frame(self.tr_inner_frame, bg=theme.BG_CARD, bd=1, relief="solid", padx=10, pady=8)
            row.pack(fill="x", pady=2)
            row.columnconfigure(1, weight=1)

            # Icon or placeholder
            icon_img = None
            if Image and ImageTk and tr["icon"]:
                cache_key = f"{tr['id']}_{'u' if is_unlocked else 'l'}"
                if cache_key in self.trophy_photo_cache:
                    icon_img = self.trophy_photo_cache[cache_key]
                else:
                    try:
                        import io
                        raw_im = Image.open(io.BytesIO(tr["icon"])).convert("RGBA").resize((44, 44), getattr(Image, "Resampling", Image).LANCZOS)
                        if not is_unlocked and ImageEnhance:
                            raw_im = ImageEnhance.Brightness(raw_im.convert("RGB")).enhance(0.4)
                        icon_img = ImageTk.PhotoImage(raw_im)
                        self.trophy_photo_cache[cache_key] = icon_img
                    except Exception:
                        icon_img = None

            if icon_img:
                icon_lbl = tk.Label(row, image=icon_img, bg=theme.BG_CARD)
                icon_lbl.image = icon_img  # type: ignore[attr-defined]
                icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 10), sticky="w")
            else:
                emoji = {"platinum": "🏆", "gold": "🥇", "silver": "🥈", "bronze": "🥉"}.get(tr["tier"], "🏆")
                icon_lbl = tk.Label(row, text=emoji, bg=theme.BG_CARD, font=("Segoe UI", 18))
                icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 10), sticky="w")

            # Title row: Title + Tier Badge
            title_box = tk.Frame(row, bg=theme.BG_CARD)
            title_box.grid(row=0, column=1, sticky="w")

            t_title = tk.Label(title_box, text=tr["name"] or f"Trophy #{tr['id']}", bg=theme.BG_CARD, fg=theme.TEXT_PRIMARY, font=theme.FONT_BODY_BOLD)
            t_title.pack(side="left", padx=(0, 8))

            tier_colors = {
                "platinum": ("#1e293b", "#93c5fd"),
                "gold": ("#3b2910", "#fbbf24"),
                "silver": ("#334155", "#cbd5e1"),
                "bronze": ("#3b1d11", "#f97316"),
            }
            t_bg, t_fg = tier_colors.get(tr["tier"], ("#1e293b", "#93c5fd"))
            tier_badge_text = t(f"trophies.cat_{tr['tier']}").upper()
            tier_badge = tk.Label(title_box, text=tier_badge_text, bg=t_bg, fg=t_fg, font=theme.FONT_BADGE, padx=6, pady=1)
            tier_badge.pack(side="left")

            # Description
            t_desc = tk.Label(row, text=tr["description"] or "", bg=theme.BG_CARD, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION, justify="left", wraplength=620)
            t_desc.grid(row=1, column=1, sticky="w")

            # Status Badge
            badge_text = f"✓ {t('trophies.status_unlocked')}" if is_unlocked else f"🔒 {t('trophies.status_locked')}"
            badge_bg = "#14331d" if is_unlocked else "#1c1e24"
            badge_fg = theme.COLOR_SUCCESS if is_unlocked else theme.TEXT_MUTED
            badge = tk.Label(row, text=badge_text, bg=badge_bg, fg=badge_fg, font=theme.FONT_BADGE, padx=8, pady=3)
            badge.grid(row=0, column=2, rowspan=2, padx=(8, 0), sticky="e")

    def _reset_trophies(self):
        if messagebox.askyesno(t("trophies.reset_confirm_title"), t("trophies.reset_confirm_msg"), parent=self):
            ok, bak = trophies_module.reset_trophies(USER / "trophies.dat")
            messagebox.showinfo(t("common.success"), t("trophies.reset_success_msg", path=str(bak or "")), parent=self)
            self._refresh_trophies_page()
            self._refresh_home_status()

    # ---- CONTROLLER CONTROLS EMBEDDED METHODS ----

    def _build_ctrl_action_rows(self):
        for widget in self.ctrl_inner_frame.winfo_children():
            widget.destroy()

        self.ctrl_row_combos.clear()
        self.ctrl_row_combo_vars.clear()
        self.ctrl_row_cap_btns.clear()
        self.ctrl_row_title_lbls.clear()
        self.ctrl_row_desc_lbls.clear()

        style = self.ctrl_style_var.get().lower()
        is_id = i18n.get_language().startswith("id")
        display_choices = [controls_module.format_button_label(btn, style) for btn in AVAILABLE_SDL_BUTTONS]

        for action_id, default_btn, lbl_en, lbl_id, desc_en, desc_id in controls_module.LOGICAL_ACTIONS:
            row = tk.Frame(self.ctrl_inner_frame, bg=theme.BG_ELEVATED, bd=1, relief="solid", padx=10, pady=6)
            row.pack(fill="x", pady=2)
            row.columnconfigure(0, weight=2)
            row.columnconfigure(1, weight=3)

            # Left Info
            left_box = tk.Frame(row, bg=theme.BG_ELEVATED)
            left_box.grid(row=0, column=0, sticky="w")

            title_txt = lbl_id if is_id else lbl_en
            desc_txt = desc_id if is_id else desc_en

            t_lbl = tk.Label(left_box, text=title_txt, bg=theme.BG_ELEVATED, fg=theme.ACCENT_GOLD, font=theme.FONT_BODY_BOLD)
            t_lbl.pack(anchor="w")
            d_lbl = tk.Label(left_box, text=desc_txt, bg=theme.BG_ELEVATED, fg=theme.TEXT_SECONDARY, font=theme.FONT_CAPTION)
            d_lbl.pack(anchor="w")

            self.ctrl_row_title_lbls[action_id] = t_lbl
            self.ctrl_row_desc_lbls[action_id] = d_lbl

            # Right Controls
            right_box = tk.Frame(row, bg=theme.BG_ELEVATED)
            right_box.grid(row=0, column=1, sticky="e")

            current_btn = self.ctrl_controls.get(action_id, default_btn)
            combo_var = tk.StringVar(value=controls_module.format_button_label(current_btn, style))

            combo = ttk.Combobox(
                right_box,
                textvariable=combo_var,
                values=display_choices,
                state="readonly",
                width=24,
            )
            combo.pack(side="left", padx=(0, 6))

            def _make_combo_handler(act=action_id, c_var=combo_var):
                return lambda _e=None: self._on_ctrl_combo_selected(act, c_var.get())

            combo.bind("<<ComboboxSelected>>", _make_combo_handler())

            cap_btn = ttk.Button(
                right_box,
                text=t("controls.btn_capture"),
                style="Small.TButton",
                command=lambda act=action_id: self._start_ctrl_capture(act),
            )
            cap_btn.pack(side="left", padx=(0, 4))

            reset_btn = ttk.Button(
                right_box,
                text=t("controls.btn_reset_action"),
                style="Small.TButton",
                command=lambda act=action_id: self._reset_ctrl_action(act),
            )
            reset_btn.pack(side="left")

            self.ctrl_row_combos[action_id] = combo
            self.ctrl_row_combo_vars[action_id] = combo_var
            self.ctrl_row_cap_btns[action_id] = cap_btn

    def _on_ctrl_combo_selected(self, action_id: str, display_text: str):
        style = self.ctrl_style_var.get().lower()
        target_token = "None"
        for btn in AVAILABLE_SDL_BUTTONS:
            if controls_module.format_button_label(btn, style) == display_text:
                target_token = btn
                break

        swapped = controls_module.bind_button(self.ctrl_controls, action_id, target_token, swap_duplicates=True)
        if swapped and swapped in self.ctrl_row_combo_vars:
            swapped_btn = self.ctrl_controls.get(swapped, "None")
            self.ctrl_row_combo_vars[swapped].set(controls_module.format_button_label(swapped_btn, style))
            self.ctrl_status_lbl.config(
                text=t("controls.swapped_notice", old_action=action_id.upper(), new_action=swapped.upper()),
                fg=theme.ACCENT_GOLD,
            )
        else:
            self.ctrl_status_lbl.config(text="")

        self._update_ctrl_spec_status()

    def _start_ctrl_capture(self, action_id: str):
        self._cancel_ctrl_capture()
        self.ctrl_capturing_action = action_id

        if not self.ctrl_capture_helper:
            self.ctrl_capture_helper = controls_module.SDL3CaptureHelper(BIN)

        if action_id in self.ctrl_row_cap_btns:
            self.ctrl_row_cap_btns[action_id].config(text=t("controls.btn_capturing"))

        self.ctrl_status_lbl.config(
            text=f"🎮 {t('controls.btn_capturing')}",
            fg=theme.COLOR_WARNING,
        )
        self._poll_ctrl_capture()

    def _poll_ctrl_capture(self):
        if not self.ctrl_capturing_action:
            return

        if self.ctrl_capture_helper:
            detected = self.ctrl_capture_helper.poll_pressed_button()
            if detected:
                action = self.ctrl_capturing_action
                self._cancel_ctrl_capture()
                style = self.ctrl_style_var.get().lower()
                swapped = controls_module.bind_button(self.ctrl_controls, action, detected, swap_duplicates=True)
                if action in self.ctrl_row_combo_vars:
                    self.ctrl_row_combo_vars[action].set(controls_module.format_button_label(detected, style))
                if swapped and swapped in self.ctrl_row_combo_vars:
                    swapped_btn = self.ctrl_controls.get(swapped, "None")
                    self.ctrl_row_combo_vars[swapped].set(controls_module.format_button_label(swapped_btn, style))
                    self.ctrl_status_lbl.config(
                        text=t("controls.swapped_notice", old_action=action.upper(), new_action=swapped.upper()),
                        fg=theme.ACCENT_GOLD,
                    )
                else:
                    self.ctrl_status_lbl.config(text="")
                self._update_ctrl_spec_status()
                return

        self.ctrl_capture_timer = self.after(50, self._poll_ctrl_capture)

    def _cancel_ctrl_capture(self):
        if self.ctrl_capture_timer:
            self.after_cancel(self.ctrl_capture_timer)
            self.ctrl_capture_timer = None
        if self.ctrl_capturing_action and self.ctrl_capturing_action in self.ctrl_row_cap_btns:
            self.ctrl_row_cap_btns[self.ctrl_capturing_action].config(text=t("controls.btn_capture"))
        self.ctrl_capturing_action = None

    def _on_ctrl_escape(self, _e=None):
        if self.ctrl_capturing_action:
            self._cancel_ctrl_capture()
            self.ctrl_status_lbl.config(text="")

    def _reset_ctrl_action(self, action_id: str):
        self._cancel_ctrl_capture()
        controls_module.reset_button(self.ctrl_controls, action_id)
        style = self.ctrl_style_var.get().lower()
        btn = self.ctrl_controls.get(action_id, "None")
        if action_id in self.ctrl_row_combo_vars:
            self.ctrl_row_combo_vars[action_id].set(controls_module.format_button_label(btn, style))
        self._update_ctrl_spec_status()

    def _on_ctrl_reset_all(self):
        self._cancel_ctrl_capture()
        if messagebox.askyesno(t("controls.reset_confirm_title"), t("controls.reset_confirm_msg"), parent=self):
            controls_module.reset_all_controls(self.ctrl_controls)
            style = self.ctrl_style_var.get().lower()
            for act, c_var in self.ctrl_row_combo_vars.items():
                btn = self.ctrl_controls.get(act, "None")
                c_var.set(controls_module.format_button_label(btn, style))
            self._update_ctrl_spec_status()

    def _on_ctrl_save(self):
        self._cancel_ctrl_capture()
        self.cfg["pad_controls"] = controls_module.diff_controls(self.ctrl_controls)
        self.cfg["pad_style"] = self.ctrl_style_var.get().lower()
        save_config(self.cfg)
        self._refresh_all_statuses()
        self.ctrl_status_lbl.config(text=f"✓ {t('controls.save_success')}", fg=theme.COLOR_SUCCESS)

    def _update_ctrl_spec_status(self):
        spec = controls_module.build_pad_map_spec(self.ctrl_controls)
        if spec:
            self.ctrl_status_lbl.config(text=t("controls.active_spec", spec=spec), fg=theme.ACCENT_GOLD)
        else:
            self.ctrl_status_lbl.config(text=t("controls.default_spec"), fg=theme.TEXT_SECONDARY)

    def _on_ctrl_style_changed(self, _e=None):
        style = self.ctrl_style_var.get().lower()
        self.cfg["pad_style"] = style
        display_choices = [controls_module.format_button_label(btn, style) for btn in AVAILABLE_SDL_BUTTONS]
        for act, combo in self.ctrl_row_combos.items():
            combo.configure(values=display_choices)
            btn = self.ctrl_controls.get(act, controls_module.DEFAULT_PAD_CONTROLS.get(act, "None"))
            if act in self.ctrl_row_combo_vars:
                self.ctrl_row_combo_vars[act].set(controls_module.format_button_label(btn, style))

    def _refresh_controls_page(self):
        if MAPPING.exists():
            self.ctrl_hw_status.config(text=t("controls.hw_status_custom"), fg=theme.COLOR_SUCCESS)
        else:
            self.ctrl_hw_status.config(text=t("controls.hw_status_default"), fg=theme.TEXT_SECONDARY)

        style = self.ctrl_style_var.get().lower()
        for act, c_var in self.ctrl_row_combo_vars.items():
            btn = self.ctrl_controls.get(act, controls_module.DEFAULT_PAD_CONTROLS.get(act, "None"))
            c_var.set(controls_module.format_button_label(btn, style))

        self._update_ctrl_spec_status()

    def _refresh_settings_page(self):
        self._load_ini_into_ui()

    def _refresh_diagnostics_page(self):
        self._switch_log(self.diag_active_log)
        core_exe = BIN / "sumeragi-core.exe"
        sdl_dll = BIN / "SDL3.dll"
        lines = [
            f"OS: {sys.platform}  ·  Python: {sys.version.split()[0]}",
            f"{t('diagnostics.core_label')} {core_exe} ({'Found' if core_exe.is_file() else 'Missing'})",
            f"{t('diagnostics.sdl_label')} {sdl_dll} ({'Found' if sdl_dll.is_file() else 'Missing'})",
            f"Active Game: {self.game_var.get().strip() or 'None'}",
        ]
        self.diag_env_lbl.config(text="\n".join(lines))

    def _switch_log(self, log_type: str):
        self.diag_active_log = log_type
        target = LOG if log_type == "last_run" else (PREPARE_LOG if log_type == "prepare" else AUDIO_LOG)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        if target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                self.log_text.insert("1.0", content)
            except Exception as e:
                self.log_text.insert("1.0", f"Error reading log: {e}")
        else:
            self.log_text.insert("1.0", t("diagnostics.no_log_yet"))
        self.log_text.config(state="disabled")

    def _open_active_log(self):
        target = LOG if self.diag_active_log == "last_run" else (PREPARE_LOG if self.diag_active_log == "prepare" else AUDIO_LOG)
        if target.is_file():
            os.startfile(target)
        else:
            messagebox.showinfo(t("common.status"), t("diagnostics.no_log_yet"), parent=self)

    def _copy_log(self):
        text = self.log_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo(t("common.copied"), t("common.copied"), parent=self)

    # -----------------------------------------------------------------------
    # Browser Helpers & Launch Operations
    # -----------------------------------------------------------------------

    def _browse(self):
        path = filedialog.askdirectory(initialdir=self.game_var.get() or str(ROOT), mustexist=True)
        if path:
            self.game_var.set(os.path.normpath(path))
            self.cfg["game"] = self.game_var.get()
            save_config(self.cfg)
            self._art()
            if hasattr(self, "home_cover_lbl") and self.cover:
                self.home_cover_lbl.config(image=self.cover)
            self._refresh_all_statuses()

    def _browse_update(self):
        path = filedialog.askdirectory(initialdir=self.update_var.get() or self.game_var.get() or str(ROOT), mustexist=True)
        if path:
            self.update_var.set(os.path.normpath(path))
            self.cfg["update_dir"] = self.update_var.get()
            save_config(self.cfg)
            self._art()
            if hasattr(self, "home_cover_lbl") and self.cover:
                self.home_cover_lbl.config(image=self.cover)
            self._refresh_all_statuses()

    def _clear_update(self):
        self.update_var.set("")
        self.cfg["update_dir"] = ""
        save_config(self.cfg)
        self._art()
        if hasattr(self, "home_cover_lbl") and self.cover:
            self.home_cover_lbl.config(image=self.cover)
        self._refresh_all_statuses()

    def _browse_dlc(self):
        path = filedialog.askdirectory(initialdir=self.dlc_var.get() or self.game_var.get() or str(ROOT), mustexist=True)
        if path:
            self.dlc_var.set(os.path.normpath(path))
            self.cfg["dlc_dir"] = self.dlc_var.get()
            save_config(self.cfg)
            self._refresh_all_statuses()

    def _clear_dlc(self):
        self.dlc_var.set("")
        self.cfg["dlc_dir"] = ""
        save_config(self.cfg)
        self._refresh_all_statuses()

    def _open_dir(self, dir_path: str):
        p = Path(dir_path) if dir_path else USER
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
        os.startfile(p)

    def _force_reprepare(self):
        if messagebox.askyesno(t("game_files.reprepare_confirm_title"), t("game_files.reprepare_confirm_msg"), parent=self):
            if STAMP.is_file():
                try:
                    STAMP.unlink()
                except OSError:
                    pass
            self._refresh_all_statuses()

    # -----------------------------------------------------------------------
    # Backend Launch Lifecycle & Environment Construction
    # -----------------------------------------------------------------------

    def _cleanup_leftover_views(self):
        if not OUT.is_dir():
            return
        for item in OUT.iterdir():
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
        )
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
            },
        )

    def _save_settings(self):
        self._collect()
        messagebox.showinfo(t("common.success"), t("settings.save_success"), parent=self)

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
        return env

    def on_play(self):
        if self.busy or self.proc:
            return
        self._collect()
        try:
            trophies_module.sync_trophy_texts_file(USER, language=self.cfg.get("language", "en"))
        except Exception:
            pass
        game = Path(self.cfg["game"]) if self.cfg["game"] else None
        update_dir = Path(self.cfg["update_dir"]) if self.cfg.get("update_dir") else None
        dlc_dir = Path(self.cfg["dlc_dir"]) if self.cfg.get("dlc_dir") else None

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
            game_update.validate_game(game, update_dir)
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
        threading.Thread(target=self._prepare_then_launch, args=(game, update_dir, exe, dlc_dir), daemon=True).start()
        self.after(200, self._wait_prepare)

    def _progress(self, text):
        self.pending_text = text

    def _prepare_then_launch(self, game, update_dir, exe, dlc_dir=None):
        self.pending_text = t("home.game_starting")
        error = None
        view = None
        effective_game = game

        if update_dir:
            self.pending_text = "Preparing game update overlay…"
            try:
                view = game_update.create_view(game, update_dir, OUT)
                effective_game = view
            except (ValueError, OSError) as err:
                self.pending = (str(err), None, None, [], "", None)
                return

        try:
            if not image_ready(effective_game):
                error = prepare_image(effective_game, self._progress)
            patch_args, notice = [], ""
            if not error and self.cfg.get("fps_limit", 60) != 60:
                try:
                    writes, _ = patches_module.build(OUT / "eboot.elf", OUT / "patches.bin", True)
                except OSError:
                    writes = []
                if writes:
                    patch_args = ["--patches", str(OUT / "patches.bin")]
                else:
                    self.cfg["fps_limit"] = 60
                    notice = "Frame limiter not found in this eboot.bin: staying at 60.  "

            addon_args = []
            if not error and dlc_dir:
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

    def _make_window_icon(self, game):
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

            if self.play_now:
                self.destroy()
                return

            if code in (0, None):
                self.status.config(text=t("home.game_closed"), fg=theme.ACCENT_GOLD)
            else:
                self.status.config(text=t("home.game_exited_code", code=f"{code & 0xFFFFFFFF:#x}"), fg=theme.COLOR_ERROR)
            self._load_ini_into_ui()
        self.after(500, self._poll)

    # -----------------------------------------------------------------------
    # Controller Mappers & Utility Windows
    # -----------------------------------------------------------------------

    def map_pad(self, extra):
        candidates = [
            BIN / "sumeragi-pad-mapper.exe",
            BIN / "basara4-pad-mapper.exe",
            ROOT / "out" / "sumeragi-pad-mapper.exe",
            ROOT / "out" / "basara4-pad-mapper.exe",
            ROOT / "tools" / "sumeragi-pad-mapper.exe",
            ROOT / "tools" / "basara4-pad-mapper.exe",
        ]
        exe = None
        for cand in candidates:
            if cand.is_file():
                exe = cand
                break

        if not exe or not exe.is_file():
            messagebox.showerror(
                t("dialog.error_title"),
                t("dialog.device_mapper_missing", path=str(BIN)),
                parent=self,
            )
            return

        env = os.environ.copy()
        clang = Path(r"C:\msys64\clang64\bin")
        if clang.is_dir():
            env["PATH"] = str(clang) + os.pathsep + env.get("PATH", "")
        if BIN.is_dir():
            env["PATH"] = str(BIN) + os.pathsep + env.get("PATH", "")
        if OUT.is_dir():
            env["PATH"] = str(OUT) + os.pathsep + env.get("PATH", "")
        USER.mkdir(parents=True, exist_ok=True)

        subprocess.Popen([str(exe), str(MAPPING)] + extra, env=env, creationflags=0x00000010)
        self.status.config(text=t("dialog.device_map_prompt"))
        self.after(4000, self._refresh_all_statuses)

    def reset_map(self):
        if MAPPING.exists() and messagebox.askyesno(t("common.reset"), t("dialog.device_reset_confirm"), parent=self):
            os.replace(MAPPING, str(MAPPING) + ".bak")
            self._refresh_all_statuses()

    def open_log(self):
        self.show_page("diagnostics")

    def open_audio_log(self):
        self.show_page("diagnostics")
        self._switch_log("audio")

    def open_saves(self):
        path = USER / "savedata"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_trophies(self):
        self.show_page("trophies")

    def open_controller_controls(self):
        self.show_page("controls")

    def _close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(t("dialog.stop_confirm_title"), t("dialog.stop_confirm_msg"), parent=self):
                return
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

        try:
            self._collect()
        except Exception:
            pass

        self.destroy()


if __name__ == "__main__":
    Launcher(play_now="--play" in sys.argv).mainloop()
