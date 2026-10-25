from paths import ROOT  # noqa: F401  (puts scripts/ on the path)
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

import game_update
from mods import is_link
import patches
from prepare import sfo

# Put launcher on sys.path for launcher integration tests
sys.path.insert(0, str(ROOT / 'launcher'))
import sumeragi_launcher as basara4_launcher  # noqa: E402


def write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding='utf-8')


def make_sfo(entries):
    """Builds valid binary \\0PSF metadata for test fixtures."""
    keys_data = bytearray()
    values_data = bytearray()
    index_table = []
    for k, v in sorted(entries.items()):
        key_offset = len(keys_data)
        keys_data += k.encode('utf-8') + b'\0'
        val_offset = len(values_data)
        if isinstance(v, int):
            fmt = 0x404
            val_bytes = struct.pack('<I', v)
        else:
            fmt = 0x204
            val_bytes = v.encode('utf-8') + b'\0'
        values_data += val_bytes
        index_table.append((key_offset, fmt, len(val_bytes), len(val_bytes), val_offset))
    header_size = 20
    entries_size = len(index_table) * 16
    keys_offset = header_size + entries_size
    values_offset = keys_offset + len(keys_data)
    header = struct.pack('<4sIIII', b'\0PSF', 0x0101, keys_offset, values_offset, len(index_table))
    out = bytearray(header)
    for entry in index_table:
        out += struct.pack('<HHIII', *entry)
    out += keys_data
    out += values_data
    return bytes(out)


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hashes(directory):
    return {p.relative_to(directory).as_posix(): file_hash(p)
            for p in Path(directory).rglob('*') if p.is_file()}


def no_links_but_hard_links():
    """Simulates a network share (SMB): symlinks and junctions are refused, hard links work.
    CreateJunction creates the directory and only then refuses the reparse point."""
    def create_junction(src, dst):
        Path(dst).mkdir()
        raise PermissionError(5, 'Access is denied')
    return (mock.patch.object(Path, 'symlink_to', side_effect=PermissionError(5, 'Access is denied')),
            mock.patch('mods.os.name', 'nt'),
            mock.patch.dict(sys.modules, {'_winapi': types.SimpleNamespace(CreateJunction=create_junction)}))


class GameUpdateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.base, self.update, self.out = self.root / 'base', self.root / 'update', self.root / 'out'
        write(self.base / 'eboot.bin', 'base eboot')
        write(self.base / 'EXEC/WAD/A.WAD', 'wad')
        write(self.base / 'sce_sys/icon0.png', 'old icon')
        write(self.update / 'eboot.bin', 'update eboot')
        write(self.update / 'SCE_SYS/param.sfo', 'new sfo')
        write(self.update / 'SCE_SYS/icon0.png', 'new icon')

    def view(self, ids=('CUSA01623', 'CUSA01623')):
        with mock.patch('patches.game_title_id', side_effect=list(ids)):
            return game_update.create_view(self.base, self.update, self.out)

    def test_update_files_replace_base_files_and_the_rest_stays(self):
        view = self.view()
        self.assertEqual((view / 'eboot.bin').read_text(), 'update eboot')
        self.assertEqual((view / 'EXEC/WAD/A.WAD').read_text(), 'wad')
        self.assertEqual((view / 'sce_sys/icon0.png').read_text(), 'new icon')
        self.assertEqual((view / 'sce_sys/param.sfo').read_text(), 'new sfo')
        self.assertEqual([p.name for p in view.iterdir() if p.name.lower() == 'sce_sys'], ['sce_sys'])

    def test_folders_the_update_leaves_alone_are_linked_whole(self):
        view = self.view()
        self.assertTrue(is_link(view / 'EXEC'))
        self.assertFalse(is_link(view / 'sce_sys'))  # merged: base and update files together

    def test_removing_the_view_leaves_the_dumps_whole(self):
        view = self.view()
        game_update.remove_view(view)
        self.assertFalse(view.exists())
        self.assertEqual((self.base / 'EXEC/WAD/A.WAD').read_text(), 'wad')
        self.assertEqual((self.base / 'sce_sys/icon0.png').read_text(), 'old icon')
        self.assertEqual((self.update / 'SCE_SYS/param.sfo').read_text(), 'new sfo')

    def test_dumps_are_not_modified(self):
        self.view()
        self.assertEqual((self.base / 'eboot.bin').read_text(), 'base eboot')
        self.assertEqual((self.base / 'sce_sys/icon0.png').read_text(), 'old icon')

    def test_a_network_share_without_junctions_mirrors_the_tree(self):
        with contextlib.ExitStack() as stack:
            for patcher in no_links_but_hard_links():
                stack.enter_context(patcher)
            view = self.view()
        self.assertEqual((view / 'eboot.bin').read_text(), 'update eboot')
        self.assertEqual((view / 'EXEC/WAD/A.WAD').read_text(), 'wad')
        self.assertEqual((view / 'sce_sys/icon0.png').read_text(), 'new icon')
        self.assertEqual((view / 'sce_sys/param.sfo').read_text(), 'new sfo')
        self.assertEqual((self.base / 'EXEC/WAD/A.WAD').read_text(), 'wad')
        self.assertEqual((self.base / 'sce_sys/icon0.png').read_text(), 'old icon')
        game_update.remove_view(view)
        self.assertFalse(view.exists())
        self.assertEqual((self.base / 'EXEC/WAD/A.WAD').read_text(), 'wad')
        self.assertEqual((self.base / 'sce_sys/icon0.png').read_text(), 'old icon')

    def test_different_titles_and_nested_folders_are_refused(self):
        with self.assertRaises(ValueError):
            self.view(('CUSA01623', 'CUSA01715'))
        with mock.patch('patches.game_title_id', return_value='CUSA01623'):
            with self.assertRaises(ValueError):
                game_update.create_view(self.base, self.base / 'EXEC', self.out)
        self.assertEqual(list(self.out.iterdir()) if self.out.exists() else [], [])

    def test_case_insensitive_directory_merges(self):
        write(self.base / 'DVDROOT_PS4/DATA/WAD/STAGE.WAD', 'base stage')
        write(self.base / 'DVDROOT_PS4/DATA/WAD/MENU.WAD', 'base menu')
        write(self.update / 'dvdroot_ps4/data/wad/stage.wad', 'update stage')
        write(self.update / 'dvdroot_ps4/data/wad/NEW.WAD', 'new wad')
        view = self.view()
        self.assertEqual((view / 'DVDROOT_PS4/DATA/WAD/STAGE.WAD').read_text(), 'update stage')
        self.assertEqual((view / 'DVDROOT_PS4/DATA/WAD/MENU.WAD').read_text(), 'base menu')
        self.assertEqual((view / 'DVDROOT_PS4/DATA/WAD/NEW.WAD').read_text(), 'new wad')
        # Casing of base folder preserved, no duplicate folders created
        self.assertEqual([p.name for p in view.iterdir() if p.name.lower() == 'dvdroot_ps4'], ['DVDROOT_PS4'])

    def test_preservation_of_both_original_dumps_byte_exact(self):
        base_before = tree_hashes(self.base)
        update_before = tree_hashes(self.update)
        view = self.view()
        self.assertEqual(tree_hashes(self.base), base_before)
        self.assertEqual(tree_hashes(self.update), update_before)
        # Read files through view
        _ = (view / 'eboot.bin').read_bytes()
        _ = (view / 'EXEC/WAD/A.WAD').read_bytes()
        game_update.remove_view(view)
        self.assertEqual(tree_hashes(self.base), base_before)
        self.assertEqual(tree_hashes(self.update), update_before)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.base = self.root / 'base'
        self.update = self.root / 'update'
        write(self.base / 'eboot.bin', b'\x7fELF base eboot')
        write(self.base / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.00'}))
        write(self.update / 'eboot.bin', b'\x7fELF update eboot')
        write(self.update / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.02'}))

    def test_base_only_validation_succeeds(self):
        b_meta, u_meta = game_update.validate_game(self.base)
        self.assertEqual(b_meta.get('TITLE_ID'), 'CUSA01159')
        self.assertEqual(b_meta.get('APP_VER'), '01.00')
        self.assertIsNone(u_meta)

    def test_base_and_update_validation_succeeds(self):
        b_meta, u_meta = game_update.validate_game(self.base, self.update)
        self.assertEqual(b_meta.get('TITLE_ID'), 'CUSA01159')
        self.assertEqual(b_meta.get('APP_VER'), '01.00')
        self.assertIsNotNone(u_meta)
        assert u_meta is not None
        self.assertEqual(u_meta.get('TITLE_ID'), 'CUSA01159')
        self.assertEqual(u_meta.get('APP_VER'), '01.02')

    def test_mismatched_title_ids_rejected(self):
        write(self.update / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01715', 'APP_VER': '01.02'}))
        with self.assertRaisesRegex(ValueError, 'not the same title'):
            game_update.validate_game(self.base, self.update)

    def test_missing_base_eboot_rejected(self):
        (self.base / 'eboot.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing eboot.bin'):
            game_update.validate_game(self.base)

    def test_missing_base_sfo_rejected(self):
        (self.base / 'sce_sys/param.sfo').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing sce_sys/param.sfo'):
            game_update.validate_game(self.base)

    def test_corrupt_base_sfo_rejected(self):
        write(self.base / 'sce_sys/param.sfo', b'not a valid sfo at all')
        with self.assertRaisesRegex(ValueError, 'Invalid metadata'):
            game_update.validate_game(self.base)

    def test_base_missing_title_id_rejected(self):
        write(self.base / 'sce_sys/param.sfo', make_sfo({'APP_VER': '01.00'}))
        with self.assertRaisesRegex(ValueError, 'TITLE_ID'):
            game_update.validate_game(self.base)

    def test_base_missing_app_ver_rejected(self):
        write(self.base / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159'}))
        with self.assertRaisesRegex(ValueError, 'APP_VER'):
            game_update.validate_game(self.base)

    def test_missing_update_eboot_rejected(self):
        (self.update / 'eboot.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing eboot.bin'):
            game_update.validate_game(self.base, self.update)

    def test_missing_update_sfo_rejected(self):
        (self.update / 'sce_sys/param.sfo').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing sce_sys/param.sfo'):
            game_update.validate_game(self.base, self.update)

    def test_corrupt_update_sfo_rejected(self):
        write(self.update / 'sce_sys/param.sfo', b'corrupt update sfo')
        with self.assertRaisesRegex(ValueError, 'Invalid metadata'):
            game_update.validate_game(self.base, self.update)

    def test_update_missing_app_ver_rejected(self):
        write(self.update / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159'}))
        with self.assertRaisesRegex(ValueError, 'APP_VER'):
            game_update.validate_game(self.base, self.update)

    def test_nonexistent_folders_rejected(self):
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            game_update.validate_game(self.root / 'nonexistent')
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            game_update.validate_game(self.base, self.root / 'nonexistent_update')

    def test_same_and_nested_folders_rejected(self):
        with self.assertRaisesRegex(ValueError, 'separate folders'):
            game_update.validate_game(self.base, self.base)
        sub = self.base / 'nested'
        sub.mkdir()
        with self.assertRaisesRegex(ValueError, 'separate folders'):
            game_update.validate_game(self.base, sub)

    def test_case_insensitive_sfo_lookup(self):
        # Base with SCE_SYS/PARAM.SFO (uppercase)
        (self.base / 'sce_sys/param.sfo').unlink()
        (self.base / 'sce_sys').rmdir()
        write(self.base / 'SCE_SYS/PARAM.SFO', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.00'}))
        b_meta, _ = game_update.validate_game(self.base)
        self.assertEqual(b_meta.get('TITLE_ID'), 'CUSA01159')


class CleanupAndFailureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.base = self.root / 'base'
        self.update = self.root / 'update'
        self.out = self.root / 'out'
        write(self.base / 'eboot.bin', 'base')
        write(self.base / 'sce_sys/param.sfo', 'base sfo')
        write(self.update / 'eboot.bin', 'update')
        write(self.update / 'sce_sys/param.sfo', 'update sfo')

    def test_create_view_cleans_up_when_overlay_fails(self):
        with mock.patch('patches.game_title_id', return_value='CUSA01159'):
            with mock.patch('game_update.overlay', side_effect=RuntimeError('simulated overlay error')):
                with self.assertRaisesRegex(RuntimeError, 'simulated overlay error'):
                    game_update.create_view(self.base, self.update, self.out)
        # Verify no temporary directory left in out
        leftovers = list(self.out.iterdir()) if self.out.exists() else []
        self.assertEqual(leftovers, [])
        # Original dumps remain intact
        self.assertEqual((self.base / 'eboot.bin').read_text(), 'base')
        self.assertEqual((self.update / 'eboot.bin').read_text(), 'update')

    def test_remove_view_removes_read_only_files(self):
        with mock.patch('patches.game_title_id', return_value='CUSA01159'):
            view = game_update.create_view(self.base, self.update, self.out)
        read_only_file = view / 'test_ro.txt'
        write(read_only_file, 'ro')
        read_only_file.chmod(0o444)
        game_update.remove_view(view)
        self.assertFalse(view.exists())

    def test_cleanup_leftover_views_in_launcher(self):
        orphaned = self.out / 'game-update-leftover123'
        orphaned.mkdir(parents=True, exist_ok=True)
        write(orphaned / 'dummy.txt', 'junk')
        with mock.patch.object(basara4_launcher, 'OUT', self.out):
            launcher_mock = mock.MagicMock()
            basara4_launcher.Launcher._cleanup_leftover_views(launcher_mock)
        self.assertFalse(orphaned.exists())


class CacheInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.base = self.root / 'base'
        self.update = self.root / 'update'
        self.out = self.root / 'out'
        self.out.mkdir(parents=True, exist_ok=True)
        write(self.base / 'eboot.bin', 'base eboot')
        write(self.base / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.00', 'USER_DEFINED_PARAM_1': 1}))
        write(self.base / 'sce_module/libc.prx', 'base libc')
        write(self.base / 'sce_module/libSceFios2.prx', 'base fios2')

        write(self.update / 'eboot.bin', 'update eboot')
        write(self.update / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.02', 'USER_DEFINED_PARAM_1': 2}))

        # Create simulated outputs in out
        for name in ('boot-linked.bin', 'content.bin', 'eboot.elf', 'boot.bin'):
            write(self.out / name, 'output')

    def test_cache_invalidation_lifecycle(self):
        with mock.patch.object(basara4_launcher, 'OUT', self.out), \
             mock.patch.object(basara4_launcher, 'STAMP', self.out / 'prepared.json'):
            # 1. Base game without stamp is not ready
            self.assertFalse(basara4_launcher.image_ready(self.base))

            # 2. Base game stamp saved -> image is ready
            base_stamp = basara4_launcher.input_files_stamp(self.base)
            base_stamp['game'] = str(self.base)
            (self.out / 'prepared.json').write_text(json.dumps(base_stamp))
            self.assertTrue(basara4_launcher.image_ready(self.base))

            # 3. Create update overlay view: inputs differ from base stamp
            with mock.patch('patches.game_title_id', return_value='CUSA01159'):
                view = game_update.create_view(self.base, self.update, self.out / 'tmp')
            self.addCleanup(game_update.remove_view, view)

            # View has update eboot -> cache is invalidated!
            self.assertFalse(basara4_launcher.image_ready(view))

            # 4. Stamp updated for view -> image ready
            view_stamp = basara4_launcher.input_files_stamp(view)
            view_stamp['game'] = str(view)
            (self.out / 'prepared.json').write_text(json.dumps(view_stamp))
            self.assertTrue(basara4_launcher.image_ready(view))

            # 5. Base game checked against update stamp -> invalidated!
            self.assertFalse(basara4_launcher.image_ready(self.base))

            # 6. Missing output file -> invalidated!
            (self.out / 'boot-linked.bin').unlink()
            self.assertFalse(basara4_launcher.image_ready(view))


class LauncherAndPackageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_launcher_config_persistence_with_update_dir(self):
        config_file = self.root / 'user/launcher.json'
        with mock.patch.object(basara4_launcher, 'CONFIG', config_file), \
             mock.patch.object(basara4_launcher, 'USER', self.root / 'user'):
            # Default includes update_dir
            cfg = basara4_launcher.load_config()
            self.assertIn('update_dir', cfg)
            self.assertEqual(cfg['update_dir'], '')

            # Save with update_dir
            cfg['update_dir'] = 'D:/Games/update'
            basara4_launcher.save_config(cfg)
            loaded = basara4_launcher.load_config()
            self.assertEqual(loaded['update_dir'], 'D:/Games/update')

    def test_make_package_includes_runtime_scripts(self):
        pkg_dir = ROOT / 'packaging/sumeragi'
        if not pkg_dir.is_dir():
            pkg_dir = ROOT / 'packaging/basara4'
        sys.path.insert(0, str(pkg_dir))
        import make_package
        for script in ('game_update.py', 'mods.py', 'patches.py'):
            self.assertIn(script, make_package.PREPARE_SCRIPTS)
            self.assertTrue((ROOT / 'scripts' / script).is_file())

    def test_launcher_base_only_launch_flow(self):
        base = self.root / 'base'
        write(base / 'eboot.bin', b'\x7fELF base')
        write(base / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.00'}))

        launcher = mock.MagicMock()
        launcher.cfg = {'game': str(base), 'update_dir': '', 'fps_limit': 60}
        launcher.busy = False
        launcher.proc = None

        with mock.patch.object(basara4_launcher, 'image_ready', return_value=True):
            basara4_launcher.Launcher._prepare_then_launch(launcher, base, None, Path('dummy.exe'))
        error, effective_game, exe, patch_args, notice, view = launcher.pending
        self.assertIsNone(error)
        self.assertEqual(effective_game, base)
        self.assertIsNone(view)

    def test_launcher_update_overlay_launch_flow(self):
        base = self.root / 'base'
        update = self.root / 'update'
        out = self.root / 'out'
        write(base / 'eboot.bin', b'\x7fELF base')
        write(base / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.00'}))
        write(update / 'eboot.bin', b'\x7fELF update')
        write(update / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.02'}))

        launcher = mock.MagicMock()
        launcher.cfg = {'game': str(base), 'update_dir': str(update), 'fps_limit': 60}
        launcher.busy = False
        launcher.proc = None

        with mock.patch.object(basara4_launcher, 'OUT', out), \
             mock.patch.object(basara4_launcher, 'image_ready', return_value=True):
            basara4_launcher.Launcher._prepare_then_launch(launcher, base, update, Path('dummy.exe'))
            error, effective_game, exe, patch_args, notice, view = launcher.pending
            self.assertIsNone(error)
            self.assertIsNotNone(view)
            self.assertEqual(effective_game, view)
            self.assertTrue(view.exists())
            self.assertEqual((view / 'eboot.bin').read_bytes(), b'\x7fELF update')

            # Simulate game exiting -> clean up view
            launcher.update_view = view
            launcher.proc = mock.MagicMock()
            launcher.proc.poll.return_value = 0
            launcher.proc.returncode = 0
            launcher.play_now = False
            basara4_launcher.Launcher._poll(launcher)
            self.assertIsNone(launcher.update_view)
            self.assertFalse(view.exists())

    def test_launcher_failed_validation_never_starts_game(self):
        base = self.root / 'base'
        update = self.root / 'update'
        write(base / 'eboot.bin', b'\x7fELF base')
        write(base / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA01159', 'APP_VER': '01.00'}))
        write(update / 'eboot.bin', b'\x7fELF update')
        # Mismatched title ID in update
        write(update / 'sce_sys/param.sfo', make_sfo({'TITLE_ID': 'CUSA09999', 'APP_VER': '01.02'}))

        launcher = mock.MagicMock()
        launcher.cfg = {'game': str(base), 'update_dir': str(update)}
        launcher.busy = False
        launcher.proc = None

        with mock.patch('tkinter.messagebox.showerror') as showerror, \
             mock.patch('threading.Thread') as thread:
            basara4_launcher.Launcher.on_play(launcher)
            showerror.assert_called_once()
            self.assertIn('not the same title', showerror.call_args[0][1])
            thread.assert_not_called()
            self.assertFalse(launcher.busy)


if __name__ == '__main__':
    unittest.main()
