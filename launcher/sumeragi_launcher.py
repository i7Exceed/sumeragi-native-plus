"""Sumeragi Native+ Launcher - by i7Exceed (based on Basara 4 PC by Razz).

Runs Sengoku Basara 4 Sumeragi (PS4, CUSA01159) on the native PC runtime in bin\\ (sumeragi-core.exe / basara4-core.exe),
a fork of SpartanPort. Free software under the GNU GPL v2 or later; credits and licenses are in NOTICE.md.

Everything lives next to this program:
  bin\\   the runtime (sumeragi-core.exe / basara4-core.exe) and its DLLs
  game\\  the game dump (the folder with eboot.bin); another folder can be chosen
  dlc\\   optional extracted add-on content folders (auto-detected)
  out\\   the prepared game image, made automatically from eboot.bin
  user\\  saves, shader cache, settings, the log
"""
import hashlib
import importlib.util
import json
import os
import runpy
import shutil
import subprocess
import sys
import threading
from pathlib import Path

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
TAGLINE = "The Sumeragi experience, evolved."
AUTHOR = "i7Exceed"
AUTHOR_URL = "https://github.com/i7Exceed"
LOG = USER / "last_run.log"
PREPARE_LOG = USER / "prepare.log"
MAPPING = USER / "gamepad_mapping.txt"
AUDIO_LOG = USER / "audio_debug.log"
AUDIO_WAV = USER / "audio_wav"  # SPARTAN_AUDIO_WAV_DIR: float WAV capture of the mix and of long voices
STAMP = OUT / "prepared.json"
WAV_WARNING = ("WAV capture saves the final mix and every long voice as uncompressed audio in user\\audio_wav: about 70 MB per "
               "minute, up to 3 GB for one session.\n\nUse it only to find an audio problem, and delete the files afterwards.\n\n"
               "It applies to the next game start only and switches itself off after that. It also turns on the audio debug "
               "log. Turn it on?")
PIPELINE = [("prepare.py", []), ("link_libc.py", []), ("link_modules.py", []),
            ("content_profile.py", ["--sku", "full"])]
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

import tkinter as tk  # noqa: E402  (after the script mode, which needs no window)
from tkinter import filedialog, messagebox, ttk  # noqa: E402

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageTk  # type: ignore[import-not-found, import-untyped]
except ImportError:  # still works, just without artwork
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageTk = None

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
# pyrefly: ignore[missing-import]
import game_update  # noqa: E402
# pyrefly: ignore[missing-import]
from patches import find_sfo, game_title_id, game_app_ver  # noqa: E402
# pyrefly: ignore[missing-import]
import dlc  # noqa: E402
import sumeragi_patches as patches_module  # noqa: E402
from sumeragi_native_trophies import TrophiesWindow  # noqa: E402

DEFAULTS = {"game": "", "update_dir": "", "dlc_dir": "", "display_mode": "borderless", "vsync": True, "fps_limit": 60, "rcas": False,
            "anisotropy": 0, "resolution": "native", "upscale": "off", "audio_log": False, "audio_wav": False}
DISPLAY_MODES = [("Windowed", "windowed"), ("Borderless fullscreen", "borderless"),
                 ("Exclusive fullscreen", "fullscreen")]
FPS_LIMITS = [("60 (game default)", 60), ("90", 90), ("120", 120), ("144", 144), ("165", 165),
              ("240", 240), ("Unlimited", 0)]
RESOLUTIONS = [("1920 x 1080  (native)", "native"), ("1280 x 720", "720p"), ("1600 x 900", "900p"),
               ("2560 x 1440", "1440p"), ("3200 x 1800", "1800p"), ("3840 x 2160  (4K)", "4K")]
