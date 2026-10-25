#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Comprehensive unit tests for Sumeragi Native+ Controller Controls & Button Remapping."""

import json
import os
from pathlib import Path
import subprocess
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

import sumeragi_controller_controls as controls
import sumeragi_launcher as launcher_mod


class TestControllerControlsLogic(unittest.TestCase):
    """Tests for pure mapping logic, validation, diffing, and spec building."""

    def test_default_controls_complete(self):
        defaults = controls.get_default_controls()
        expected_actions = {
            "cross", "circle", "square", "triangle",
            "l1", "r1", "l3", "r3", "options",
            "touchpad_right", "touchpad_left",
            "up", "down", "left", "right",
        }
        self.assertEqual(set(defaults.keys()), expected_actions)
        self.assertEqual(defaults["cross"], "a")
        self.assertEqual(defaults["circle"], "b")
        self.assertEqual(defaults["square"], "x")
        self.assertEqual(defaults["triangle"], "y")
        self.assertEqual(defaults["l1"], "leftshoulder")
        self.assertEqual(defaults["r1"], "rightshoulder")

    def test_validation_rejects_unknown_targets_and_tokens(self):
        raw = {
            "cross": "b",
            "invalid_action": "a",
            "circle": "not_a_button",
            "triangle": "Y",  # case-insensitive
            "l1": "None",
            "r1": "NONE",
            123: "a",
            "square": None,
        }
        validated = controls.validate_controls(raw)
        self.assertEqual(validated.get("cross"), "b")
        self.assertEqual(validated.get("triangle"), "y")
        self.assertEqual(validated.get("l1"), "None")
        self.assertEqual(validated.get("r1"), "None")
        self.assertNotIn("invalid_action", validated)
        self.assertNotIn("circle", validated)
        self.assertNotIn("square", validated)
        self.assertNotIn(123, validated)

    def test_build_pad_map_spec_default_is_empty(self):
        defaults = controls.get_default_controls()
        self.assertEqual(controls.build_pad_map_spec(defaults), "")
        self.assertEqual(controls.build_pad_map_spec({}), "")
        self.assertEqual(controls.build_pad_map_spec(None), "")

    def test_build_pad_map_spec_with_custom_swaps(self):
        custom = {"cross": "b", "circle": "a"}
        spec = controls.build_pad_map_spec(custom)
        # Ordered by action order: cross then circle
        self.assertEqual(spec, "cross=b,circle=a")

    def test_duplicate_rebinding_swaps_buttons(self):
        active = controls.get_default_controls()
        # Cross was 'a', Circle was 'b'
        swapped = controls.bind_button(active, "cross", "b", swap_duplicates=True)
        self.assertEqual(swapped, "circle")
        self.assertEqual(active["cross"], "b")
        self.assertEqual(active["circle"], "a")

    def test_binding_unassigned_does_not_swap(self):
        active = controls.get_default_controls()
        swapped = controls.bind_button(active, "cross", "paddle1", swap_duplicates=True)
        self.assertIsNone(swapped)
        self.assertEqual(active["cross"], "paddle1")
        self.assertEqual(active["circle"], "b")

    def test_unassigning_with_none(self):
        active = controls.get_default_controls()
        swapped = controls.bind_button(active, "touchpad_left", "None")
        self.assertIsNone(swapped)
        self.assertEqual(active["touchpad_left"], "None")

    def test_reset_single_and_all_controls(self):
        active = {"cross": "b", "circle": "a", "l1": "r1"}
        controls.reset_button(active, "cross")
        self.assertEqual(active["cross"], "a")
        self.assertEqual(active["circle"], "a")

        controls.reset_all_controls(active)
        self.assertEqual(active, controls.get_default_controls())

    def test_formatting_labels_across_styles(self):
        self.assertIn("✕", controls.format_button_label("a", "playstation"))
        self.assertIn("A", controls.format_button_label("a", "xbox"))
        self.assertIn("B", controls.format_button_label("a", "nintendo"))
        self.assertEqual(controls.format_button_label("None", "playstation"), "— None (Unassigned) —")


