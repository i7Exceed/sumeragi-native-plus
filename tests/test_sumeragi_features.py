import unittest
from pathlib import Path
import tempfile
import sys

# Ensure launcher is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "launcher"))
sys.path.insert(0, str(ROOT / "scripts"))

from sumeragi_launcher import (
    SYSTEM_GPUS,
    analyze_crash_log,
    CRASH_GUIDES,
    enumerate_vulkan_gpus,
)


class SumeragiFeaturesTests(unittest.TestCase):
    def test_gpu_enumeration_returns_auto_and_devices(self):
        gpus = enumerate_vulkan_gpus()
        self.assertGreaterEqual(len(gpus), 1)
        # First entry is always Auto
        auto_entry = gpus[0]
        self.assertEqual(auto_entry[0], -1)
        self.assertIn("Auto", auto_entry[1])

    def test_crash_analyzer_detects_error_1455_commitment_limit(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as f:
            f.write(
                "[0 ms] log.start\n"
                "[100 ms] memory.init\n"
                "Runtime: cannot create 3136 MiB of guest memory (error 1455: ERROR_COMMITMENT_LIMIT); is the page file large enough?\n"
            )
            temp_path = Path(f.name)

        try:
            analysis = analyze_crash_log(temp_path)
            self.assertEqual(analysis["category"], "memory_commit")
            self.assertIn("memory_commit", CRASH_GUIDES)
            self.assertTrue(any("1455" in err for err in analysis["matched_errors"]))
        finally:
            temp_path.unlink(missing_ok=True)

    def test_crash_analyzer_detects_vulkan_device_lost(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as f:
            f.write(
                "[100 ms] Render.Vulkan\n"
                "GPU [Render.Vulkan] <Error> vkQueueSubmit failed: VK_ERROR_DEVICE_LOST\n"
            )
            temp_path = Path(f.name)

        try:
            analysis = analyze_crash_log(temp_path)
            self.assertEqual(analysis["category"], "vulkan")
            self.assertTrue(any("VK_ERROR_DEVICE_LOST" in err for err in analysis["matched_errors"]))
        finally:
            temp_path.unlink(missing_ok=True)

    def test_crash_analyzer_detects_missing_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as f:
            f.write(
                "[500 ms] Runtime: open(rom:/sound/stream/bgm01.at9) -> not found\n"
            )
            temp_path = Path(f.name)

        try:
            analysis = analyze_crash_log(temp_path)
            self.assertEqual(analysis["category"], "missing_file")
        finally:
            temp_path.unlink(missing_ok=True)

    def test_crash_analyzer_handles_empty_or_missing_log(self):
        missing_path = Path("non_existent_log_12345.log")
        analysis = analyze_crash_log(missing_path)
        self.assertEqual(analysis["category"], "general")
        self.assertEqual(analysis["total_lines"], 0)

    def test_crash_guides_i18n_localization(self):
        import sumeragi_i18n as i18n
        # Test English
        i18n.set_language("en")
        guide_en = CRASH_GUIDES["memory_commit"]
        self.assertIn("Virtual Memory", guide_en["title"])
        self.assertIn("Paging File", guide_en["title"])

        # Test Indonesian
        i18n.set_language("id")
        guide_id = CRASH_GUIDES["memory_commit"]
        self.assertIn("Memori Virtual", guide_id["title"])
        self.assertIn("Paging File", guide_id["title"])

        # Reset back to English
        i18n.set_language("en")

    def test_sumeragi_cheats_module(self):
        import sumeragi_cheats as cheats
        self.assertIn("gold", cheats.CHEATS)
        self.assertIn("Gold Won't Decrease", cheats.CHEATS["gold"]["name"])
        normalized = cheats.normalize_selection(["gold", "special_coin"])
        self.assertEqual(normalized, ["gold", "special_coin"])
        cheats.validate_selection(normalized)
        with self.assertRaises(ValueError):
            cheats.validate_selection(["invalid_cheat_id"])

    def test_sumeragi_config_defaults_and_descriptions(self):
        import sumeragi_config as sc
        self.assertEqual(sc.DEFAULTS["input_mode"], "controller")
        self.assertEqual(sc.DEFAULTS["mouse_camera"], True)
        self.assertEqual(sc.DEFAULTS["mouse_sens"], 100)
        self.assertIn("square", sc.DEFAULT_PC_KEYMAP)
        self.assertGreaterEqual(len(sc.ACTION_DESCRIPTIONS), 16)

    def test_crash_dialog_and_theme_font_small(self):
        import tkinter as tk
        import sumeragi_theme as theme
        from sumeragi_crash import SumeragiCrashDialog

        self.assertEqual(theme.FONT_SMALL, theme.FONT_CAPTION)
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception as e:
            self.skipTest(f"Tkinter display not available: {e}")
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as f:
                f.write("ERROR: invalid content profile\n")
                log_path = Path(f.name)
            try:
                dlg = SumeragiCrashDialog(root, 1, log_path)
                dlg.destroy()
            finally:
                log_path.unlink(missing_ok=True)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
