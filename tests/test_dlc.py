#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Unit tests for Basara 4 PC Local DLC Support (Stage 2)."""

from paths import ROOT  # noqa: F401  (puts scripts/ on sys.path)
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

from dlc import (
    MAGIC,
    MANIFEST_VERSION,
    HEADER_SIZE,
    ENTRY_SIZE,
    MAX_ADDONS,
    STATUS_INSTALLED,
    DLCValidationError,
    is_valid_entitlement_id,
    discover_addons,
    build_binary_manifest,
    generate_manifest,
)


class TestDLCValidationAndDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b4_dlc_test_"))
        self.dlc_root = self.tmp / "dlc_root"
        self.dlc_root.mkdir()
        self.out_dir = self.tmp / "out"
        self.out_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_entitlement_id_validation(self):
        """Validates alphanumeric, hyphen, underscore, 1-16 chars."""
        self.assertTrue(is_valid_entitlement_id("COSTUME001"))
        self.assertTrue(is_valid_entitlement_id("DLC_01-EX"))
        self.assertTrue(is_valid_entitlement_id("1234567890123456"))  # 16 chars

        self.assertFalse(is_valid_entitlement_id(""))  # empty
        self.assertFalse(is_valid_entitlement_id("12345678901234567"))  # 17 chars (too long)
        self.assertFalse(is_valid_entitlement_id("COSTUME/01"))  # path traversal slash
        self.assertFalse(is_valid_entitlement_id(".."))  # path traversal
        self.assertFalse(is_valid_entitlement_id("COSTUME.01"))  # dots
        self.assertFalse(is_valid_entitlement_id("COSTUME 01"))  # space

    def test_no_dlc_directory(self):
        """None or empty string returns empty list without error."""
        self.assertEqual(discover_addons(None), [])
        self.assertEqual(discover_addons(""), [])

    def test_nonexistent_dlc_directory_raises(self):
        """Non-existent DLC directory raises DLCValidationError."""
        with self.assertRaises(DLCValidationError):
            discover_addons(self.dlc_root / "does_not_exist")

    def test_valid_folder_discovery_and_enumeration(self):
        """Auto-discovers valid add-on folders under <DLC_ROOT>/CUSA01159/."""
        title_dir = self.dlc_root / "CUSA01159"
        addon1 = title_dir / "COSTUME000000001"
        addon2 = title_dir / "WEAPON0000000001"
        addon1.mkdir(parents=True)
        addon2.mkdir(parents=True)

        (addon1 / "data.bin").write_bytes(b"DATA1")
        (addon2 / "data.bin").write_bytes(b"DATA2")

        addons = discover_addons(self.dlc_root, title_id="CUSA01159")
        self.assertEqual(len(addons), 2)
        labels = [a["entitlement_label"] for a in addons]
        self.assertIn("COSTUME000000001", labels)
        self.assertIn("WEAPON0000000001", labels)
        self.assertEqual(addons[0]["status"], STATUS_INSTALLED)
        self.assertEqual(addons[0]["service_label"], 0)

    def test_wrong_title_id_ignored(self):
        """Folders for other titles are ignored if expected title folder is missing."""
        wrong_dir = self.dlc_root / "CUSA99999"
        wrong_addon = wrong_dir / "COSTUME001"
        wrong_addon.mkdir(parents=True)
        (wrong_addon / "data.bin").write_bytes(b"WRONG")

        addons = discover_addons(self.dlc_root, title_id="CUSA01159")
        self.assertEqual(addons, [])

    def test_empty_addon_folder_rejected(self):
        """An empty add-on folder is rejected as invalid/corrupted."""
        title_dir = self.dlc_root / "CUSA01159"
        empty_addon = title_dir / "EMPTY001"
        empty_addon.mkdir(parents=True)

        with self.assertRaises(DLCValidationError) as ctx:
            discover_addons(self.dlc_root, title_id="CUSA01159")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_duplicate_entitlement_ids_rejected(self):
        """Duplicate entitlement IDs in user manifest are rejected."""
        title_dir = self.dlc_root / "CUSA01159"
        addon1 = title_dir / "ADDON1"
        addon1.mkdir(parents=True)
        (addon1 / "file.bin").write_bytes(b"A")

        manifest = {
            "version": 1,
            "title_id": "CUSA01159",
            "addons": [
                {"entitlement_label": "SAME_LABEL", "path": "ADDON1"},
                {"entitlement_label": "SAME_LABEL", "path": "ADDON1"}
            ]
        }
        (title_dir / "dlc_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(DLCValidationError) as ctx:
            discover_addons(self.dlc_root, title_id="CUSA01159")
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_unsafe_path_traversal_in_manifest_rejected(self):
        """Manifest paths attempting to escape DLC root are rejected."""
        title_dir = self.dlc_root / "CUSA01159"
        title_dir.mkdir(parents=True)

        manifest = {
            "version": 1,
            "title_id": "CUSA01159",
            "addons": [
                {"entitlement_label": "ESCAPED01", "path": "../../windows"}
            ]
        }
        (title_dir / "dlc_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(DLCValidationError) as ctx:
            discover_addons(self.dlc_root, title_id="CUSA01159")
        self.assertIn("missing or unsafe", str(ctx.exception).lower())

    def test_binary_and_json_manifest_generation(self):
        """generate_manifest produces valid addons.json and binary B4ADD001."""
        title_dir = self.dlc_root / "CUSA01159"
        addon = title_dir / "COSTUME001"
        addon.mkdir(parents=True)
        (addon / "asset.arc").write_bytes(b"ARC_DATA")

        json_path, bin_path, addons = generate_manifest(self.dlc_root, self.out_dir, title_id="CUSA01159")
        self.assertTrue(json_path.is_file())
        self.assertTrue(bin_path.is_file())
        self.assertEqual(len(addons), 1)

        # Validate JSON content
        manifest = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["title_id"], "CUSA01159")
        self.assertEqual(manifest["count"], 1)
        self.assertEqual(manifest["addons"][0]["entitlement_label"], "COSTUME001")

        # Validate binary layout
        bin_data = bin_path.read_bytes()
        self.assertEqual(len(bin_data), HEADER_SIZE + ENTRY_SIZE)
        magic, ver, count, title_b = struct.unpack("<8sII16s", bin_data[:HEADER_SIZE])
        self.assertEqual(magic, MAGIC)
        self.assertEqual(ver, MANIFEST_VERSION)
        self.assertEqual(count, 1)
        self.assertEqual(title_b.split(b"\x00")[0].decode(), "CUSA01159")

        # Entry layout
        srv, ent_b, status, host_b, flags = struct.unpack("<I20sI512sI", bin_data[HEADER_SIZE:])
        self.assertEqual(srv, 0)
        self.assertEqual(ent_b.split(b"\x00")[0].decode(), "COSTUME001")
        self.assertEqual(status, STATUS_INSTALLED)
        self.assertEqual(flags, 0)
        self.assertEqual(host_b.split(b"\x00")[0].decode(), str(addon.resolve()))


# Put launcher on sys.path for launcher integration tests
sys.path.insert(0, str(ROOT / 'launcher'))
import sumeragi_launcher as basara4_launcher  # noqa: E402
from unittest import mock
try:
    import packaging.sumeragi.make_package as make_package
except ModuleNotFoundError:
    import importlib.util
    _spec = importlib.util.spec_from_file_location('make_package', ROOT / 'packaging' / 'sumeragi' / 'make_package.py')
    make_package = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(make_package)


class TestLauncherDLCIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="b4_launcher_dlc_"))
        self.game = self.tmp / "game"
        self.game.mkdir()
        (self.game / "eboot.bin").write_bytes(b"\x7fELF")
        self.dlc_root = self.tmp / "dlc"
        self.dlc_root.mkdir()
        addon = self.dlc_root / "CUSA01159" / "COSTUME001"
        addon.mkdir(parents=True)
        (addon / "asset.arc").write_bytes(b"ARC")
        self.out = self.tmp / "out"
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_launcher_config_includes_dlc_dir(self):
        """Launcher defaults and config persistence handle dlc_dir."""
        self.assertIn("dlc_dir", basara4_launcher.DEFAULTS)
        self.assertEqual(basara4_launcher.DEFAULTS["dlc_dir"], "")

    def test_launcher_prepare_then_launch_with_dlc(self):
        """_prepare_then_launch generates addons.bin and passes --addons when dlc_dir is configured."""
        launcher = mock.MagicMock()
        launcher.cfg = {"game": str(self.game), "update_dir": "", "dlc_dir": str(self.dlc_root), "fps_limit": 60}
        launcher.busy = False
        launcher.proc = None

        with mock.patch.object(basara4_launcher, "OUT", self.out), \
             mock.patch.object(basara4_launcher, "image_ready", return_value=True):
            basara4_launcher.Launcher._prepare_then_launch(
                launcher, self.game, None, Path("dummy.exe"), dlc_dir=self.dlc_root
            )

        error, effective_game, exe, patch_args, notice, view = launcher.pending
        self.assertIsNone(error)
        self.assertEqual(effective_game, self.game)
        self.assertIn("--addons", patch_args)
        addons_bin_idx = patch_args.index("--addons") + 1
        self.assertEqual(Path(patch_args[addons_bin_idx]), self.out / "addons.bin")
        self.assertTrue((self.out / "addons.bin").is_file())

    def test_launcher_prepare_then_launch_without_dlc_removes_stale_manifest(self):
        """_prepare_then_launch removes stale addons.bin if DLC is not configured."""
        stale_bin = self.out / "addons.bin"
        stale_bin.write_bytes(b"STALE")

        launcher = mock.MagicMock()
        launcher.cfg = {"game": str(self.game), "update_dir": "", "dlc_dir": "", "fps_limit": 60}
        launcher.busy = False
        launcher.proc = None

        with mock.patch.object(basara4_launcher, "OUT", self.out), \
             mock.patch.object(basara4_launcher, "image_ready", return_value=True):
            basara4_launcher.Launcher._prepare_then_launch(
                launcher, self.game, None, Path("dummy.exe"), dlc_dir=None
            )

        error, effective_game, exe, patch_args, notice, view = launcher.pending
        self.assertIsNone(error)
        self.assertNotIn("--addons", patch_args)
        self.assertFalse(stale_bin.exists(), "Stale addons.bin should have been deleted")

    def test_packaging_includes_dlc_script(self):
        """Packaging script includes dlc.py in PREPARE_SCRIPTS."""
        self.assertIn("dlc.py", make_package.PREPARE_SCRIPTS)


if __name__ == "__main__":
    unittest.main()