UPSCALERS = [("Off  (plain scaling)", "off"), ("FSR 1  (sharper)", "fsr1")]
ANISO = [("Off", 0), ("2x", 2), ("4x", 4), ("8x", 8), ("16x", 16)]
BG, PANEL, FG, MUTED, GOLD, RED = "#12100e", "#1c1916", "#eadfcb", "#8d8374", "#c9a24a", "#9c2b24"
RAZZ = "#e0526a"  # the accent of the by-Razz mark


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
            result = subprocess.run(script + [str(game), "--out", str(OUT)] + extra, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
            if result.returncode:
                return f"{name} failed (exit {result.returncode}). See user\\prepare.log"
    stamp_data = input_files_stamp(game)
    stamp_data["game"] = str(game)
    STAMP.write_text(json.dumps(stamp_data, indent=2), encoding="utf-8")
    return None


class Launcher(tk.Tk):
    def __init__(self, play_now=False):
        super().__init__()
        self.cfg = load_config()
        self.proc = None
        self.busy = False
        self.pending = None
        self.play_now = play_now
        self.update_view = None
        self._cleanup_leftover_views()
        self.title(f"{BRAND}  \u00b7  {TAGLINE}")
        self.configure(bg=BG)
        self.geometry("1020x630")
        self.minsize(980, 580)
        icon = Path(__file__).resolve().parent / "sumeragi.ico"
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass
        self._style()
        self._art()
        self._build()
        self._load_ini_into_ui()
        self._refresh_image_label()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(500, self._poll)
        if play_now:
            self.iconify()
            self.after(300, self.on_play)
        else:
            self.after(700, self._check_wav_leftovers)

    # ---- look ----
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, bordercolor=PANEL,
                    lightcolor=PANEL, darkcolor=PANEL, font=("Segoe UI", 10))
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("Card.TFrame", background="#181512")
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Panel.TLabel", background=PANEL, foreground=FG)
        s.configure("Card.TLabel", background="#181512", foreground=FG)
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        s.configure("CardMuted.TLabel", background="#181512", foreground=MUTED, font=("Segoe UI", 9))
        s.configure("Head.TLabel", background=PANEL, foreground=GOLD, font=("Segoe UI Semibold", 12))
        s.configure("Section.TLabel", background="#181512", foreground=GOLD, font=("Segoe UI", 10, "bold"))
        s.configure("Badge.TLabel", background="#26201a", foreground=GOLD, font=("Segoe UI Semibold", 9), padding=(8, 3))
        s.configure("TRadiobutton", background="#181512", foreground=FG)
        s.configure("TCheckbutton", background="#181512", foreground=FG)
        s.map("TRadiobutton", background=[("active", "#181512")], foreground=[("active", GOLD)])
        s.map("TCheckbutton", background=[("active", "#181512")], foreground=[("active", GOLD)])
        s.configure("TButton", background="#2a251f", foreground=FG, padding=(10, 5), borderwidth=0)
        s.map("TButton", background=[("active", "#3d362e"), ("disabled", "#1c1916")],
              foreground=[("disabled", MUTED)])
        s.configure("Small.TButton", padding=(8, 4), font=("Segoe UI", 9))
        s.configure("Play.TButton", background=RED, foreground="#ffffff", font=("Segoe UI Semibold", 13),
                    padding=(10, 10))
        s.map("Play.TButton", background=[("active", "#b8362d"), ("disabled", "#4a2522")])
        s.configure("Stop.TButton", background="#241e1b", foreground=MUTED, font=("Segoe UI", 9), padding=(6, 4))
        s.map("Stop.TButton", background=[("active", "#3a2a28"), ("disabled", "#1a1614")])
        s.configure("TCombobox", arrowcolor=GOLD, selectbackground=PANEL, selectforeground=FG)
        s.map("TCombobox", fieldbackground=[("readonly", "#14120f")], foreground=[("readonly", FG)])
        s.configure("TEntry", fieldbackground="#14120f", foreground=FG, insertcolor=GOLD)
        self.option_add("*TCombobox*Listbox.background", "#14120f")
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", RED)
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

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
            self.cover = ImageTk.PhotoImage(Image.open(sys_dir / "icon0.png").convert("RGB").resize((200, 200)))
        except OSError:
            pass
        try:
            bg = Image.open(sys_dir / "pic1.png").convert("RGB").resize((1020, 600))
            bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(6))).enhance(0.25)
            self.bg_img = ImageTk.PhotoImage(bg)
        except OSError:
            pass

    # ---- layout ----
    def _build(self):
        if self.bg_img:
            tk.Label(self, image=self.bg_img, bd=0).place(x=0, y=0, relwidth=1, relheight=1)
        root = ttk.Frame(self, style="TFrame")
        root.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.96, relheight=0.94)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # =========================================================================
        # LEFT SIDEBAR: Cover Art, Identity, Status, Play Action, Branding
        # =========================================================================
        left = ttk.Frame(root, style="Panel.TFrame", padding=(14, 14))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)

        if self.cover:
            cover_box = tk.Frame(left, bg="#2a241c", bd=1, relief="solid")
            cover_box.pack(pady=(0, 6))
            self.cover_label = tk.Label(cover_box, image=self.cover, bd=0, bg=PANEL)
            self.cover_label.pack(padx=2, pady=2)

        ttk.Label(left, text=BRAND, style="Head.TLabel").pack(pady=(4, 0))
        ttk.Label(left, text=TAGLINE, style="Panel.TLabel", font=("Segoe UI", 9, "italic")).pack()
        ttk.Label(left, text="Target: Sengoku Basara 4 Sumeragi", style="CardMuted.TLabel", font=("Segoe UI", 8)).pack(pady=(2, 0))
        self.ver_label = ttk.Label(left, text="CUSA01159", style="Badge.TLabel")
        self.ver_label.pack(pady=(6, 8))

        status_card = ttk.Frame(left, style="Card.TFrame", padding=(10, 8))
        status_card.pack(fill="x", pady=(0, 10))
        self.status = ttk.Label(status_card, text="Ready", style="CardMuted.TLabel", wraplength=190, justify="center")
        self.status.pack()

        self.play = ttk.Button(left, text="▶   PLAY GAME", style="Play.TButton", command=self.on_play)
        self.play.pack(fill="x", pady=(0, 4))
        self.stop = ttk.Button(left, text="■   Stop Game", style="Stop.TButton", command=self.on_stop, state="disabled")
        self.stop.pack(fill="x")

        # Bottom author & credits
        mark = ttk.Frame(left, style="Panel.TFrame")
        mark.pack(side="bottom", fill="x", pady=(8, 0))
        tk.Label(mark, text=BRAND.upper(), bg=PANEL, fg=GOLD, font=("Georgia", 10, "bold")).pack()
        tk.Label(mark, text=f"Developed by {AUTHOR}  ·  v{VERSION}", bg=PANEL, fg=GOLD, font=("Segoe UI Semibold", 8)).pack()
        tk.Label(mark, text="Based on Basara 4 PC (Razz) & SpartanPort", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack()
        ttk.Button(mark, text="Credits & Licenses", style="Small.TButton", command=self.show_credits).pack(fill="x", pady=(6, 0))

        # =========================================================================
        # RIGHT PANEL: Organized into 3 Clean Cards
        # =========================================================================
        right = ttk.Frame(root, style="Panel.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        # -------------------------------------------------------------------------
        # Card 1: Game & Update Files
        # -------------------------------------------------------------------------
        c1 = ttk.Frame(right, style="Card.TFrame", padding=(12, 10))
        c1.pack(fill="x", pady=(0, 10))
        c1.columnconfigure(1, weight=1)

        ttk.Label(c1, text="📁  GAME, UPDATE & DLC DIRECTORIES", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        # Game folder
        self.game_var = tk.StringVar(value=self.cfg["game"])
        self.game_var.trace_add("write", lambda *_: self._refresh_image_label())
        ttk.Label(c1, text="Game Folder", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(c1, textvariable=self.game_var).grid(row=1, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(c1, text="Browse…", style="Small.TButton", command=self._browse).grid(row=1, column=2, pady=3)

        # Update folder
        self.update_var = tk.StringVar(value=self.cfg.get("update_dir", ""))
        self.update_var.trace_add("write", lambda *_: self._refresh_image_label())
        ttk.Label(c1, text="Update Folder", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(c1, textvariable=self.update_var).grid(row=2, column=1, sticky="ew", padx=8, pady=3)
        up_btns = ttk.Frame(c1, style="Card.TFrame")
        up_btns.grid(row=2, column=2, sticky="w", pady=3)
        ttk.Button(up_btns, text="Browse…", style="Small.TButton", command=self._browse_update).pack(side="left")
        ttk.Button(up_btns, text="Clear", style="Small.TButton", command=self._clear_update).pack(side="left", padx=(4, 0))

        # DLC folder
        self.dlc_var = tk.StringVar(value=self.cfg.get("dlc_dir", ""))
        self.dlc_var.trace_add("write", lambda *_: self._refresh_image_label())
        ttk.Label(c1, text="DLC Folder", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(c1, textvariable=self.dlc_var).grid(row=3, column=1, sticky="ew", padx=8, pady=3)
        dlc_btns = ttk.Frame(c1, style="Card.TFrame")
        dlc_btns.grid(row=3, column=2, sticky="w", pady=3)
        ttk.Button(dlc_btns, text="Browse…", style="Small.TButton", command=self._browse_dlc).pack(side="left")
        ttk.Button(dlc_btns, text="Clear", style="Small.TButton", command=self._clear_dlc).pack(side="left", padx=(4, 0))

        # Status of image
        self.image_label = ttk.Label(c1, text="", style="CardMuted.TLabel")
        self.image_label.grid(row=4, column=1, columnspan=2, sticky="w", padx=8, pady=(2, 0))

        # -------------------------------------------------------------------------
        # Card 2: Graphics & Display Settings
        # -------------------------------------------------------------------------
        c2 = ttk.Frame(right, style="Card.TFrame", padding=(12, 10))
        c2.pack(fill="x", pady=(0, 10))
        c2.columnconfigure(1, weight=1)
        c2.columnconfigure(3, weight=1)

        ttk.Label(c2, text="🖥  GRAPHICS & DISPLAY", style="Section.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        # Display Mode Radios
        self.mode_var = tk.StringVar(value=self.cfg["display_mode"])
        modes = ttk.Frame(c2, style="Card.TFrame")
        modes.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        for label, key in DISPLAY_MODES:
            ttk.Radiobutton(modes, text=label, value=key, variable=self.mode_var).pack(side="left", padx=(0, 16))

        # Grid of comboboxes (2x2)
        ttk.Label(c2, text="Window Size", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        self.res_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.res_var, state="readonly", width=18,
                     values=[n for n, _ in RESOLUTIONS]).grid(row=2, column=1, sticky="ew", padx=(6, 16), pady=3)

        ttk.Label(c2, text="Upscaling", style="Card.TLabel").grid(row=2, column=2, sticky="w", pady=3)
        self.up_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.up_var, state="readonly", width=18,
                     values=[n for n, _ in UPSCALERS]).grid(row=2, column=3, sticky="ew", padx=(6, 0), pady=3)

        ttk.Label(c2, text="Frame Limit", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=3)
        self.fps_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.fps_var, state="readonly", width=18,
                     values=[n for n, _ in FPS_LIMITS]).grid(row=3, column=1, sticky="ew", padx=(6, 16), pady=3)

        ttk.Label(c2, text="Anisotropic", style="Card.TLabel").grid(row=3, column=2, sticky="w", pady=3)
        self.aniso_var = tk.StringVar()
        ttk.Combobox(c2, textvariable=self.aniso_var, state="readonly", width=18,
                     values=[n for n, _ in ANISO]).grid(row=3, column=3, sticky="ew", padx=(6, 0), pady=3)

        # Checkboxes
        checks = ttk.Frame(c2, style="Card.TFrame")
        checks.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 2))
        self.vsync_var = tk.BooleanVar(value=self.cfg["vsync"])
        self.rcas_var = tk.BooleanVar(value=self.cfg["rcas"])
        self.audio_var = tk.BooleanVar(value=self.cfg.get("audio_log", False))
        self.wav_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(checks, text="VSync", variable=self.vsync_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(checks, text="Sharpening (RCAS)", variable=self.rcas_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(checks, text="Audio debug log", variable=self.audio_var, command=self._audio_toggled).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(checks, text="+ WAV capture", variable=self.wav_var, command=self._wav_toggled).pack(side="left")

        # In-game menu hint
        ttk.Label(c2, text="* In-game menu: Tekan Insert di keyboard, atau R3 + L2 pada stik/controller.",
                  style="CardMuted.TLabel").grid(row=5, column=0, columnspan=4, sticky="w", pady=(4, 0))

        # -------------------------------------------------------------------------
        # Card 3: Controller & System Tools
        # -------------------------------------------------------------------------
        c3 = ttk.Frame(right, style="Card.TFrame", padding=(12, 10))
        c3.pack(fill="x")
        c3.columnconfigure(0, weight=1)

        ttk.Label(c3, text="🎮  CONTROLLER & UTILITIES", style="Section.TLabel").pack(anchor="w", pady=(0, 4))

        self.pad_label = ttk.Label(c3, text="", style="CardMuted.TLabel")
        self.pad_label.pack(anchor="w", pady=(0, 6))

        # Button rows
        btn_row1 = ttk.Frame(c3, style="Card.TFrame")
        btn_row1.pack(fill="x", pady=(0, 4))
        ttk.Button(btn_row1, text="🎮 Map Controller", style="Small.TButton", command=lambda: self.map_pad([])).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row1, text="🕹 Map Sticks Only", style="Small.TButton", command=lambda: self.map_pad(["--sticks"])).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row1, text="↺ Reset Mapping", style="Small.TButton", command=self.reset_map).pack(side="left")

        btn_row2 = ttk.Frame(c3, style="Card.TFrame")
        btn_row2.pack(fill="x")
        ttk.Button(btn_row2, text="💾 Open Saves", style="Small.TButton", command=self.open_saves).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row2, text="🏆 Trophies", style="Small.TButton", command=self.open_trophies).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row2, text="📜 Open Log", style="Small.TButton", command=self.open_log).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row2, text="🔊 Audio Log", style="Small.TButton", command=self.open_audio_log).pack(side="left")

        self._pad_text()

    # ---- helpers ----
    def _cleanup_leftover_views(self):
        if not OUT.is_dir():
            return
        for item in OUT.iterdir():
            if item.is_dir() and item.name.startswith("game-update-"):
                try:
                    game_update.remove_view(item)
                except Exception:
                    pass

    def _browse(self):
        path = filedialog.askdirectory(initialdir=self.game_var.get() or str(ROOT), mustexist=True)
        if path:
            self.game_var.set(os.path.normpath(path))
            self.cfg["game"] = self.game_var.get()
            self._art()
            if hasattr(self, "cover_label") and self.cover:
                self.cover_label.config(image=self.cover)

    def _browse_update(self):
        path = filedialog.askdirectory(initialdir=self.update_var.get() or self.game_var.get() or str(ROOT), mustexist=True)
        if path:
            self.update_var.set(os.path.normpath(path))
            self.cfg["update_dir"] = self.update_var.get()
            self._art()
            if hasattr(self, "cover_label") and self.cover:
                self.cover_label.config(image=self.cover)

    def _clear_update(self):
        self.update_var.set("")
        self.cfg["update_dir"] = ""
        self._art()
        if hasattr(self, "cover_label") and self.cover:
            self.cover_label.config(image=self.cover)

    def _browse_dlc(self):
        path = filedialog.askdirectory(initialdir=self.dlc_var.get() or self.game_var.get() or str(ROOT), mustexist=True)
        if path:
            self.dlc_var.set(os.path.normpath(path))
            self.cfg["dlc_dir"] = self.dlc_var.get()
            self._refresh_image_label()

    def _clear_dlc(self):
        self.dlc_var.set("")
        self.cfg["dlc_dir"] = ""
        self._refresh_image_label()

    def _refresh_image_label(self):
        game = self.game_var.get().strip()
        update_dir = self.update_var.get().strip()
        dlc_dir = self.dlc_var.get().strip() if hasattr(self, "dlc_var") else self.cfg.get("dlc_dir", "").strip()

        base_ver = game_app_ver(game) if game and Path(game).is_dir() else None
        base_title = game_title_id(game) if game and Path(game).is_dir() else None
        update_ver = game_app_ver(update_dir) if update_dir and Path(update_dir).is_dir() else None
        update_title = game_title_id(update_dir) if update_dir and Path(update_dir).is_dir() else None

        title_id = update_title or base_title or "CUSA01159"
        if base_ver and update_ver:
            ver_text = f"{title_id}  ·  v{base_ver} -> v{update_ver}"
        elif base_ver:
            ver_text = f"{title_id}  ·  v{base_ver}"
        else:
            ver_text = title_id

        dlc_count = 0
        dlc_err = None
        if dlc_dir and Path(dlc_dir).is_dir():
            try:
                discovered = dlc.discover_addons(dlc_dir, title_id=title_id)
                dlc_count = len(discovered)
            except Exception as e:
                dlc_err = str(e)

        if dlc_count > 0:
            ver_text += f"  ·  {dlc_count} DLC"

        if hasattr(self, "ver_label"):
            self.ver_label.config(text=ver_text)

        effective_ver = update_ver or base_ver
        ver_tag = f" (v{effective_ver})" if effective_ver else ""

        if not game or not (Path(game) / "eboot.bin").is_file():
            text = "No eboot.bin in this folder."
        elif update_dir and not (Path(update_dir) / "eboot.bin").is_file():
            text = "No eboot.bin in the update folder."
        elif update_title and base_title and update_title != base_title:
            text = f"Title ID mismatch: base is {base_title}, update is {update_title}."
        elif dlc_err:
            text = f"DLC error: {dlc_err}"
        elif image_ready(game):
            parts = [f"Game image ready: v{base_ver or '?'}" if update_ver else f"Game image ready{ver_tag}"]
            if update_ver:
                parts.append(f"update v{update_ver}")
            if dlc_count > 0:
                parts.append(f"{dlc_count} DLC loaded")
            text = " + ".join(parts) + "."
        else:
            text = f"The game image{ver_tag} is made on the first start (about a minute); again if game files change."
        self.image_label.config(text=text)

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
        mode = ini.get("display_mode", self.cfg["display_mode"])
        if mode in {k for _, k in DISPLAY_MODES}:
            self.mode_var.set(mode)
        if "vsync" in ini:
            self.vsync_var.set(ini["vsync"] == "1")
        if "rcas" in ini:
            self.rcas_var.set(ini["rcas"] == "1")
        res = ini.get("render_resolution", self.cfg["resolution"])
        self.res_var.set(next((n for n, v in RESOLUTIONS if v == res), RESOLUTIONS[0][0]))
        fsr = ini.get("fsr1")
        up = ("fsr1" if fsr == "1" else "off") if fsr is not None else self.cfg["upscale"]
        self.up_var.set(next((n for n, v in UPSCALERS if v == up), UPSCALERS[0][0]))
        fps = int(self.cfg["fps_limit"])
        self.fps_var.set(next((n for n, v in FPS_LIMITS if v == fps), FPS_LIMITS[0][0]))
        an = int(ini["anisotropy"]) if ini.get("anisotropy", "").isdigit() else self.cfg["anisotropy"]
        self.aniso_var.set(next((n for n, v in ANISO if v == an), "Off"))

    def _audio_toggled(self):
        if not self.audio_var.get():
            self.wav_var.set(False)  # the capture belongs to the log

    def _wav_toggled(self):
        if not self.wav_var.get():
            return
        if messagebox.askyesno("WAV capture", WAV_WARNING, icon="warning", default="no", parent=self):
            self.audio_var.set(True)
        else:
            self.wav_var.set(False)

    def _check_wav_leftovers(self):
        files, total = wav_captures()
        if not files or total < 50 * 2**20:
            return
        if messagebox.askyesno("Audio captures", f"user\\audio_wav holds {format_size(total)} of audio captures "
                                f"({len(files)} files) from an earlier session.\n\nDelete them to free the space?",
                                default="no", parent=self):
            for f in files:
                try:
                    f.unlink()
                except OSError:
                    pass

    def _pad_text(self):
        self.pad_label.config(text="Custom gamepad mapping in use." if MAPPING.exists()
                              else "No custom mapping: XInput and known pads work as they are.")

    def _collect(self):
        self.cfg.update(
            game=self.game_var.get().strip(),
            update_dir=self.update_var.get().strip(),
            dlc_dir=self.dlc_var.get().strip() if hasattr(self, "dlc_var") else self.cfg.get("dlc_dir", "").strip(),
            display_mode=self.mode_var.get(), vsync=self.vsync_var.get(),
            rcas=self.rcas_var.get(), fps_limit=dict(FPS_LIMITS)[self.fps_var.get()],
            resolution=dict(RESOLUTIONS)[self.res_var.get()], upscale=dict(UPSCALERS)[self.up_var.get()],
            anisotropy=dict(ANISO)[self.aniso_var.get()], audio_log=self.audio_var.get(),
            audio_wav=self.audio_var.get() and self.wav_var.get())
        save_config(self.cfg)
        write_ini(self._ini(), {
            "display_mode": self.cfg["display_mode"], "vsync": int(self.cfg["vsync"]),
            "fps_limit": self.cfg["fps_limit"], "rcas": int(self.cfg["rcas"]),
            "anisotropy": self.cfg["anisotropy"], "render_resolution": self.cfg["resolution"],
            "fsr1": int(self.cfg["upscale"] == "fsr1")})

    def _env(self):
        env = os.environ.copy()
        env["PATH"] = str(BIN) + os.pathsep + env.get("PATH", "")
        env["SPARTAN_USER_DIR"] = str(USER.resolve())
        env["SPARTAN_GPU_USER_DIR"] = str(USER.resolve())
        env["SPARTAN_CONFIG"] = str(self._ini())
        env["SPARTAN_WINDOW_TITLE"] = f"Sengoku Basara 4 Sumeragi - {BRAND} by {AUTHOR}"
        if WINDOW_ICON.exists():
            env["SPARTAN_WINDOW_ICON"] = str(WINDOW_ICON)
        if MAPPING.exists():
            env["SDL_GAMECONTROLLERCONFIG_FILE"] = str(MAPPING)
        if self.cfg.get("audio_log"):  # one timestamped line per audio event, for bug reports
            env["SPARTAN_AUDIO_DEBUG"] = str(AUDIO_LOG)
        if self.cfg.get("audio_log") and self.cfg.get("audio_wav"):  # needs about 70 MB per minute
            env["SPARTAN_AUDIO_WAV_DIR"] = str(AUDIO_WAV)
        if self.cfg["fps_limit"] != 60:  # uncapped: 480 Hz vblank, the present thread paces to the limit
            env["SPARTAN_VBLANK_HZ"] = "0"
            env["SPARTAN_FPS_LIMIT"] = str(self.cfg["fps_limit"])
        return env

    # ---- starting the game ----
    def on_play(self):
        if self.busy or self.proc:
            return
        self._collect()
        game = Path(self.cfg["game"]) if self.cfg["game"] else None
        update_dir = Path(self.cfg["update_dir"]) if self.cfg.get("update_dir") else None
        dlc_dir = Path(self.cfg["dlc_dir"]) if self.cfg.get("dlc_dir") else None
        exe = BIN / "sumeragi-core.exe"
        if not exe.is_file():
            exe = CORE
        if not exe.is_file():
            for cand in (ROOT / "bin" / "sumeragi-core.exe", ROOT / "bin" / "basara4-core.exe",
                         ROOT / "out" / "sumeragi-core.exe", ROOT / "out" / "basara4-core.exe",
                         ROOT / "out" / "gpu" / "basara4-core.exe"):
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
            messagebox.showerror("Cannot start", str(error))
            return
        if not exe.is_file():
            self._deiconify()
            messagebox.showerror("Cannot start", f"Runtime not found: {exe}")
            return
        self.busy = True
        self.play.config(state="disabled")
        self.pending = None
        threading.Thread(target=self._prepare_then_launch, args=(game, update_dir, exe, dlc_dir), daemon=True).start()
        self.after(200, self._wait_prepare)

    def _progress(self, text):
        self.pending_text = text

    def _prepare_then_launch(self, game, update_dir, exe, dlc_dir=None):
        self.pending_text = "Starting…"
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
            if not error and self.cfg["fps_limit"] != 60:
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
            self.status.config(text=getattr(self, "pending_text", "Starting…"))
            self.after(200, self._wait_prepare)
            return
        error, effective_game, exe, patch_args, notice, view = self.pending
        self.busy = False
        if error:
            self.play.config(state="normal")
            self._deiconify()
            self.status.config(text=error)
            messagebox.showerror("Cannot prepare the game", error)
            return
        self.update_view = view
        if self.cfg["fps_limit"] == 60:
            self.fps_var.set(FPS_LIMITS[0][0])
        USER.mkdir(parents=True, exist_ok=True)
        self._make_window_icon(effective_game)
        if self.cfg.get("audio_log") and AUDIO_LOG.exists():  # keep the previous run's log
            try:
                os.replace(AUDIO_LOG, AUDIO_LOG.with_name("audio_debug.previous.log"))
            except OSError:
                pass
        if self.cfg.get("audio_log") and self.cfg.get("audio_wav"):  # only this run's captures stay
            AUDIO_WAV.mkdir(parents=True, exist_ok=True)
            for old in AUDIO_WAV.glob("*.wav"):
                try:
                    old.unlink()
                except OSError:
                    pass
        log = open(LOG, "wb")
        self.proc = subprocess.Popen(
            [str(exe), str(OUT / "boot-linked.bin"), "--content-profile", str(OUT / "content.bin"),
             "--app0", str(effective_game), "--user", str(USER), "--no-game-hooks", "--cheats"] + patch_args,
            env=self._env(), cwd=str(USER), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        if self.cfg.get("audio_wav"):  # a one-session option: the next start has it off again
            self.cfg["audio_wav"] = False
            save_config(self.cfg)
            self.wav_var.set(False)
        self.stop.config(state="normal")
        self.status.config(text=notice + ("Running, writing user\\audio_debug.log…" if self.cfg.get("audio_log")
                                          else "Running…  (Insert opens the in-game menu)"))
        self._refresh_image_label()

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
            Image.open(icon_path).convert("RGBA").resize((128, 128)).save(
                WINDOW_ICON, format="BMP")
        except OSError:
            pass

    def show_credits(self):
        notice = ROOT / "NOTICE.md"
        try:
            text = notice.read_text(encoding="utf-8")
        except OSError:
            text = "Credits are in NOTICE.md."
        win = tk.Toplevel(self)
        win.title(f"{BRAND} - credits")
        win.configure(bg=BG)
        win.geometry("640x460")
        box = tk.Text(win, bg=PANEL, fg=FG, wrap="word", relief="flat", padx=14, pady=12, font=("Segoe UI", 10))
        box.insert("1.0", text)
        box.config(state="disabled")
        box.pack(fill="both", expand=True, padx=10, pady=10)

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
            self.status.config(text="Game closed." if code in (0, None) else
                               f"Game exited with code {code & 0xFFFFFFFF:#x}. See the log.")
            self._load_ini_into_ui()
        self.after(500, self._poll)

    # ---- controller and files ----
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
            messagebox.showerror("Mapper missing", f"Could not find sumeragi-pad-mapper.exe or basara4-pad-mapper.exe in:\n{BIN}")
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
        subprocess.Popen([str(exe), str(MAPPING)] + extra, env=env, creationflags=0x00000010)  # new console
        self.status.config(text="Follow the prompts in the mapper window, then press PLAY.")
        self.after(4000, self._pad_text)

    def reset_map(self):
        if MAPPING.exists() and messagebox.askyesno("Reset mapping", "Delete the saved controller mapping?"):
            os.replace(MAPPING, str(MAPPING) + ".bak")
            self._pad_text()

    def open_log(self):
        if LOG.exists():
            os.startfile(LOG)
        else:
            messagebox.showinfo("Log", "No log yet. Start the game first.")

    def open_audio_log(self):
        if AUDIO_LOG.exists():
            os.startfile(AUDIO_LOG)
        else:
            messagebox.showinfo("Audio log", "No audio log yet. Tick \"Audio debug log\", then start the game.")

    def open_saves(self):
        path = USER / "savedata"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_trophies(self):
        if getattr(self, "trophies_win", None) and self.trophies_win.winfo_exists():
            self.trophies_win.lift()
            self.trophies_win.focus_force()
            return
        self.trophies_win = TrophiesWindow(
            self,
            game_dir=self.game_var.get(),
            update_dir=self.update_var.get(),
            user_dir=USER,
        )

    def _close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Game running", "Stop the game and close the launcher?"):
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
