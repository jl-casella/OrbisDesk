"""Focused checks for the product rename and non-destructive settings import."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from project_brand import NAME, package_build, state_root


class ProductIdentity(unittest.TestCase):
    def test_old_and_new_packages_are_recognized_for_cleanup(self):
        self.assertEqual(package_build('orbisdesk-W283-0123456789ab.pkg'), 283)
        self.assertEqual(package_build('orbis-win-W282-0123456789ab.pkg'), 282)
        for name in ('../orbisdesk-W282-0123456789ab.pkg', 'other.pkg',
                     'orbisdesk-W283-0123456789ab.pkg.bak'):
            self.assertIsNone(package_build(name))

    def test_historical_collection_keeps_the_old_location(self):
        self.assertEqual(NAME, 'OrbisDesk')
        self.assertEqual(state_root('W282'), '/data/orbis-win')
        self.assertEqual(state_root('W283'), '/data/orbisdesk')

    def test_settings_import_is_once_only_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = pathlib.Path(directory)
            old, new = temp / 'legacy', temp / 'new'
            old.mkdir()
            new.mkdir()
            (old / 'launch.txt').write_text('original game')
            (old / 'boot-mode.txt').write_text('root')
            (new / 'boot-mode.txt').write_text('normal')
            source = temp / 'check.c'
            source.write_text('#include "pw_brand.h"\nint main(void) { return pw_brand_prepare_state() ? 1 : 0; }\n')
            executable = temp / 'check'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I' + str(ROOT / 'platform/ps4'),
                            '-DPW_STATE_ROOT="' + str(new) + '"',
                            '-DPW_LEGACY_STATE_ROOT="' + str(old) + '"',
                            str(source), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)
            self.assertEqual((new / 'launch.txt').read_text(), 'original game')
            self.assertEqual((new / 'boot-mode.txt').read_text(), 'normal')
            self.assertEqual((old / 'launch.txt').read_text(), 'original game')
            # A consumed launch request must never be reimported on another boot.
            (new / 'launch.txt').unlink()
            subprocess.run([str(executable)], check=True)
            self.assertFalse((new / 'launch.txt').exists())
            self.assertTrue((new / '.brand-migrated-v1').exists())


if __name__ == '__main__':
    unittest.main()
