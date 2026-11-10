"""Reproduce a populated-prefix overlap using real compiled PE32/PE64 DLLs."""
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wine_staging import verify_module_copy

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('i686-w64-mingw32-gcc') and shutil.which('x86_64-w64-mingw32-gcc'),
                     'Requires both MinGW architectures')
class WineStagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / 'sample.c'
        source.write_text('int sample(void) { return 42; }\n')
        self.images = {}
        for arch, compiler in (('i386-windows', 'i686-w64-mingw32-gcc'),
                               ('x86_64-windows', 'x86_64-w64-mingw32-gcc')):
            path = self.root / 'build/dlls/fixture' / arch / 'fixture.dll'
            path.parent.mkdir(parents=True)
            subprocess.run([compiler, '-shared', '-nostdlib', '-Wl,--entry,0',
                            str(source), '-o', str(path)], check=True, capture_output=True)
            self.images[arch] = path

    def test_identical_overlay_is_accepted_but_altered_or_wrong_arch_is_rejected(self):
        path = self.images['i386-windows']
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(verify_module_copy('i386-windows', 'fixture.dll', path,
                         data, 'prefix', digest)['sha256'], digest)
        with self.assertRaisesRegex(ValueError, 'configured Wine build'):
            verify_module_copy('i386-windows', 'fixture.dll', path, data + b'altered', 'prefix')
        with self.assertRaisesRegex(ValueError, 'provider manifest'):
            verify_module_copy('i386-windows', 'fixture.dll', path, data, 'provider', '0' * 64)
        with self.assertRaisesRegex(ValueError, 'wrong architecture'):
            verify_module_copy('i386-windows', 'fixture.dll', path,
                               self.images['x86_64-windows'].read_bytes(), 'prefix')
        with self.assertRaisesRegex(ValueError, 'not a PE'):
            verify_module_copy('i386-windows', 'fixture.dll', path, b'broken', 'prefix')

    def run_w261_section(self, excluded=False):
        archive = self.root / 'reports/increment15/prefix-package/prefix.tar.gz'
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, 'w:gz') as tar:
            for arch, windows in (('i386-windows', 'syswow64'), ('x86_64-windows', 'system32')):
                tar.add(self.images[arch], arcname='prefix/drive_c/windows/' + windows + '/fixture.dll')
                extra = self.root / 'build/dlls/avifil32' / arch / 'avifil32.dll'
                extra.parent.mkdir(parents=True)
                shutil.copyfile(self.images[arch], extra)
            data = b'WINE REGISTRY Version 2\n'
            member = tarfile.TarInfo('prefix/system.reg'); member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
        for stage in ('wine-pe64', 'wine-gui', 'wine-programs'):
            manifest = self.root / 'out' / stage / 'manifest.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'modules': {}}))
        out = self.root / 'out/wine-i386'; out.mkdir()
        tree = ast.parse((ROOT / 'tools/stage-wine-i386.py').read_text())
        helpers = [n for n in tree.body if
                   isinstance(n, ast.FunctionDef) and (n.name.startswith('w261_') or n.name in ('imports', 'locate', 'sha'))
                   or isinstance(n, ast.ClassDef) and n.name == 'W261Registrar']
        begin = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.With)
                     and 'w261_sealed' in ast.unparse(n))
        end = next(i for i in range(begin, len(tree.body)) if isinstance(tree.body[i], ast.If)
                   and ast.unparse(tree.body[i].test) == 'w261_problems')
        scope = dict(hashlib=hashlib, json=json, pathlib=__import__('pathlib'), re=re,
                     struct=struct, subprocess=subprocess, tarfile=tarfile,
                     verify_module_copy=verify_module_copy, ROOT=self.root, BUILD=self.root / 'build', out=out,
                     W261_I386=('fixture.dll',), W261_X64=('fixture.dll',),
                     W261_LEFT_OUT={'excluded': ('fixture.dll',)} if excluded else {},
                     W261_OTHERS={arch: set() for arch in self.images},
                     present=set(), present64=set(), staged={}, staged64={})
        exec(compile(ast.Module(body=helpers + tree.body[begin:end + 1], type_ignores=[]),
                     'stage-wine-i386.py:W261', 'exec'), scope)
        return scope

    def test_real_staging_loop_accepts_verified_prefix_overlaps(self):
        scope = self.run_w261_section()
        for arch in self.images:
            self.assertIn('fixture.dll', scope['w261'][arch])
            self.assertIn('fixture.dll', scope['w261_existing'][arch])

    def test_real_staging_loop_still_rejects_explicit_exclusions(self):
        with self.assertRaisesRegex(SystemExit, 'explicitly assigned elsewhere or left out'):
            self.run_w261_section(excluded=True)
