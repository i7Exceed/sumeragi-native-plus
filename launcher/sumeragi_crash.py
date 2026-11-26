#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Razz, i7Exceed.
"""Crash diagnostics, pattern recognition, and reporter dialog for Sumeragi Native+."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from sumeragi_config import BRAND, VERSION
from sumeragi_gpu import VULKAN, describe_vulkan
from sumeragi_i18n import t
import sumeragi_theme as theme

CRASH_SIGNATURES = [
    (r"(cannot create \d+ MiB of guest memory.*)", "memory_commit"),
    (r"(error 1455.*)", "memory_commit"),
    (r"(ERROR_COMMITMENT_LIMIT.*)", "memory_commit"),
    (r"(VirtualAlloc2.*failed.*)", "memory_commit"),
    (r"(VK_ERROR_\w+)", "vulkan"),
    (r"(vk::Result=.*)", "vulkan"),
    (r"(GPU \[Render\.Vulkan\] <Error> .*)", "vulkan"),
    (r"(GPU \[Render\.Vulkan\] <Warning> .*)", "vulkan"),
    (r"(GPU \[Lib\.\w+\] <Error> .*)", "vulkan"),
    (r"(ASSERT_MSG.*)", "assertion"),
    (r"(guest raised debug exception .*)", "guest_exception"),
    (r"(Fault: .*)", "fault"),
    (r"(STOP: .*)", "stop"),
    (r"(STATUS_ACCESS_VIOLATION.*)", "access_violation"),
    (r"(STATUS_ILLEGAL_INSTRUCTION.*)", "illegal_insn"),
    (r"(Runtime: open\(.*?\) -> not found)", "missing_file"),
]

CRASH_CATEGORIES = ("memory_commit", "vulkan", "missing_file", "guest_exception", "general")


class _CrashGuidesDict(dict):
    """Dictionary resolving guide entries dynamically through i18n while supporting legacy keys."""

    def __getitem__(self, key: str) -> Dict[str, str]:
        cat = key if key in CRASH_CATEGORIES else "general"
        title = t(f"crash.{cat}.title")
        desc = t(f"crash.{cat}.desc")
        action = t(f"crash.{cat}.action")
        return {
            "title": title,
            "desc": desc,
            "action": action,
            "title_id": title,
            "title_en": title,
            "desc_id": desc,
            "desc_en": desc,
            "action_id": action,
            "action_en": action,
        }

    def get(self, key: str, default: Any = None) -> Dict[str, str]:
        if key in CRASH_CATEGORIES:
            return self[key]
        return default if default is not None else self["general"]

    def __contains__(self, key: object) -> bool:
        return key in CRASH_CATEGORIES


CRASH_GUIDES: Dict[str, Dict[str, str]] = _CrashGuidesDict({cat: {} for cat in CRASH_CATEGORIES})


def explain_hardware_crash(
    exit_code: int, detected_errors: List[str], tail_context: str
) -> List[str]:
    """Provide detailed human-friendly crash troubleshooting hints."""
    hints: List[str] = []
    code_u32 = exit_code & 0xFFFFFFFF
    if code_u32 == 0xC0000139:
        hints.append(
            "🧩 Vulkan Tidak Ditemukan atau Terlalu Lama (Exit Code 0xC0000139):\n"
            "Windows gagal memuat game karena komponen Vulkan di PC tidak ada atau terlalu lama.\n"
            "👉 Solusi: Perbarui driver kartu grafis dari situs resmi (NVIDIA / AMD / Intel), lalu jalankan lagi."
        )
    elif code_u32 == 0xC0000135:
        hints.append(
            "📁 File Game Tidak Lengkap (Exit Code 0xC0000135):\n"
            "Windows tidak menemukan salah satu file yang dibutuhkan game.\n"
            "👉 Solusi: Pastikan seluruh file ter-ekstrak sempurna dan tidak dikarantina oleh antivirus."
        )
    elif any("1455" in e or "COMMITMENT_LIMIT" in e for e in detected_errors):
        hints.append(
            "💾 Kehabisan Virtual Memory / Paging File (Error 1455):\n"
            "Windows kehabisan kuota alokasi memory commit.\n"
            "👉 Solusi: Aktifkan 'Automatically manage paging file size' di Pengaturan Windows Advanced System."
        )
    return hints


def analyze_crash_log(log_path: Path, max_tail: int = 15) -> Dict[str, Any]:
    if not log_path.is_file():
        return {
            "category": "general",
            "matched_errors": [t("crash.status_no_log")],
            "tail": "",
            "total_lines": 0,
        }
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return {
            "category": "general",
            "matched_errors": [t("crash.status_read_fail", error=str(e))],
            "tail": "",
            "total_lines": 0,
        }
    if not lines:
        return {
            "category": "general",
            "matched_errors": [t("crash.status_empty_log")],
            "tail": "",
            "total_lines": 0,
        }

    tail = lines[-max_tail:]
    detected = []
    category = "general"

    for line in reversed(lines):
        for pattern, cat in CRASH_SIGNATURES:
            m = re.search(pattern, line)
            if m:
                msg = m.group(1).strip()
                if msg not in detected:
                    detected.append(msg)
                if category == "general":
                    category = cat
        if len(detected) >= 5:
            break

    return {
        "category": category,
        "matched_errors": detected if detected else [t("crash.status_no_signature")],
        "tail": "\n".join(tail),
        "total_lines": len(lines),
    }


class SumeragiCrashDialog(tk.Toplevel):
    """Modern modal dialog presenting crash diagnostics and troubleshooting advice."""

    def __init__(self, parent: tk.Tk, exit_code: int, log_path: Path):
        super().__init__(parent)
        self.parent_app = parent
        self.exit_code = exit_code
        self.log_path = log_path
        self.analysis = analyze_crash_log(log_path)
        guide = CRASH_GUIDES.get(self.analysis["category"], CRASH_GUIDES["general"])

        self.title(f"{BRAND} - {t('crash.title')}")
        self.configure(bg=theme.BG_MAIN)
        self.geometry("740x580")
        self.minsize(640, 480)
        self.transient(parent)
        self.grab_set()

        # Header Frame
        hdr = tk.Frame(self, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=12)
        hdr.pack(fill="x", padx=16, pady=(16, 10))

        err_title = guide["title"]
        err_desc = guide["desc"]
        self.action_text = guide["action"]

        top_row = tk.Frame(hdr, bg=theme.BG_CARD)
        top_row.pack(fill="x")
        tk.Label(
            top_row,
            text=f"⚠️ {t('crash.badge_fatal')}",
            bg=theme.BG_CARD,
            fg=theme.ACCENT_CRIMSON,
            font=theme.FONT_HEADING,
        ).pack(side="left")
        hex_code = f"{exit_code & 0xFFFFFFFF:#x}"
        tk.Label(
            top_row,
            text=f"{t('crash.exit_code')}: {hex_code} ({exit_code})",
            bg=theme.BG_CARD,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_CAPTION,
        ).pack(side="right")

        tk.Label(
            hdr,
            text=err_title,
            bg=theme.BG_CARD,
            fg=theme.ACCENT_GOLD,
            font=theme.FONT_SUBHEADING,
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(6, 2))
        tk.Label(
            hdr,
            text=err_desc,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_BODY,
            wraplength=680,
            justify="left",
        ).pack(anchor="w")

        # Recommendation Frame
        rec = tk.Frame(self, bg=theme.BG_CARD, bd=1, relief="solid", padx=16, pady=12)
        rec.pack(fill="x", padx=16, pady=(0, 10))

        tk.Label(
            rec,
            text=f"💡 {t('crash.recommendation')}",
            bg=theme.BG_CARD,
            fg=theme.ACCENT_GOLD,
            font=theme.FONT_SUBHEADING,
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            rec,
            text=self.action_text,
            bg=theme.BG_CARD,
            fg=theme.TEXT_PRIMARY,
            font=theme.FONT_BODY,
            wraplength=680,
            justify="left",
        ).pack(anchor="w")

        # Log Tail Frame
        log_frame = tk.Frame(self, bg=theme.BG_CARD, bd=1, relief="solid", padx=12, pady=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        tk.Label(
            log_frame,
            text=t("crash.log_tail"),
            bg=theme.BG_CARD,
            fg=theme.TEXT_SECONDARY,
            font=theme.FONT_CAPTION,
        ).pack(anchor="w", pady=(0, 4))

        self.txt = tk.Text(
            log_frame,
            bg=theme.BG_INPUT,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.ACCENT_GOLD,
            wrap="none",
            relief="flat",
            font=("Consolas", 9),
            padx=8,
            pady=6,
        )
        self.txt.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.txt.yview)
        sb.pack(side="right", fill="y")
        self.txt.configure(yscrollcommand=sb.set)

        tail_content = self.analysis["tail"] or t("crash.no_log_recorded")
        self.txt.insert("1.0", tail_content)
        self.txt.config(state="disabled")

        # Bottom Button Bar
        btn_bar = tk.Frame(self, bg=theme.BG_MAIN)
        btn_bar.pack(fill="x", padx=16, pady=(0, 16))

        self.copy_btn = ttk.Button(
            btn_bar,
            text=t("crash.btn_copy"),
            style="Primary.TButton",
            command=self._copy_report,
        )
        self.copy_btn.pack(side="left", padx=(0, 8))

        self.open_log_btn = ttk.Button(
            btn_bar,
            text=t("crash.btn_open_log"),
            style="Small.TButton",
            command=self._open_log_file,
        )
        self.open_log_btn.pack(side="left", padx=(0, 8))

        self.close_btn = ttk.Button(
            btn_bar,
            text=t("crash.btn_close"),
            style="Small.TButton",
            command=self.destroy,
        )
        self.close_btn.pack(side="right")

    def _copy_report(self):
        hex_code = f"{self.exit_code & 0xFFFFFFFF:#x}"
        heading = t("crash.report_heading", brand=BRAND)
        rec_title = t("crash.report_recommendations")
        tail_title = t("crash.report_log_tail")
        vulkan_line = describe_vulkan(VULKAN)
        report = (
            f"{heading}\n"
            f"Version       : {VERSION}\n"
            f"Exit Code     : {hex_code} ({self.exit_code})\n"
            f"Category      : {self.analysis['category']}\n"
            f"Vulkan        : {vulkan_line}\n"
            f"Signatures:\n"
            + "\n".join(f" - {err}" for err in self.analysis["matched_errors"])
            + f"\n\n{rec_title}\n{self.action_text}\n"
            f"\n{tail_title}\n"
            f"{self.analysis['tail']}\n"
        )
        self.clipboard_clear()
        self.clipboard_append(report)
        messagebox.showinfo(t("common.success"), t("crash.copy_success"), parent=self)

    def _open_log_file(self):
        if self.log_path.is_file():
            try:
                os.startfile(str(self.log_path.resolve()))
            except Exception as e:
                messagebox.showerror(t("dialog.error_title"), str(e), parent=self)
        else:
            messagebox.showwarning(t("dialog.error_title"), t("diagnostics.no_log_yet"), parent=self)
