# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed, Felipe Prado.
"""Comprehensive unit tests for the Sumeragi Native+ Trophy System."""

import io
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
from paths import ROOT  # sets up sys.path

import sumeragi_native_trophies as trophies
from sumeragi_native_trophies import (
    TRP_MAGIC,
    TROPHY_MAX,
)

try:
    from PIL import Image
except ImportError:
    Image = None


def build_trp(entries, magic=TRP_MAGIC, element=0x40):
    """Builds a synthetic in-memory TRP binary package with given (name, bytes) entries."""
    header_size = 0x60
    offset = header_size + element * len(entries)
    table, body = b'', b''
    for name, data in entries:
        table += name.encode('latin-1').ljust(0x20, b'\0') + struct.pack('>QQ', offset + len(body), len(data))
        table = table.ljust(len(table) + element - 0x30, b'\0')
        body += data
    header = magic + struct.pack('>I', 3) + struct.pack('>Q', header_size + len(table) + len(body))
    header += struct.pack('>II', len(entries), element)
    return header.ljust(header_size, b'\0') + table + body


def solid_png(rgb):
    """Generates a solid color 32x32 PNG byte sequence."""
    if not Image:
        return b'\x89PNG\r\n\x1a\nfake'
    out = io.BytesIO()
    Image.new('RGB', (32, 32), rgb).save(out, 'PNG')
    return out.getvalue()


class TestTrophyPackageParsing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='b4_trophy_test_'))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_file(self, name, data):
        p = self.tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_dynamic_trophy_ids_and_count(self):
        """Basara 4 Sumeragi has 43 trophies (0 to 42) or dynamic IDs."""
        png = b'\x89PNG-fake-icon'
        entries = [('TROPCONF.ESFM', b'encrypted_meta')]
        for i in range(43):
            entries.append((f'TROP{i:03d}.PNG', png + bytes([i])))

        trp_bytes = build_trp(entries)
        path = self.write_file('trophy00.trp', trp_bytes)

        icons = trophies.read_trp_icons(path)
        self.assertEqual(len(icons), 43)
        self.assertEqual(icons[0], png + bytes([0]))
        self.assertEqual(icons[42], png + bytes([42]))

        ids, total, ic = trophies.read_trp_entries(path)
        self.assertEqual(ids, list(range(43)))
        self.assertEqual(total, 43)
        self.assertEqual(len(ic), 43)

    def test_malformed_and_edge_case_packages(self):
        good = build_trp([('TROP001.PNG', b'abc')])
        # Missing file
        self.assertEqual(trophies.read_trp_icons(self.tmp / 'missing.trp'), {})
        # Empty file
        self.assertEqual(trophies.read_trp_icons(self.write_file('empty.trp', b'')), {})
        # Invalid magic
        self.assertEqual(trophies.read_trp_icons(self.write_file('bad_magic.trp', b'\0\0\0\0' + good[4:])), {})
        # Too small element size
        self.assertEqual(trophies.read_trp_icons(self.write_file('bad_elem.trp', build_trp([('TROP001.PNG', b'abc')], element=8))), {})
        # Truncated entry offset beyond file size
        self.assertEqual(trophies.read_trp_icons(self.write_file('truncated.trp', good[:-2])), {})