class TestLauncherControlsIntegration(unittest.TestCase):
    """Tests launcher configuration, environment propagation, and isolation from hardware mapper."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sumeragi_ctrl_test_"))
        self.user_dir = self.tmp / "user"
        self.user_dir.mkdir(parents=True)
        self.cfg_file = self.user_dir / "launcher.json"
        self.mapping_file = self.user_dir / "gamepad_mapping.txt"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backward_compatibility_empty_config(self):
        # When launcher.json has no pad_controls, it defaults cleanly
        self.cfg_file.write_text("{}", encoding="utf-8")
        with mock.patch.object(launcher_mod, "USER", self.user_dir), \
             mock.patch.object(launcher_mod, "CONFIG", self.cfg_file):
            cfg = launcher_mod.load_config()
            self.assertIn("pad_controls", cfg)
            self.assertEqual(cfg["pad_controls"], {})
            self.assertEqual(controls.build_pad_map_spec(cfg["pad_controls"]), "")

    def test_saving_and_restoring_pad_controls(self):
        custom_controls = {"cross": "b", "circle": "a"}
        with mock.patch.object(launcher_mod, "USER", self.user_dir), \
             mock.patch.object(launcher_mod, "CONFIG", self.cfg_file):
            cfg = launcher_mod.load_config()
            cfg["pad_controls"] = custom_controls
            cfg["pad_style"] = "xbox"
            launcher_mod.save_config(cfg)

            # Reload
            reloaded = launcher_mod.load_config()
            self.assertEqual(reloaded.get("pad_controls"), custom_controls)
            self.assertEqual(reloaded.get("pad_style"), "xbox")

    def test_env_strips_inherited_and_sets_custom_spec(self):
        with mock.patch.object(launcher_mod, "USER", self.user_dir), \
             mock.patch.object(launcher_mod, "CONFIG", self.cfg_file), \
             mock.patch.object(launcher_mod, "MAPPING", self.mapping_file):

            # 1. Without custom controls: SPARTAN_PAD_MAP is not set even if parent environment had it
            with mock.patch.dict(os.environ, {"SPARTAN_PAD_MAP": "cross=y"}):
                launcher = launcher_mod.Launcher()
                launcher.withdraw()
                try:
                    launcher.cfg["pad_controls"] = {}
                    env = launcher._env()
                    self.assertNotIn("SPARTAN_PAD_MAP", env)
                finally:
                    launcher.destroy()

            # 2. With custom controls: SPARTAN_PAD_MAP is populated exactly
            launcher2 = launcher_mod.Launcher()
            launcher2.withdraw()
            try:
                launcher2.cfg["pad_controls"] = {"cross": "b", "circle": "a"}
                env2 = launcher2._env()
                self.assertEqual(env2.get("SPARTAN_PAD_MAP"), "cross=b,circle=a")
            finally:
                launcher2.destroy()

    def test_reset_mappings_does_not_delete_hardware_map(self):
        # Create a mock hardware mapping file
        self.mapping_file.write_text("030000005e0400008e02000000000000,X360,a:b0,b:b1\n", encoding="utf-8")
        self.assertTrue(self.mapping_file.exists())

        active_controls = {"cross": "b", "circle": "a"}
        controls.reset_all_controls(active_controls)

        # Hardware mapping file must still be present untouched
        self.assertTrue(self.mapping_file.exists())
        self.assertIn("030000005e0400008e02000000000000", self.mapping_file.read_text(encoding="utf-8"))

    def test_runtime_seam_pad_map_test(self):
        """Verifies that the compiled C runtime test validates SPARTAN_PAD_MAP against button state."""
        exe = REPO_ROOT / "out" / "gpu" / "pad-map-test.exe"
        if not exe.is_file():
            self.skipTest("out/gpu/pad-map-test.exe not built yet")
        env = os.environ.copy()
        env["PATH"] = str(REPO_ROOT / "bin") + os.pathsep + r"C:\msys64\clang64\bin" + os.pathsep + env.get("PATH", "")
        res = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"pad-map-test.exe failed: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
