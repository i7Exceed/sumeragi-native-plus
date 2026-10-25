#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Comprehensive unit tests for the Sumeragi Native+ Launcher UI Redesign & i18n."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

# Setup sys.path
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
LAUNCHER_DIR = REPO_ROOT / "launcher"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(LAUNCHER_DIR) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_DIR))

import sumeragi_launcher as launcher
import sumeragi_i18n as i18n
import sumeragi_theme as theme


class TestLauncherArchitectureAndPages(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sumeragi_redesign_test_"))
        self.cfg_file = self.tmp / "launcher.json"
        self.user_dir = self.tmp / "user"
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pages_definition_and_completeness(self):
        """Verifies that all 8 required pages are enumerated in order."""
        expected_pages = ("home", "game_files", "updates", "dlc", "trophies", "controls", "settings", "diagnostics")
        self.assertEqual(launcher.PAGES, expected_pages)

    def test_launcher_shell_instantiation_and_page_switching(self):
        """Tests that the launcher can switch between all 8 pages without raising errors."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            try:
                app = launcher.Launcher()
                app.withdraw()
            except Exception as e:
                self.skipTest(f"Tkinter display not available: {e}")

            try:
                # Verify all 8 pages exist in page_frames
                for p in launcher.PAGES:
                    self.assertIn(p, app.page_frames)
                    self.assertIn(p, app.nav_buttons)

                # Switch through all pages
                for p in launcher.PAGES:
                    app.show_page(p)
                    self.assertEqual(app.current_page, p)
            finally:
                app.destroy()

    def test_default_language_is_english(self):
        """Fresh configuration must always default to English."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            cfg = launcher.load_config()
            self.assertEqual(cfg.get("language"), "en")
            self.assertEqual(i18n.get_language(), "en")

    def test_language_persistence_in_launcher_config(self):
        """Selecting Indonesian persists across reloads without altering other settings."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            cfg = launcher.load_config()
            cfg["language"] = "id"
            cfg["fps_limit"] = 120
            launcher.save_config(cfg)

            # Reload
            reloaded = launcher.load_config()
            self.assertEqual(reloaded["language"], "id")
            self.assertEqual(reloaded["fps_limit"], 120)
            self.assertEqual(i18n.get_language(), "id")

            # Restore
            cfg["language"] = "en"
            launcher.save_config(cfg)

    def test_dynamic_language_switch_updates_navigation_and_hero(self):
        """Switching language dynamically updates translated text across the UI immediately."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            try:
                app = launcher.Launcher()
                app.withdraw()
            except Exception as e:
                self.skipTest(f"Tkinter display not available: {e}")

            try:
                # Initial English
                i18n.set_language("en")
                self.assertIn("Home", app.nav_buttons["home"]._lbl.cget("text"))
                self.assertEqual(app.home_hero_title.cget("text"), "Ready for Battle?")

                # Switch to Indonesian
                i18n.set_language("id")
                self.assertIn("Beranda", app.nav_buttons["home"]._lbl.cget("text"))
                self.assertEqual(app.home_hero_title.cget("text"), "Siap Bertempur?")

                # Restore English
                i18n.set_language("en")
                self.assertIn("Home", app.nav_buttons["home"]._lbl.cget("text"))
                self.assertEqual(app.home_hero_title.cget("text"), "Ready for Battle?")
            finally:
                app.destroy()

    def test_env_construction_preserves_spartan_contracts(self):
        """Verifies environment variables construction passes correct parameters."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            app = launcher.Launcher.__new__(launcher.Launcher)
            app.cfg = {
                "game": str(self.tmp / "game"),
                "update_dir": "",
                "dlc_dir": "",
                "fps_limit": 144,
                "pad_controls": {"cross": "b", "circle": "a"},
                "audio_log": True,
                "audio_wav": False,
            }

            env = app._env()
            self.assertEqual(env["SPARTAN_USER_DIR"], str(self.user_dir.resolve()))
            self.assertEqual(env["SPARTAN_GPU_USER_DIR"], str(self.user_dir.resolve()))
            self.assertEqual(env["SPARTAN_PAD_MAP"], "cross=b,circle=a")
            self.assertEqual(env["SPARTAN_FPS_LIMIT"], "144")
            self.assertEqual(env["SPARTAN_VBLANK_HZ"], "0")
            self.assertEqual(env["SPARTAN_AUDIO_DEBUG"], str(self.user_dir / "audio_debug.log"))

    def test_trophies_and_controls_embedded_no_toplevel_popups(self):
        """Verifies trophies and controls are fully embedded inside main launcher with zero popup windows."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            try:
                app = launcher.Launcher()
                app.withdraw()
            except Exception as e:
                self.skipTest(f"Tkinter display not available: {e}")

            try:
                initial_toplevels = [w for w in app.winfo_children() if isinstance(w, launcher.tk.Toplevel)]
                self.assertEqual(len(initial_toplevels), 0)

                # 1. Open Trophies
                app.open_trophies()
                self.assertEqual(app.current_page, "trophies")
                # Ensure no Toplevel was spawned
                toplevels_after_tr = [w for w in app.winfo_children() if isinstance(w, launcher.tk.Toplevel)]
                self.assertEqual(len(toplevels_after_tr), 0)
                # Ensure trophies are populated directly in the frame
                self.assertEqual(len(app.current_trophies), 43)
                self.assertEqual(app.current_trophies[0]["id"], 0)
                self.assertEqual(app.current_trophies[0]["tier"], "platinum")

                # 2. Open Controls
                app.open_controller_controls()
                self.assertEqual(app.current_page, "controls")
                # Ensure no Toplevel was spawned
                toplevels_after_ctrl = [w for w in app.winfo_children() if isinstance(w, launcher.tk.Toplevel)]
                self.assertEqual(len(toplevels_after_ctrl), 0)
                # Ensure all 15 action rows are embedded in the controls canvas
                self.assertEqual(len(app.ctrl_row_combos), 15)
                self.assertIn("cross", app.ctrl_row_combos)
                self.assertIn("circle", app.ctrl_row_combos)

                # 3. Test changing button style (PlayStation -> Xbox)
                app.ctrl_style_var.set("Xbox")
                app._on_ctrl_style_changed()
                cross_var = app.ctrl_row_combo_vars["cross"].get()
                self.assertIn("A", cross_var)

                # 4. Test remapping: bind cross to 'b' (auto-swaps with circle)
                app._on_ctrl_combo_selected("cross", "B (East / Kanan)")
                self.assertEqual(app.ctrl_controls["cross"], "b")
                self.assertEqual(app.ctrl_controls["circle"], "a")

                # 5. Save controls
                app._on_ctrl_save()
                reloaded = launcher.load_config()
                self.assertEqual(reloaded["pad_controls"]["cross"], "b")
                self.assertEqual(reloaded["pad_controls"]["circle"], "a")
                self.assertEqual(reloaded["pad_style"], "xbox")
            finally:
                app.destroy()

    def test_trophy_language_synchronization_with_settings(self):
        """Verifies changing language in Settings automatically updates trophy texts, filter labels, and trophy_texts.txt."""
        with mock.patch.object(launcher, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher, "USER", self.user_dir):
            try:
                app = launcher.Launcher()
                app.withdraw()
            except Exception as e:
                self.skipTest(f"Tkinter display not available: {e}")

            try:
                # 1. Initial English state
                app.open_trophies()
                self.assertIn("Sengoku Champion", app.current_trophies[0]["name"])
                self.assertEqual(app.tr_filter_var.get(), "All Trophies")
                file_text_en = (self.user_dir / "trophy_texts.txt").read_text(encoding="utf-8")
                self.assertIn("Sengoku Champion", file_text_en)

                # 2. Switch to Indonesian
                app.lang_var.set("Bahasa Indonesia")
                app._on_lang_combo_selected()
                app.open_trophies()
                self.assertIn("Penguasa Sengoku", app.current_trophies[0]["name"])
                self.assertEqual(app.tr_filter_var.get(), "Semua Piala")
                file_text_id = (self.user_dir / "trophy_texts.txt").read_text(encoding="utf-8")
                self.assertIn("Penguasa Sengoku", file_text_id)

                # 3. Switch back to English
                app.lang_var.set("English")
                app._on_lang_combo_selected()
                app.open_trophies()
                self.assertIn("Sengoku Champion", app.current_trophies[0]["name"])
                self.assertEqual(app.tr_filter_var.get(), "All Trophies")
                file_text_en2 = (self.user_dir / "trophy_texts.txt").read_text(encoding="utf-8")
                self.assertIn("Sengoku Champion", file_text_en2)
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
