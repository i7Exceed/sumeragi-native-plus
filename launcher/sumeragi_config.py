#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Configuration, defaults, paths, and INI management for Sumeragi Native+."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import sumeragi_i18n as i18n
import sumeragi_theme as theme

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent.parent
BIN, OUT, USER, SCRIPTS = ROOT / "bin", ROOT / "out", ROOT / "user", ROOT / "scripts"
CONFIG = USER / "launcher.json"
INI = USER / "sumeragi.ini"
OLD_INI = USER / "basara4.ini"
ANCIENT_INI = USER / "spartanport.ini"
WINDOW_ICON = USER / "window_icon.bmp"
CORE = BIN / "sumeragi-core.exe" if (BIN / "sumeragi-core.exe").is_file() else BIN / "basara4-core.exe"
VERSION = "1.0.4"
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
    ("isa_rewrite.py", []),
]
NO_WINDOW = 0x08000000

# Configuration Defaults & Options
DEFAULTS: Dict[str, Any] = {
    "game": "",
    "update_dir": "",
    "dlc_dir": "",
    "mods_dir": str(ROOT / "mods"),
    "enabled_mods": [],
    "extra_mods": [],
    "display_mode": "borderless",
    "vsync": True,
    "fps_limit": 60,
    "rcas": False,
    "anisotropy": 0,
    "resolution": "native",
    "upscale": "off",
    "gpu_index": -1,
    "audio_log": False,
    "audio_wav": False,
    "pad_controls": {},
    "pad_style": "playstation",
    "keymap": {},
    "mouse_camera": True,
    "mouse_sens": 100,
    "input_mode": "controller",
    "cheats": [],
    "render_trace": False,
    "language": "en",
}

DEFAULT_PC_KEYMAP: Dict[str, str] = {
    "square": "Mouse Left",       # Normal Attack (Serangan Biasa)
    "circle": "Mouse Right",      # Heavy / Special Attack / Basara Skill
    "triangle": "Q",              # Secondary Skill (Khas Hack & Slash)
    "cross": "Space",             # Jump / Lompat
    "l1": "Left Shift",           # Guard / Tangkis / Evade
    "r1": "E",                    # Special Skill 2 (Interact / Skill Kanan)
    "r2": "F",                    # Basara Attack (Ultimate Finisher)
    "l2": "R",                    # Sengoku Drive / Poise Boost (Rage/Burst)
    "touchpad": "Tab",            # Taunt / Provoke
    "options": "Escape",          # Pause / Menu
    "up": "Up",                   # D-Pad Up
    "down": "Down",               # D-Pad Down
    "left": "Left",               # D-Pad Left
    "right": "Right",             # D-Pad Right
    "l3": "Z",                    # L3
    "r3": "C",                    # R3 (Lock-On)
}

ACTION_DESCRIPTIONS: List[Tuple[str, str, str]] = [
    ("square", "Normal Attack (Serangan Biasa)", "Kotak / Square"),
    ("triangle", "Special Skill 1 (Skill Utama)", "Segitiga / Triangle"),
    ("cross", "Jump (Lompat)", "Silang / Cross"),
    ("circle", "Basara Attack (Ultimate)", "Lingkaran / Circle"),
    ("l1", "Guard / Tangkis / Dash", "L1"),
    ("r1", "Special Skill 2 (Skill Tambahan)", "R1"),
    ("r2", "Special Skill 3 (Skill Karakter)", "R2"),
    ("l2", "Sengoku Drive / Boost", "L2"),
    ("touchpad", "Taunt / Provoke", "Touchpad / Tab"),
    ("options", "Pause / In-Game Menu", "Options / Enter"),
    ("up", "D-Pad Up (Navigasi / Perintah)", "D-Pad Atas"),
    ("down", "D-Pad Down (Navigasi / Perintah)", "D-Pad Bawah"),
    ("left", "D-Pad Left (Navigasi / Perintah)", "D-Pad Kiri"),
    ("right", "D-Pad Right (Navigasi / Perintah)", "D-Pad Kanan"),
    ("l3", "L3 Action", "L3"),
    ("r3", "R3 Action / Lock-on", "R3"),
]

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
    ("640 x 360  (360p - Low-End)", "360p"),
    ("854 x 480  (480p - Low-End)", "480p"),
    ("960 x 540  (540p - Balanced)", "540p"),
    ("1280 x 720  (720p HD)", "720p"),
    ("1600 x 900  (900p HD+)", "900p"),
    ("1920 x 1080  (1080p Native)", "native"),
    ("2560 x 1440  (1440p 2K)", "1440p"),
    ("3200 x 1800  (1800p QHD+)", "1800p"),
    ("3840 x 2160  (4K UHD)", "4K"),
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


