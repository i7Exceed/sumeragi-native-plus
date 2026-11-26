#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Unit tests for Mod Overlay (game_update), Config migration, and Mod Manager UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
LAUNCHER_DIR = REPO_ROOT / "launcher"

for p in (TESTS_DIR, SCRIPTS_DIR, LAUNCHER_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import game_update
import mods as mods_fs
import sumeragi_config as sc
import sumeragi_launcher as sl


def build_sfo(values: dict[str, str]) -> bytes:
    entries, keys, data = [], bytearray(), bytearray()
    for key in sorted(values):
        value = values[key]
        key_at = len(keys)
        keys.extend(key.encode("utf-8") + b"\0")
        encoded = value.encode("utf-8") + b"\0"
        entries.append((key_at, len(data), encoded))
        data.extend(encoded)
    key_offset = 20 + len(entries) * 16
    data_offset = key_offset + len(keys)
    header = struct.pack("<4sIIII", b"\0PSF", 0x101, key_offset, data_offset, len(entries))
    index = b"".join(
        struct.pack("<HHIII", key_at, 0x0204, len(encoded), len(encoded), value_at)
        for key_at, value_at, encoded in entries
    )
    return header + index + keys + data


def make_game_dump(folder: Path, *, title_id: str = "CUSA01159", app_ver: str = "01.00", eboot: bytes = b"base-eboot") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "eboot.bin").write_bytes(eboot)
    (folder / "sce_sys").mkdir(parents=True, exist_ok=True)
    (folder / "sce_sys" / "param.sfo").write_bytes(build_sfo({"TITLE_ID": title_id, "APP_VER": app_ver}))
    return folder


class ModOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sumeragi_mod_test_"))
        self.base = make_game_dump(self.tmp / "game", app_ver="01.00", eboot=b"base-eboot")
        (self.base / "nativePS4" / "arc").mkdir(parents=True)
        (self.base / "nativePS4" / "arc" / "Config.arc").write_bytes(b"base-config")
        (self.base / "nativePS4" / "arc" / "BaseOnly.arc").write_bytes(b"base-only")
        (self.base / "movie").mkdir()
        (self.base / "movie" / "intro.pam").write_bytes(b"base-movie")
        self.out = self.tmp / "out"

    def tearDown(self):
        # Restore writable permissions on any synthetic readonly test files before cleanup
        for p in self.tmp.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    p.chmod(0o666)
            except OSError:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_view_base_plus_mod_without_update_dir(self):
        mod_id = self.tmp / "mods" / "indonesia"
        (mod_id / "nativePS4" / "arc").mkdir(parents=True)
        (mod_id / "nativePS4" / "arc" / "Config.arc").write_bytes(b"id-translation-config")
        (mod_id / "mod.json").write_text(json.dumps({"name": "Bahasa Indonesia", "order": 1}), encoding="utf-8")

        view = game_update.create_view(self.base, None, self.out, mods=[mod_id])
        try:
            self.assertTrue(view.is_dir())
            self.assertEqual((view / "eboot.bin").read_bytes(), b"base-eboot")
            self.assertEqual((view / "nativePS4" / "arc" / "Config.arc").read_bytes(), b"id-translation-config")
            self.assertEqual((view / "nativePS4" / "arc" / "BaseOnly.arc").read_bytes(), b"base-only")
            self.assertEqual((view / "movie" / "intro.pam").read_bytes(), b"base-movie")
            # mod.json is launcher metadata and should not be overlaid into view root
            self.assertFalse((view / "mod.json").exists())
            # Untouched base folders remain linked as a single directory link
            self.assertTrue(mods_fs.is_link(view / "movie"))
        finally:
            game_update.remove_view(view)

        self.assertFalse(view.exists())
        self.assertEqual((self.base / "nativePS4" / "arc" / "Config.arc").read_bytes(), b"base-config")
        self.assertEqual((mod_id / "nativePS4" / "arc" / "Config.arc").read_bytes(), b"id-translation-config")

    def test_create_view_base_update_and_multiple_mods_case_insensitive_priority(self):
        update = make_game_dump(self.tmp / "update", app_ver="01.02", eboot=b"update-eboot")
        (update / "nativePS4" / "arc").mkdir(parents=True)
        (update / "nativePS4" / "arc" / "UpdateOnly.arc").write_bytes(b"update-only")
        (update / "nativePS4" / "arc" / "Shared.arc").write_bytes(b"update-shared")

        mod1 = self.tmp / "mods" / "mod1"
        (mod1 / "nativePS4" / "arc").mkdir(parents=True)
        (mod1 / "nativePS4" / "arc" / "config.arc").write_bytes(b"mod1-config")
        (mod1 / "nativePS4" / "arc" / "shared.arc").write_bytes(b"mod1-shared")

        mod2 = self.tmp / "mods" / "mod2"
        (mod2 / "nativeps4" / "ARC").mkdir(parents=True)
        (mod2 / "nativeps4" / "ARC" / "SHARED.ARC").write_bytes(b"mod2-shared")
        (mod2 / "nativeps4" / "ARC" / "Mod2Only.arc").write_bytes(b"mod2-only")

        view = game_update.create_view(self.base, update, self.out, mods=[mod1, mod2])
        try:
            self.assertEqual((view / "eboot.bin").read_bytes(), b"update-eboot")
            # Case-insensitive lookup inside merged view
            arc_dir = mods_fs.child(mods_fs.child(view, "nativePS4"), "arc")
            self.assertEqual(mods_fs.child(arc_dir, "Config.arc").read_bytes(), b"mod1-config")
            self.assertEqual(mods_fs.child(arc_dir, "Shared.arc").read_bytes(), b"mod2-shared")
            self.assertEqual(mods_fs.child(arc_dir, "UpdateOnly.arc").read_bytes(), b"update-only")
            self.assertEqual(mods_fs.child(arc_dir, "BaseOnly.arc").read_bytes(), b"base-only")
            self.assertEqual(mods_fs.child(arc_dir, "Mod2Only.arc").read_bytes(), b"mod2-only")
            self.assertTrue(mods_fs.is_link(view / "movie"))
        finally:
            game_update.remove_view(view)

        self.assertFalse(view.exists())
        self.assertEqual((self.base / "nativePS4" / "arc" / "Config.arc").read_bytes(), b"base-config")
        self.assertEqual((update / "nativePS4" / "arc" / "Shared.arc").read_bytes(), b"update-shared")
        self.assertEqual((mod1 / "nativePS4" / "arc" / "shared.arc").read_bytes(), b"mod1-shared")
        self.assertEqual((mod2 / "nativeps4" / "ARC" / "SHARED.ARC").read_bytes(), b"mod2-shared")

    def test_validate_mod_accepts_pure_mod_and_rejects_empty_or_overlapping(self):
        pure_mod = self.tmp / "mods" / "pure_translation"
        (pure_mod / "nativePS4").mkdir(parents=True)
        (pure_mod / "nativePS4" / "ui.arc").write_bytes(b"ui")

        # Pure mod without eboot.bin or param.sfo must pass
        resolved = game_update.validate_mod(pure_mod, base=self.base, out=self.out)
        self.assertEqual(resolved, pure_mod.resolve())
        base_meta, update_meta = game_update.validate_game(self.base, None, mods=[pure_mod], out=self.out)
        self.assertEqual(base_meta["TITLE_ID"], "CUSA01159")
        self.assertIsNone(update_meta)

        # Missing folder
        with self.assertRaises(ValueError):
            game_update.validate_mod(self.tmp / "mods" / "does_not_exist", base=self.base, out=self.out)

        # Empty folder / only mod.json / only empty subdir
        empty_mod = self.tmp / "mods" / "empty"
        empty_mod.mkdir(parents=True)
        with self.assertRaises(ValueError):
            game_update.validate_mod(empty_mod, base=self.base, out=self.out)
        (empty_mod / "mod.json").write_text('{"name": "Empty"}', encoding="utf-8")
        (empty_mod / "nativePS4").mkdir()
        with self.assertRaises(ValueError):
            game_update.validate_mod(empty_mod, base=self.base, out=self.out)

        # Overlapping with base (same, child, parent) and out
        with self.assertRaises(ValueError):
            game_update.validate_mod(self.base, base=self.base, out=self.out)
        with self.assertRaises(ValueError):
            game_update.validate_mod(self.base / "nativePS4", base=self.base, out=self.out)
        with self.assertRaises(ValueError):
            game_update.validate_mod(self.tmp, base=self.base, out=self.out)
        self.out.mkdir(parents=True, exist_ok=True)
        nested_in_out = self.out / "bad_mod"
        nested_in_out.mkdir()
        (nested_in_out / "a.arc").write_bytes(b"x")
        with self.assertRaises(ValueError):
            game_update.validate_mod(nested_in_out, base=self.base, out=self.out)

    def test_remove_view_preserves_readonly_attributes_across_restart(self):
        mod = self.tmp / "mods" / "ro_mod"
        (mod / "nativePS4" / "arc").mkdir(parents=True)
        base_cfg = self.base / "nativePS4" / "arc" / "Config.arc"
        base_only = self.base / "nativePS4" / "arc" / "BaseOnly.arc"
        mod_cfg = mod / "nativePS4" / "arc" / "Config.arc"
        mod_cfg.write_bytes(b"ro-mod-config")

        base_cfg.chmod(0o444)
        base_only.chmod(0o444)
        mod_cfg.chmod(0o444)

        view = game_update.create_view(self.base, None, self.out, mods=[mod])
        # Simulate a fresh launcher process where in-memory LINKED tracking was lost
        mods_fs.LINKED.clear()
        game_update.remove_view(view)

        self.assertFalse(view.exists())
        self.assertTrue(base_cfg.exists())
        self.assertTrue(base_only.exists())
        self.assertTrue(mod_cfg.exists())
        self.assertFalse(base_cfg.stat().st_mode & stat.S_IWRITE)
        self.assertFalse(base_only.stat().st_mode & stat.S_IWRITE)
        self.assertFalse(mod_cfg.stat().st_mode & stat.S_IWRITE)

    def test_discover_mods_and_mod_json_ordering(self):
        mods_root = self.tmp / "mods"
        m_b = mods_root / "zeta"
        (m_b / "nativePS4").mkdir(parents=True)
        (m_b / "nativePS4" / "b.arc").write_bytes(b"b")
        (m_b / "mod.json").write_text(json.dumps({"name": "Zeta Translation", "order": 1, "version": "1.2"}), encoding="utf-8")

        m_a = mods_root / "alpha"
        (m_a / "nativePS4").mkdir(parents=True)
        (m_a / "nativePS4" / "a.arc").write_bytes(b"a")

        discovered = game_update.discover_mods(mods_root, base=self.base, out=self.out)
        self.assertEqual([d["name"] for d in discovered], ["Zeta Translation", "alpha"])
        self.assertEqual(discovered[0]["version"], "1.2")
        self.assertTrue(all(d["valid"] for d in discovered))

    def test_empty_override_dir_keeps_base_directory_linked(self):
        empty_sub_mod = self.tmp / "mods" / "empty_subdir_mod"
        (empty_sub_mod / "nativePS4").mkdir(parents=True)
        (empty_sub_mod / "movie" / "intro.pam").parent.mkdir(parents=True, exist_ok=True)
        (empty_sub_mod / "movie" / "intro.pam").write_bytes(b"custom-intro")

        view = game_update.create_view(self.base, None, self.out, mods=[empty_sub_mod])
        try:
            # nativePS4 in mod was empty, so base's nativePS4 remains a single fast link
            self.assertTrue(mods_fs.is_link(view / "nativePS4"))
            self.assertEqual((view / "movie" / "intro.pam").read_bytes(), b"custom-intro")
        finally:
            game_update.remove_view(view)

    def test_cross_drive_view_root_prefers_base_volume_when_symlinks_disabled(self):
        fake_out = mock.MagicMock(spec=Path)
        fake_out.drive = "Z:"
        fake_base = mock.MagicMock(spec=Path)
        fake_base.drive = "E:"
        fake_base.parent = self.tmp
        with mock.patch.object(game_update.os, "name", "nt"), \
             mock.patch.object(game_update, "_can_create_symlink", return_value=False):
            chosen = game_update._choose_view_root(fake_base, fake_out)
        self.assertEqual(chosen, self.tmp / game_update._OVERLAY_DIR_NAME)
        self.assertTrue(chosen.is_dir())


class ModConfigAndLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sumeragi_mod_cfg_"))
        self.user_dir = self.tmp / "user"
        self.user_dir.mkdir(parents=True)
        self.cfg_file = self.user_dir / "launcher.json"
        self.out_dir = self.tmp / "out"
        self.base = make_game_dump(self.tmp / "game", app_ver="01.00", eboot=b"base-eboot")
        (self.base / "nativePS4").mkdir()
        (self.base / "nativePS4" / "Text.arc").write_bytes(b"jp-text")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_legacy_config_migration_without_mod_keys(self):
        # Legacy launcher.json from before mod manager existed
        self.cfg_file.write_text(json.dumps({
            "game": str(self.base),
            "update_dir": "",
            "fps_limit": 120,
            "language": "id",
        }), encoding="utf-8")

        with mock.patch.object(sl, "CONFIG", self.cfg_file), \
             mock.patch.object(sl, "USER", self.user_dir), \
             mock.patch.object(sl, "ROOT", self.tmp):
            cfg = sc.load_config()
            self.assertEqual(cfg["fps_limit"], 120)
            self.assertEqual(cfg["language"], "id")
            self.assertEqual(cfg["mods_dir"], str(self.tmp / "mods"))
            self.assertEqual(cfg["enabled_mods"], [])
            self.assertEqual(cfg["extra_mods"], [])
            sc.save_config(cfg)

            # Corrupt/non-list values are also sanitized gracefully
            self.cfg_file.write_text(json.dumps({"mods_dir": None, "enabled_mods": "bad"}), encoding="utf-8")
            cfg2 = sc.load_config()
            self.assertEqual(cfg2["mods_dir"], str(self.tmp / "mods"))
            self.assertEqual(cfg2["enabled_mods"], [])

    def test_prepare_then_launch_with_mods_only_and_cleanup(self):
        mod1 = self.tmp / "mods" / "indo"
        (mod1 / "nativePS4").mkdir(parents=True)
        (mod1 / "nativePS4" / "Text.arc").write_bytes(b"id-text")

        self.out_dir.mkdir(parents=True, exist_ok=True)
        for name in ("boot-linked.bin", "content.bin", "eboot.elf", "boot.bin"):
            (self.out_dir / name).write_bytes(b"prepared")

        with mock.patch.object(sl, "OUT", self.out_dir), \
             mock.patch.object(sl, "USER", self.user_dir), \
             mock.patch.object(sl, "STAMP", self.out_dir / "prepared.json"), \
             mock.patch.object(sl, "CONFIG", self.cfg_file), \
             mock.patch.object(sl, "ROOT", self.tmp):
            import sumeragi_pipeline as sp
            stamp = sp.input_files_stamp(self.base)
            stamp["game"] = str(self.base)
            (self.out_dir / "prepared.json").write_text(json.dumps(stamp), encoding="utf-8")

            app = sl.Launcher.__new__(sl.Launcher)
            app.cfg = dict(sc.DEFAULTS)
            app.cfg.update({"game": str(self.base), "update_dir": "", "dlc_dir": "", "enabled_mods": [str(mod1)]})
            app.pending = None
            app.pending_text = ""

            with mock.patch.object(sl.patches_module, "build", return_value=([], [])):
                app._prepare_then_launch(self.base, None, self.tmp / "bin" / "sumeragi-core.exe", None, [mod1])

            error, effective_game, _exe, _args, _notice, view = app.pending
            self.assertIsNone(error)
            self.assertIsNotNone(view)
            self.assertEqual(effective_game, view)
            self.assertEqual((view / "nativePS4" / "Text.arc").read_bytes(), b"id-text")

            # Simulate stop/cleanup
            app.proc = None
            app.update_view = view
            app.on_stop()
            self.assertIsNone(app.update_view)
            self.assertFalse(view.exists())
            self.assertEqual((self.base / "nativePS4" / "Text.arc").read_bytes(), b"jp-text")
            self.assertEqual((mod1 / "nativePS4" / "Text.arc").read_bytes(), b"id-text")

    def test_home_card_and_mods_manager_dialog_workflow(self):
        mod1 = self.tmp / "mods" / "indo"
        (mod1 / "nativePS4").mkdir(parents=True)
        (mod1 / "nativePS4" / "Text.arc").write_bytes(b"id-text")
        (mod1 / "mod.json").write_text(json.dumps({"name": "Indonesia Patch", "order": 1}), encoding="utf-8")

        mod2 = self.tmp / "mods" / "hd_ui"
        (mod2 / "nativePS4").mkdir(parents=True)
        (mod2 / "nativePS4" / "Text.arc").write_bytes(b"hd-text")

        with mock.patch.object(sl, "CONFIG", self.cfg_file), \
             mock.patch.object(sl, "USER", self.user_dir), \
             mock.patch.object(sl, "OUT", self.out_dir), \
             mock.patch.object(sl, "ROOT", self.tmp):
            try:
                app = sl.Launcher()
                app.withdraw()
            except Exception as e:
                self.skipTest(f"Tkinter display not available: {e}")

            try:
                self.assertTrue(hasattr(app, "card_mods"))
                self.assertIn("2", app.card_mods._val_lbl.cget("text"))

                dlg = app.open_mods_manager()
                state = dlg._mod_state
                self.assertEqual(len(state["entries"]), 2)
                self.assertEqual(state["entries"][0]["name"], "Indonesia Patch")

                # Enable both mods and reorder so Indonesia Patch is second (higher priority)
                state["entries"][0]["enabled"] = True
                state["entries"][1]["enabled"] = True
                self.assertTrue(sl.move_mod_entry(state["entries"], 0, 1))
                state["save"]()

                reloaded = sc.load_config()
                self.assertEqual(reloaded["enabled_mods"], [str(mod2.resolve()), str(mod1.resolve())])
                self.assertIn("2", app.card_mods._val_lbl.cget("text"))

                # Re-open and test adding an external mod folder & rejecting an invalid one
                ext_mod = self.tmp / "external_mods" / "custom_bgm"
                (ext_mod / "nativePS4" / "sound").mkdir(parents=True)
                (ext_mod / "nativePS4" / "sound" / "bgm.at9").write_bytes(b"bgm")
                bad_mod = self.tmp / "external_mods" / "empty_bad"
                bad_mod.mkdir(parents=True)

                dlg2 = app.open_mods_manager()
                state2 = dlg2._mod_state
                self.assertTrue(state2["add_mod_path"](ext_mod))
                with mock.patch.object(sl.messagebox, "showerror") as show_err:
                    self.assertFalse(state2["add_mod_path"](bad_mod))
                    show_err.assert_called_once()
                state2["save"]()

                reloaded2 = sc.load_config()
                self.assertEqual(len(reloaded2["enabled_mods"]), 3)
                self.assertIn(str(ext_mod.resolve()), reloaded2["extra_mods"])
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
