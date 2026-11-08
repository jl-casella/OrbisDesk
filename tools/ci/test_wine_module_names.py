"""Wine source aliases must not invent DLLs or hide unresolved dependencies."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wine_module_names import import_library_alias, register_alias, resolve_import_library


class WineModuleNameTests(unittest.TestCase):
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