def find_game() -> str:
    """The first folder under game\\ that holds an eboot.bin."""
    base = ROOT / "game"
    if (base / "eboot.bin").is_file():
        return str(base)
    for child in sorted(base.iterdir()) if base.is_dir() else []:
        if (child / "eboot.bin").is_file():
            return str(child)
    return ""


def find_dlc() -> str:
    """The default dlc\\ folder if it exists next to the launcher."""
    base = ROOT / "dlc"
    if (base / "CUSA01159").is_dir():
        return str(base)
    return ""


def _get_active_config_path() -> Path:
    import sys
    launcher_mod = sys.modules.get("sumeragi_launcher")
    if launcher_mod and hasattr(launcher_mod, "CONFIG"):
        return Path(getattr(launcher_mod, "CONFIG"))
    return CONFIG


def _get_active_user_path() -> Path:
    import sys
    launcher_mod = sys.modules.get("sumeragi_launcher")
    if launcher_mod and hasattr(launcher_mod, "USER"):
        return Path(getattr(launcher_mod, "USER"))
    return USER


def _get_active_root() -> Path:
    import sys
    launcher_mod = sys.modules.get("sumeragi_launcher")
    if launcher_mod and hasattr(launcher_mod, "ROOT"):
        return Path(getattr(launcher_mod, "ROOT"))
    return ROOT


def resolve_mod_path(entry: str | Path, mods_dir: str | Path | None = None) -> Path:
    """Resolves a saved mod identifier (absolute path, relative path, or folder name)."""
    p = Path(entry)
    if p.is_absolute():
        return p
    if mods_dir:
        cand = Path(mods_dir) / p
        if cand.exists() or len(p.parts) == 1:
            return cand
    return _get_active_root() / p


def resolve_enabled_mods(cfg: Dict[str, Any]) -> List[Path]:
    """Returns resolved Paths of active mods in overlay order."""
    mods_dir = cfg.get("mods_dir") or str(_get_active_root() / "mods")
    raw_list = cfg.get("enabled_mods")
    if not isinstance(raw_list, list):
        return []
    resolved: List[Path] = []
    seen: Set[str] = set()
    for item in raw_list:
        if not isinstance(item, str) or not item.strip():
            continue
        p = resolve_mod_path(item.strip(), mods_dir)
        key = os.path.normpath(str(p)).casefold()
        if key not in seen:
            seen.add(key)
            resolved.append(p)
    return resolved


def _sanitize_mod_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    seen: Set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        val = item.strip()
        if not val:
            continue
        key = os.path.normpath(val).casefold()
        if key not in seen:
            seen.add(key)
            cleaned.append(val)
    return cleaned


def load_config() -> Dict[str, Any]:
    import copy
    cfg = copy.deepcopy(DEFAULTS)
    active_config = _get_active_config_path()
    loaded: Dict[str, Any] = {}
    try:
        raw = json.loads(active_config.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            loaded = raw
            cfg.update(loaded)
    except (OSError, ValueError):
        pass
    if not cfg["game"] or not (Path(cfg["game"]) / "eboot.bin").is_file():
        cfg["game"] = find_game()
    if not cfg.get("dlc_dir") or not Path(cfg["dlc_dir"]).is_dir():
        found = find_dlc()
        if found:
            cfg["dlc_dir"] = found
    if "mods_dir" not in loaded or not isinstance(cfg.get("mods_dir"), str) or not cfg["mods_dir"].strip():
        cfg["mods_dir"] = str(_get_active_root() / "mods")
    cfg["enabled_mods"] = _sanitize_mod_list(cfg.get("enabled_mods"))
    cfg["extra_mods"] = _sanitize_mod_list(cfg.get("extra_mods"))
    # Ensure language is initialized
    lang = cfg.get("language") or cfg.get("lang") or "en"
    if lang not in i18n.SUPPORTED_LANGUAGES:
        lang = "en"
    cfg["language"] = lang
    i18n.set_language(lang, notify=False)
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    active_user = _get_active_user_path()
    active_config = _get_active_config_path()
    active_user.mkdir(parents=True, exist_ok=True)
    active_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def read_ini(path: str | Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.strip().split("=", 1)
                values[key] = value
    except OSError:
        pass
    return values


def write_ini(path: str | Path, updates: Dict[str, Any]) -> None:
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
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def check_commit_limit_mb() -> Optional[int]:
    """Returns available virtual memory (page file commit limit) in MB, or None if unavailable."""
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullAvailPageFile // (1024 * 1024)
    except Exception:
        pass
    return None