class TestTrophyStateAndProgress(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='b4_trophy_state_'))
        self.dat = self.tmp / 'trophies.dat'

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_read_and_write_unlocked_bits(self):
        unlocked_in = {0, 5, 9, 31, 32, 42, 127}
        trophies.write_unlocked_trophies(self.dat, unlocked_in)
        self.assertTrue(self.dat.is_file())
        self.assertEqual(self.dat.stat().st_size, 16)

        unlocked_out = trophies.read_unlocked_trophies(self.dat)
        self.assertEqual(unlocked_out, unlocked_in)

    def test_nonexistent_and_short_dat(self):
        self.assertEqual(trophies.read_unlocked_trophies(self.tmp / 'nonexistent.dat'), set())
        # 1 byte with bit 1 set -> trophy 1
        short = self.tmp / 'short.dat'
        short.write_bytes(b'\x02')
        self.assertEqual(trophies.read_unlocked_trophies(short), {1})

    def test_calculate_progress(self):
        unlocked = {0, 1, 2, 9}
        have, total, pct = trophies.calculate_progress(unlocked, 43)
        self.assertEqual(have, 4)
        self.assertEqual(total, 43)
        self.assertAlmostEqual(pct, 4 / 43 * 100.0, places=2)

        # Zero total handles gracefully without divide by zero
        self.assertEqual(trophies.calculate_progress(set(), 0), (0, 0, 0.0))

    def test_filter_trophies(self):
        all_ids = list(range(5))
        unlocked = {1, 3}
        self.assertEqual(trophies.filter_trophies(all_ids, unlocked, 'all'), [0, 1, 2, 3, 4])
        self.assertEqual(trophies.filter_trophies(all_ids, unlocked, 'unlocked'), [1, 3])
        self.assertEqual(trophies.filter_trophies(all_ids, unlocked, 'locked'), [0, 2, 4])

    def test_safe_reset_with_backup(self):
        trophies.write_unlocked_trophies(self.dat, {0, 9, 15})
        ok, backup_path = trophies.reset_trophies(self.dat)
        self.assertTrue(ok)
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_path.is_file())
        self.assertEqual(backup_path.name, 'trophies.dat.bak')

        # Backup has previous state
        self.assertEqual(trophies.read_unlocked_trophies(backup_path), {0, 9, 15})
        # Reset file has 0 trophies unlocked
        self.assertEqual(trophies.read_unlocked_trophies(self.dat), set())


class TestTrophyTextsAndLocalization(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='b4_trophy_texts_'))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bilingual_labels_english_and_indonesian(self):
        en = trophies.get_ui('en')
        id_ = trophies.get_ui('id')
        keys = {'heading', 'notice', 'unlocked', 'locked', 'all', 'only_unlocked', 'only_locked', 'counter', 'hint'}
        for k in keys:
            self.assertIn(k, en)
            self.assertIn(k, id_)
            self.assertTrue(en[k].strip())
            self.assertTrue(id_[k].strip())

    def test_load_and_save_user_texts_preserving_overrides(self):
        text_file = self.tmp / 'trophy_texts.txt'
        content = (
            "@heading=Custom Trophies\n"
            "@notice=UNLOCKED!\n"
            "0=The Conqueror | Obtain all trophies\n"
            "9=Warlord's Path | Win 50 battles\n"
        )
        text_file.write_text(content, encoding='utf-8')

        labels, texts = trophies.load_trophy_texts(self.tmp)
        self.assertEqual(labels.get('heading'), 'Custom Trophies')
        self.assertEqual(labels.get('notice'), 'UNLOCKED!')
        self.assertEqual(texts[0], ('The Conqueror', 'Obtain all trophies'))
        self.assertEqual(texts[9], ("Warlord's Path", 'Win 50 battles'))

        # Save new label while preserving custom trophy descriptions
        trophies.save_trophy_texts(self.tmp, labels={'counter': '{} of {} unlocked'}, preserve_existing=True)
        new_labels, new_texts = trophies.load_trophy_texts(self.tmp)
        self.assertEqual(new_labels.get('heading'), 'Custom Trophies')
        self.assertEqual(new_labels.get('counter'), '{} of {} unlocked')
        self.assertEqual(new_texts[9], ("Warlord's Path", 'Win 50 battles'))


class TestPackageResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='b4_trophy_res_'))
        self.game = self.tmp / 'game'
        self.update = self.tmp / 'update'
        self.game.mkdir()
        self.update.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolves_update_package_first_and_falls_back_to_base(self):
        base_trp = self.game / 'sce_sys' / 'trophy' / 'trophy00.trp'
        base_trp.parent.mkdir(parents=True)
        base_trp.write_bytes(build_trp([('TROP000.PNG', b'base')]))

        update_trp = self.update / 'sce_sys' / 'trophy' / 'trophy00.trp'
        update_trp.parent.mkdir(parents=True)
        update_trp.write_bytes(build_trp([('TROP000.PNG', b'update')]))

        # With both present, update is selected
        self.assertEqual(trophies.resolve_trophy_package(self.game, self.update), update_trp)

        # When update has no trp, base is selected
        update_trp.unlink()
        self.assertEqual(trophies.resolve_trophy_package(self.game, self.update), base_trp)

        # When neither has trp, returns None
        base_trp.unlink()
        self.assertIsNone(trophies.resolve_trophy_package(self.game, self.update))


