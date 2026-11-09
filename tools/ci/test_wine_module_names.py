"""Wine source aliases must not invent DLLs or hide unresolved dependencies."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wine_module_names import import_library_alias, register_alias, resolve_import_library, forwarded_modules, configured_pe_targets


class WineModuleNameTests(unittest.TestCase):
    def test_configured_pe_wrappers_are_not_filtered_by_legacy_extension(self):
        makefile = ('dlls/krnl386.exe16/i386-windows/krnl386.exe16: source\n'
                    'dlls/krnl386.exe16/i386-windows/atom.o: source\n'
                    'dlls/apisetschema/x86_64-windows/apisetschema.dll: source\n')
        targets = configured_pe_targets(makefile)
        self.assertIn(('i386', 'krnl386.exe16'), targets)
        self.assertIn(('x86_64', 'apisetschema.dll'), targets)
        self.assertEqual(len(targets), 2)

    def test_importlib_maps_to_actual_driver_for_both_architectures(self):
        aliases = {}
        definition = 'MODULE = winspool.drv\nIMPORTLIB = winspool\n'
        for arch in ('i386', 'x86_64'):
            register_alias(aliases, arch, import_library_alias(definition), 'winspool.drv')
            self.assertEqual(resolve_import_library('winspool', arch, aliases), 'winspool.drv')
            self.assertEqual(resolve_import_library('winspool.drv', arch, aliases), 'winspool.drv')

    def test_missing_dependency_is_still_returned_for_closure_rejection(self):
        self.assertEqual(resolve_import_library('missing', 'i386', {}), 'missing.dll')
        self.assertEqual(resolve_import_library('ole32', 'x86_64', {}), 'ole32.dll')

    def test_alias_is_architecture_specific_and_case_insensitive(self):
        aliases = {}
        register_alias(aliases, 'x86_64', 'Driver', 'Driver.drv')
        self.assertEqual(resolve_import_library('DRIVER', 'x86_64', aliases), 'driver.drv')
        self.assertEqual(resolve_import_library('driver', 'i386', aliases), 'driver.dll')

    def test_ambiguous_and_unexpanded_names_fail(self):
        aliases = {}
        register_alias(aliases, 'i386', 'driver', 'first.drv')
        with self.assertRaises(ValueError):
            register_alias(aliases, 'i386', 'driver', 'second.dll')
        with self.assertRaises(ValueError):
            resolve_import_library('$(DRIVER)', 'i386', aliases)

    def test_empty_importlib_does_not_consume_the_following_line(self):
        self.assertIsNone(import_library_alias('IMPORTLIB =\nIMPORTS = user32\n'))
        self.assertIsNone(import_library_alias('IMPORTLIB = # disabled\nMODULE = test.dll\n'))


@unittest.skipUnless(all(shutil.which(name) for name in ('i686-w64-mingw32-gcc', 'x86_64-w64-mingw32-gcc')),
                     'Real PE forwarder fixtures require both MinGW compilers')
class ForwardedModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        (cls.root / 'forward.def').write_text('LIBRARY fixture\nEXPORTS\n Forwarded=cryptbase.SystemFunction036\n')
        (cls.root / 'normal.c').write_text('__declspec(dllexport) int normal(void) { return 7; }\n')
        for compiler in ('i686-w64-mingw32-gcc', 'x86_64-w64-mingw32-gcc'):
            for source in ('forward.def', 'normal.c'):
                result = subprocess.run([compiler, '-shared', '-nostdlib', '-Wl,--entry,0',
                                         str(cls.root / source), '-o', str(cls.root / (compiler + source + '.dll'))],
                                        capture_output=True, text=True)
                if result.returncode:
                    raise AssertionError(result.stdout + result.stderr)

    def test_real_pe32_and_pe64_forwarders_add_the_provider(self):
        for compiler in ('i686-w64-mingw32-gcc', 'x86_64-w64-mingw32-gcc'):
            with self.subTest(compiler=compiler):
                self.assertEqual(forwarded_modules(self.root / (compiler + 'forward.def.dll')), ['cryptbase'])

    def test_real_code_exports_do_not_add_a_false_provider(self):
        for compiler in ('i686-w64-mingw32-gcc', 'x86_64-w64-mingw32-gcc'):
            with self.subTest(compiler=compiler):
                self.assertEqual(forwarded_modules(self.root / (compiler + 'normal.c.dll')), [])

    def test_truncated_pe_is_rejected(self):
        path = self.root / 'truncated.dll'
        path.write_bytes(b'MZ')
        with self.assertRaises(ValueError):
            forwarded_modules(path)
