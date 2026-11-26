from paths import ROOT, built, built_env
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import content_profile

EXE=built('content-test')

class ProfileTests(unittest.TestCase):
    def test_sfo_parameters_and_explicit_trial_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'sce_sys').mkdir();(p/'sce_sys/param.sfo').write_bytes(b'fixture')
            with patch.object(content_profile,'sfo',return_value={'USER_DEFINED_PARAM_1':13,'USER_DEFINED_PARAM_4':0xffffffff}):
                content_profile.prepare(p,p,'trial')
            self.assertEqual(struct.unpack('<8s5I',(p/'content.bin').read_bytes()),(
                b'G3CONT01',1,13,0,0,0xffffffff))

    def test_extracted_addons_are_written_to_profile(self):
        label = 'DLCXBGMXXXXXX000'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / 'game'
            (game / 'sce_sys').mkdir(parents=True)
            (game / 'sce_sys' / 'param.sfo').write_bytes(b'fixture')
            dlc_root = root / 'dlc'
            dlc = dlc_root / label
            (dlc / 'sce_sys').mkdir(parents=True)
            (dlc / 'sce_sys' / 'param.sfo').write_bytes(b'fixture')
            base_values = {'TITLE_ID': 'CUSA01159', 'USER_DEFINED_PARAM_1': 13}
            addon_values = {
                'TITLE_ID': 'CUSA01159', 'CATEGORY': 'ac',
                'CONTENT_ID': f'JP0102-CUSA01159_00-{label}', 'TITLE': 'Test DLC',
            }

            def sfo_values(path):
                return addon_values if path.parent.parent == dlc else base_values

            with patch.object(content_profile, 'sfo', return_value=base_values), \
                    patch.object(content_profile, 'read_sfo', side_effect=sfo_values):
                content_profile.prepare(game, root / 'out', dlc_dir=dlc_root)
            blob = (root / 'out' / 'content.bin').read_bytes()
            self.assertEqual(len(blob), 28)
            self.assertEqual(struct.unpack('<8s5I', blob), (
                b'G3CONT01', 3, 13, 0, 0, 0))
            profile = (root / 'out' / 'content-profile.json').read_text(encoding='utf-8')
            self.assertIn(label, profile)

    def test_invalid_sfo_parameter_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'sce_sys').mkdir();(p/'sce_sys/param.sfo').write_bytes(b'fixture')
            with patch.object(content_profile,'sfo',return_value={'USER_DEFINED_PARAM_1':'13'}):
                with self.assertRaisesRegex(ValueError,'invalid user-defined'):
                    content_profile.prepare(p,p)

@unittest.skipUnless(EXE.exists(),'run bash build.sh --test first')
class ContentTests(unittest.TestCase):
    def run_case(self,*args):
        return subprocess.run([str(EXE.resolve()),*args],capture_output=True,text=True,timeout=5,env=built_env(EXE))

    def test_lifecycle_and_output_boundaries(self):
        r=self.run_case();self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_missing_profile_does_not_report_loaded(self):
        r=self.run_case('--missing');self.assertEqual(r.returncode,21)
        self.assertIn('needs --content-profile',r.stderr)

    def test_other_modules_are_counted_independently(self):
        r=self.run_case('--unknown');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
