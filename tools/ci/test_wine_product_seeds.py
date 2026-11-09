"""Product producers must cover staging inputs without executing the stagers."""
import ast
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wine_product_seeds import declaration, product_seeds

ROOT = Path(__file__).resolve().parents[2]


class ProductSeedTests(unittest.TestCase):
    def test_declarations_are_read_without_executing_module(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stager.py'
            path.write_text("raise RuntimeError('must not execute')\nA=('a.dll',)\nB={'i386': A+('b.dll',)}\n")
            self.assertEqual(declaration(path, 'B'), {'i386': ('a.dll', 'b.dll')})
            path.write_text("A=__import__('os').getcwd()\n")
            with self.assertRaises(ValueError):
                declaration(path, 'A')

    def test_product_covers_every_declared_w261_module_and_resources(self):
        modules, resources = product_seeds(ROOT)
        for arch, name in (('i386', 'ddraw.dll'), ('i386', 'winevulkan.dll'),
                           ('x86_64', 'notepad.exe'), ('x86_64', 'joy.cpl'),
                           ('i386', 'quartz.dll'), ('x86_64', 'mshtml.dll')):
            self.assertIn((arch, name), modules)
        for arch, field in (('i386', 'W261_I386'), ('x86_64', 'W261_X64')):
            for name in declaration(ROOT / 'tools/stage-wine-i386.py', field):
                self.assertIn((arch, name), modules)
        self.assertIn('dlls/mshtml.tlb/i386-windows/mshtml.tlb', resources)
        self.assertIn('libs/strmbase/i386-windows/libstrmbase.a', resources)
        self.assertIn('dlls/aero.msstyles/x86_64-windows/aero.msstyles', resources)

    def test_manifest_producers_precede_staging_consumers(self):
        tree = ast.parse((ROOT / 'tools/ci/build-product.py').read_text())
        sequence = next(ast.literal_eval(node.iter) for node in ast.walk(tree)
                        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple)
                        and isinstance(node.iter.elts[0], ast.Constant)
                        and node.iter.elts[0].value == 'stage-wine-pe64')
        for producer, consumer in (('stage-wine-programs', 'stage-wine-i386'),
                                   ('build-bcrypt-x64', 'stage-mshtml-hw'),
                                   ('build-dmsynth-i386', 'stage-dshow-i386')):
            self.assertLess(sequence.index(producer), sequence.index(consumer))
            self.assertEqual(sequence.count(producer), 1)
