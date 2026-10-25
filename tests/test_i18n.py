#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed.
"""Comprehensive unit tests for the Sumeragi Native+ i18n subsystem."""

import json
from pathlib import Path
import re
import sys
import unittest

# Setup sys.path
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
LAUNCHER_DIR = REPO_ROOT / "launcher"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(LAUNCHER_DIR) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_DIR))

import sumeragi_i18n as i18n


class TestI18nSystem(unittest.TestCase):
    def setUp(self):
        self.locales_dir = LAUNCHER_DIR / "i18n" / "locales"
        self.en_file = self.locales_dir / "en.json"
        self.id_file = self.locales_dir / "id.json"

    def test_locale_files_exist_and_valid_json(self):
        """Verifies en.json and id.json exist and parse as valid JSON objects."""
        self.assertTrue(self.en_file.is_file(), f"Missing {self.en_file}")
        self.assertTrue(self.id_file.is_file(), f"Missing {self.id_file}")

        en_data = json.loads(self.en_file.read_text(encoding="utf-8"))
        id_data = json.loads(self.id_file.read_text(encoding="utf-8"))
        self.assertIsInstance(en_data, dict)
        self.assertIsInstance(id_data, dict)
        self.assertGreater(len(en_data), 50)
        self.assertGreater(len(id_data), 50)

    def test_key_parity_between_english_and_indonesian(self):
        """Ensures every key in en.json exists in id.json and vice-versa."""
        en_data = json.loads(self.en_file.read_text(encoding="utf-8"))
        id_data = json.loads(self.id_file.read_text(encoding="utf-8"))

        missing_in_id = set(en_data.keys()) - set(id_data.keys())
        missing_in_en = set(id_data.keys()) - set(en_data.keys())

        self.assertEqual(missing_in_id, set(), f"Keys in en.json missing in id.json: {missing_in_id}")
        self.assertEqual(missing_in_en, set(), f"Keys in id.json missing in en.json: {missing_in_en}")

    def test_placeholders_match(self):
        """Ensures named placeholders {var} match between en.json and id.json."""
        en_data = json.loads(self.en_file.read_text(encoding="utf-8"))
        id_data = json.loads(self.id_file.read_text(encoding="utf-8"))

        placeholder_pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")

        for key, en_val in en_data.items():
            en_placeholders = set(placeholder_pattern.findall(en_val))
            id_val = id_data.get(key, "")
            id_placeholders = set(placeholder_pattern.findall(id_val))
            self.assertEqual(
                en_placeholders,
                id_placeholders,
                f"Placeholder mismatch for key '{key}': EN={en_placeholders} vs ID={id_placeholders}",
            )

    def test_safe_translation_and_formatting(self):
        """Tests the t() translation helper with formatting and safe missing args."""
        i18n.set_language("en")
        self.assertEqual(i18n.t("nav.home"), "Home")
        self.assertEqual(i18n.t("nav.settings"), "Settings")

        # Test formatting
        formatted = i18n.t("app.developed_by", author="i7Exceed", version="1.0.4")
        self.assertIn("i7Exceed", formatted)
        self.assertIn("1.0.4", formatted)

        # Test partial/missing kwargs does not raise KeyError
        safe_format = i18n.t("app.developed_by", author="i7Exceed")
        self.assertIn("i7Exceed", safe_format)
        self.assertIn("{version}", safe_format)

    def test_dynamic_language_switch_and_subscriptions(self):
        """Tests dynamic language switching and subscription callbacks."""
        notified = []

        def on_change(lang):
            notified.append(lang)

        i18n.on_language_change(on_change)
        try:
            i18n.set_language("id")
            self.assertEqual(i18n.get_language(), "id")
            self.assertEqual(i18n.t("nav.home"), "Beranda")
            self.assertEqual(i18n.t("nav.settings"), "Pengaturan")
            self.assertEqual(notified, ["id"])

            i18n.set_language("en")
            self.assertEqual(i18n.get_language(), "en")
            self.assertEqual(i18n.t("nav.home"), "Home")
            self.assertEqual(notified, ["id", "en"])
        finally:
            i18n.set_language("en")

    def test_missing_and_invalid_language_fallback(self):
        """Tests that invalid language or unknown keys fall back safely."""
        i18n.set_language("invalid_locale_xyz")
        # Should fallback to default 'en'
        self.assertEqual(i18n.get_language(), "en")
        self.assertEqual(i18n.t("nav.home"), "Home")

        # Unknown key returns the key itself
        self.assertEqual(i18n.t("totally.nonexistent.key"), "totally.nonexistent.key")


if __name__ == "__main__":
    unittest.main()
