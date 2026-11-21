"""The PR matrix scope: installer/docs-only changes skip it, anything else runs it."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pr_scope', Path(__file__).with_name('pr_scope.py'))
pr_scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr_scope)


class PrScopeTests(unittest.TestCase):
    def needed(self, *paths):
        return pr_scope.needs_matrix(list(paths))[0]

    def test_installer_and_docs_skip(self):
        self.assertFalse(self.needed('native/hw_install.h', 'tools/upload-hardware.py',
                                     'docs/POP_SEPARATE_PROCESS.md', 'docs/POP_SEPARATE_PROCESS-es.md'))

    def test_matrix_inputs_run(self):
        for path in ('native/probe.c', 'platform/ps4/pw_wine_platform.c', 'fixtures/win32/files.c',
                     'patches/shadPS4/0001-x.patch', 'tools/build.py', 'tools/ci/run-matrix.py',
                     '.github/workflows/ci-pr.yml', 'dependencies.lock.json', 'native/hw_text.h'):
            with self.subTest(path=path):
                self.assertTrue(self.needed('native/hw_install.h', path))

    def test_empty_diff_runs(self):
        self.assertTrue(self.needed())
        self.assertTrue(self.needed('', '  '))


if __name__ == '__main__':
    unittest.main()