class TestTrophyCategoryDetermination(unittest.TestCase):
    @unittest.skipUnless(Image, 'Pillow is not installed')
    def test_category_colors(self):
        colours = {
            'platinum': (139, 167, 167),
            'bronze': (137, 89, 52),
            'silver': (136, 119, 104),
            'gold': (141, 104, 27)
        }
        for cat, rgb in colours.items():
            self.assertEqual(trophies.trophy_tier(solid_png(rgb)), cat)

        self.assertEqual(trophies.trophy_tier(b'invalid_png'), '')
        self.assertEqual(trophies.trophy_tier(solid_png((0, 0, 0))), '')


class TestTrophiesWindowUI(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = Path(tempfile.mkdtemp(prefix='b4_ui_test_'))
        self.game = self.tmp / 'game'
        self.game.mkdir()
        self.user = self.tmp / 'user'
        self.user.mkdir()

    def tearDown(self):
        import shutil
        self.root.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_state_and_refresh(self):
        win = trophies.TrophiesWindow(self.root, str(self.game), '', self.user, language='en')
        self.assertEqual(win.total_count, 0)
        self.assertEqual(len(win.unlocked_set), 0)
        self.assertIn('No trophy package found', win._t('no_package_msg'))
        win.destroy()

    def test_populated_state_filters_and_language_toggle(self):
        # Create synthetic TRP with 43 trophies
        trp_path = self.game / 'sce_sys' / 'trophy' / 'trophy00.trp'
        trp_path.parent.mkdir(parents=True)
        entries = [(f'TROP{i:03d}.PNG', solid_png((141, 104, 27))) for i in range(43)]
        trp_path.write_bytes(build_trp(entries))

        # Create trophies.dat with 3 trophies unlocked: 0, 5, 9
        trophies.write_unlocked_trophies(self.user / 'trophies.dat', {0, 5, 9})

        win = trophies.TrophiesWindow(self.root, str(self.game), '', self.user, language='en')
        self.assertEqual(win.total_count, 43)
        self.assertEqual(win.unlocked_set, {0, 5, 9})

        # Test filter switching
        win._set_filter('unlocked')
        self.assertEqual(win.filter_mode, 'unlocked')
        win._set_filter('locked')
        self.assertEqual(win.filter_mode, 'locked')
        win._set_filter('all')
        self.assertEqual(win.filter_mode, 'all')

        # Test language toggle
        win._toggle_language()
        self.assertEqual(win.lang, 'id')
        self.assertEqual(win._t('heading'), 'Piala')
        win._toggle_language()
        self.assertEqual(win.lang, 'en')
        self.assertEqual(win._t('heading'), 'Trophies')

        win.destroy()


class TestLauncherRuntimeConsistency(unittest.TestCase):
    def test_env_resolves_identical_user_dir(self):
        import sumeragi_launcher as launcher_mod
        # Create a mock or direct instance to verify env variables
        launcher = None
        try:
            launcher = launcher_mod.Launcher()
            launcher.withdraw()
            env = launcher._env()
            self.assertIn('SPARTAN_USER_DIR', env)
            self.assertIn('SPARTAN_GPU_USER_DIR', env)
            # Both must point to the identical absolute path
            self.assertEqual(
                Path(env['SPARTAN_USER_DIR']).resolve(),
                Path(env['SPARTAN_GPU_USER_DIR']).resolve()
            )
        finally:
            if launcher:
                launcher.destroy()


if __name__ == '__main__':
    unittest.main()
