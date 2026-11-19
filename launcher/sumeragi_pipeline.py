#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Image preparation pipeline and file verification for Sumeragi Native+."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
from typing import Callable, List, Optional, Tuple

from patches import find_sfo
from sumeragi_config import (
    AUDIO_WAV,
    FROZEN,
    NO_WINDOW,
    OUT,
    PIPELINE,
    PREPARE_LOG,
    SCRIPTS,
    STAMP,
    USER,
)


def _get_active_stamp() -> Path:
    launcher_mod = sys.modules.get("sumeragi_launcher")
    if launcher_mod and hasattr(launcher_mod, "STAMP"):
        return Path(getattr(launcher_mod, "STAMP"))
    return STAMP


def _get_active_out() -> Path:
    launcher_mod = sys.modules.get("sumeragi_launcher")
    if launcher_mod and hasattr(launcher_mod, "OUT"):
        return Path(getattr(launcher_mod, "OUT"))
    return OUT


def _get_active_user() -> Path:
    launcher_mod = sys.modules.get("sumeragi_launcher")
    if launcher_mod and hasattr(launcher_mod, "USER"):
        return Path(getattr(launcher_mod, "USER"))
    return USER


def wav_captures() -> Tuple[List[Path], int]:
    """The audio captures an earlier session left in user\\audio_wav: (files, total bytes)."""
    active_user = _get_active_user()
    wav_dir = active_user / "audio_wav"
    files = sorted(wav_dir.glob("*.wav")) if wav_dir.is_dir() else []
    total = 0
    for f in files:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return files, total


def format_size(n: int) -> str:
    return f"{n / 2**30:.1f} GB" if n >= 2**30 else f"{n / 2**20:.0f} MB"


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def input_files_stamp(game: str | Path) -> dict:
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


def image_ready(game: str | Path) -> bool:
    """Whether out\\ holds an image made from this effective game's current inputs."""
    try:
        active_stamp = _get_active_stamp()
        active_out = _get_active_out()
        if not active_stamp.is_file():
            return False
        stamp = json.loads(active_stamp.read_text(encoding="utf-8-sig"))
        current = input_files_stamp(game)
        if not current.get("eboot_sha256") or stamp.get("eboot_sha256") != current.get("eboot_sha256"):
            return False
        if current.get("sfo_sha256") and stamp.get("sfo_sha256") != current.get("sfo_sha256"):
            return False
        if current.get("modules") and stamp.get("modules") != current.get("modules"):
            return False
        required_outputs = ("boot-linked.bin", "content.bin", "eboot.elf", "boot.bin")
        return all((active_out / name).is_file() for name in required_outputs)
    except (OSError, ValueError):
        return False


def prepare_image(game: str | Path, progress: Callable[[str], None]) -> Optional[str]:
    """Runs the preparation scripts on the game's eboot.bin. Returns an error text or None."""
    active_out = _get_active_out()
    active_user = _get_active_user()
    active_stamp = _get_active_stamp()
    active_out.mkdir(parents=True, exist_ok=True)
    active_user.mkdir(parents=True, exist_ok=True)
    log_file = active_user / "prepare.log"
    with open(log_file, "w", encoding="utf-8", errors="replace") as log:
        for index, (name, extra) in enumerate(PIPELINE, 1):
            progress(f"Preparing the game image ({index}/{len(PIPELINE)}): {name[:-3]}…")
            script = [sys.executable, "--run-script", name] if FROZEN else [sys.executable, str(SCRIPTS / name)]
            result = subprocess.run(
                script + [str(game), "--out", str(active_out)] + extra,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=NO_WINDOW,
            )
            if result.returncode:
                return f"{name} failed (exit {result.returncode}). See user\\prepare.log"
    stamp_data = input_files_stamp(game)
    stamp_data["game"] = str(game)
    active_stamp.write_text(json.dumps(stamp_data, indent=2), encoding="utf-8")
    return None


def run_script_mode() -> None:
    """`launcher.exe --run-script NAME args...`: runs one of the preparation scripts in this process."""
    script = SCRIPTS / sys.argv[2]
    sys.path.insert(0, str(SCRIPTS))
    sys.argv = [str(script)] + sys.argv[3:]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exit_:
        code = exit_.code
        sys.exit(code if isinstance(code, int) else (0 if code is None else 1))
