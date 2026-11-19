#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Razz, i7Exceed.
"""GitHub Release Auto-updater and version checker for Sumeragi Native+."""

from __future__ import annotations

import json
from pathlib import Path
import re
import ssl
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional, Tuple
import urllib.request

from sumeragi_config import BRAND, VERSION
from sumeragi_i18n import t
import sumeragi_theme as theme

GITHUB_REPO = "i7Exceed/sumeragi-native-plus"
FALLBACK_REPO = "razzconnect/basara4-native-pc"


def parse_version(tag: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", str(tag))
    return tuple(int(n) for n in nums) if nums else (0,)


def check_latest_release(repo: str = GITHUB_REPO) -> Optional[Dict[str, Any]]:
    """Checks the latest GitHub release. Returns dict of asset info or None."""
    repos_to_try = [repo]
    if repo != FALLBACK_REPO:
        repos_to_try.append(FALLBACK_REPO)

    for r in repos_to_try:
        try:
            url = f"https://api.github.com/repos/{r}/releases/latest"
            req = urllib.request.Request(
                url, headers={"User-Agent": f"Sumeragi-Launcher/{VERSION}"}
            )
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            tag = data.get("tag_name", "")
            if parse_version(tag) > parse_version(VERSION):
                for a in data.get("assets", []):
                    name = a.get("name", "")
                    if name.endswith(".zip") and (
                        "sumeragi" in name.lower()
                        or "basara4" in name.lower()
                        or "windows" in name.lower()
                    ):
                        return {
                            "tag": tag,
                            "url": a.get("browser_download_url"),
                            "name": name,
                            "size": a.get("size", 0),
                            "body": data.get("body", ""),
                            "repo": r,
                        }
                for a in data.get("assets", []):
                    if a.get("name", "").endswith(".zip"):
                        return {
                            "tag": tag,
                            "url": a.get("browser_download_url"),
                            "name": a.get("name", ""),
                            "size": a.get("size", 0),
                            "body": data.get("body", ""),
                            "repo": r,
                        }
        except Exception:
            continue
    return None
