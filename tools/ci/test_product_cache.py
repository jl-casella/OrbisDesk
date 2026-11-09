"""Filesystem/cache control tests only; no fabricated product build acceptance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import product_cache as cache


@unittest.skipUnless(os.name == 'posix', 'Product snapshots preserve POSIX build metadata')
class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.bundle = self.root / 'bundle'
        self.key = {'key': 'test-inputs', 'inputs': {'compiler': 'test'}}
        self.output = self.root / 'output'
        self.addCleanup(patch.stopall)
        patch.object(cache, 'revision', return_value='producer').start()
        patch.dict(os.environ, {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}).start()

    def seal(self):
        return cache.seal(self.bundle, self.key, {'tree': self.source}, [self.source])

    def test_roundtrip_preserves_files_links_modes_and_mtimes(self):
        file = self.source / 'compiler'
        file.write_bytes(b'actual test input')
        file.chmod(0o755)
        os.utime(file, (1000000000, 1000000000))
        (self.source / 'alias').symlink_to('compiler')
        self.seal()
        cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertEqual((self.output / 'alias').read_bytes(), file.read_bytes())
        self.assertTrue((self.output / 'alias').is_symlink())
        self.assertEqual((self.output / 'compiler').stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.output / 'compiler').stat().st_mtime_ns, file.stat().st_mtime_ns)

    def test_low_space_refuses_snapshot_creation_and_extraction(self):
        from types import SimpleNamespace
        (self.source / 'input').write_bytes(b'input')
        with patch.object(cache.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(OSError, 'Insufficient disk'):
                self.seal()
        self.assertFalse((self.bundle / 'payload.tar.gz').exists())
        self.seal()
        with patch.object(cache.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024)):
            with self.assertRaisesRegex(OSError, 'Insufficient disk'):
                cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertFalse(self.output.exists())

    def test_corrupted_payload_and_changed_inputs_are_rejected(self):
        (self.source / 'file').write_text('content')
        self.seal()
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, {'key': 'changed'}, {'tree': self.output}, [self.output])
        with (self.bundle / 'payload.tar.gz').open('ab') as stream:
            stream.write(b'altered')
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertFalse(self.output.exists())

    def test_cache_bundle_itself_cannot_be_a_symlink(self):
        (self.source / 'file').write_text('content')
        self.seal()
        alias = self.root / 'linked-bundle'
        alias.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(ValueError):
            cache.restore(alias, self.key, {'tree': self.output}, [self.output])

    def test_file_hash_is_checked_before_any_live_output_is_written(self):
        (self.source / 'a').write_text('first')
        (self.source / 'b').write_text('second')
        manifest = self.seal()
        manifest['entries']['tree/b']['sha256'] = '0' * 64
        cache.write_json(self.bundle / 'manifest.json', manifest)
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertFalse(self.output.exists())

    def test_existing_outputs_are_not_overwritten(self):
        (self.source / 'file').write_text('cached')
        self.seal()
        self.output.mkdir()
        (self.output / 'file').write_text('existing')
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertEqual((self.output / 'file').read_text(), 'existing')

    def test_external_source_symlink_is_not_sealed(self):
        (self.source / 'escape').symlink_to(self.root / 'private')
        with self.assertRaises(ValueError):
            self.seal()

    def test_pinned_sdk_link_is_preserved_without_copying_its_contents(self):
        sdk = self.root / 'sdk'
        sdk.mkdir()
        (sdk / 'header').write_text('pinned SDK fixture')
        (self.source / 'header').symlink_to(sdk / 'header')
        manifest = cache.seal(self.bundle, self.key, {'tree': self.source}, [self.source, sdk])
        self.assertEqual(manifest['entries']['tree/header']['kind'], 'symlink')
        cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output, sdk])
        self.assertTrue((self.output / 'header').is_symlink())
        self.assertEqual((self.output / 'header').read_text(), 'pinned SDK fixture')

    def test_manifest_paths_and_linked_ancestors_cannot_escape(self):
        (self.source / 'file').write_text('content')
        manifest = self.seal()
        manifest['entries']['tree/../escape'] = {'kind': 'directory'}
        cache.write_json(self.bundle / 'manifest.json', manifest)
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        del manifest['entries']['tree/../escape']
        manifest['entries']['tree/link'] = {'kind': 'symlink', 'target': '../private'}
        cache.write_json(self.bundle / 'manifest.json', manifest)
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        del manifest['entries']['tree/link']
        cache.write_json(self.bundle / 'manifest.json', manifest)
        real = self.root / 'real'
        real.mkdir()
        self.output.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertEqual(list(real.iterdir()), [])

    def test_archive_links_are_rejected_even_with_matching_payload_hash(self):
        (self.source / 'file').write_text('content')
        manifest = self.seal()
        with tarfile.open(self.bundle / 'payload.tar.gz', 'w:gz') as archive:
            link = tarfile.TarInfo('tree/file')
            link.type = tarfile.SYMTYPE
            link.linkname = '/tmp/escape'
            archive.addfile(link)
        manifest['payload_sha256'] = cache.sha(self.bundle / 'payload.tar.gz')
        cache.write_json(self.bundle / 'manifest.json', manifest)
        with self.assertRaises(ValueError):
            cache.restore(self.bundle, self.key, {'tree': self.output}, [self.output])
        self.assertFalse(self.output.exists())

    def test_graphics_excludes_private_and_regenerated_inputs(self):
        for name in ('vk/mesa-venv/bin/python', 'vk/private-notes/note', 'vk/src/mesa/.git/config',
                     'vk/src/llvm-project-21.1.6.src/CMakeLists.txt', 'vk/src/Vulkan-Headers/.git/HEAD'):
            self.assertTrue(cache.excluded_graphics(name), name)
        for name in ('vk', 'vk/build/mesa-wine/lib.a', 'vk/src/mesa/header.h', 'vk/sysroot/include/header.h'):
            self.assertFalse(cache.excluded_graphics(name), name)

    def test_completed_block_remains_saveable_after_later_failure(self):
        (self.source / 'file').write_text('content')
        base = self.root / 'caches'
        self.bundle = base / 'graphics'
        self.seal()
        keys = self.root / 'inputs.json'
        cache.write_json(keys, {'graphics': self.key})
        emitted = {}
        with patch.object(cache, 'BASE', base), patch.object(cache, 'INPUTS', keys), \
                patch.object(cache, 'DOWNLOADS', self.root / 'downloads'), \
                patch.object(cache, 'DOWNLOAD_STATUS', self.root / 'downloads-status.json'), \
                patch.object(cache, 'download_specs', return_value={}), \
                patch.object(cache, 'output', side_effect=lambda name, value: emitted.update({name: value})):
            cache.ready()
        self.assertTrue(emitted['graphics_ready'])
        self.assertFalse(emitted['wine_ready'])

    def test_cold_mode_does_not_restore_snapshot_candidates(self):
        with patch.object(cache, 'make_keys', return_value={'graphics': self.key}), \
                patch.object(cache, 'STATUS', self.root / 'status.json'), \
                patch.object(cache, 'BASE', self.root), patch.object(cache, 'restore') as restore:
            (self.root / 'graphics').mkdir()
            controller = cache.ProductCache('cold')
            self.assertFalse(controller.use('graphics'))
        restore.assert_not_called()


@unittest.skipUnless(os.name == 'posix', 'Product fingerprints use the Linux toolchain')
class KeyTests(unittest.TestCase):
    def test_wine_recipe_changes_do_not_invalidate_graphics(self):
        real = cache.ROOT
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('dependencies.lock.json', 'artifacts.lock.json', 'sources.lock.json',
                         'product-assets.lock.json', 'fork.lock.json'):
                shutil.copyfile(real / name, root / name)
            names = ['tools/ci/product_cache.py', 'tools/ci/build-product.py', 'tools/ci/install-product.sh',
                     'tools/ci/install-runner.sh', 'tools/ci/common.py', 'tools/logged_process.py',
                     'tools/restore-dependencies.py', 'tools/ci/runner_disk.py',
                     'tools/build-wine.py', 'tools/build-host-wine-closure.py',
                     'tools/build-host-wine-unix.py', 'tools/wine_module_names.py', 'tools/vk-h0/patch.py',
                     'tools/wine_product_seeds.py', 'tools/stage-wine-i386.py',
                     'tools/stage-wine-programs.py', 'tools/stage-wine-extras.py',
                     'tools/stage-mshtml-hw.py', 'tools/stage-dshow-i386.py',
                     'native/wine_hardware.c', 'platform/ps4/pw_telemetry.h',
                     '.deps/linux-tools/cmake/data/bin/cmake', '.deps/linux-tools/bin/ninja', 'fake-compiler']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('input')
            def check_output(command, **kwargs):
                if command[0] == 'dpkg-query':
                    return 'compiler=1\n'
                if 'ls-files' in command:
                    return 'tools/vk-h0/patch.py\nnative/wine_hardware.c\nplatform/ps4/pw_telemetry.h\n'
                return 'compiler-version'
            with patch.object(cache, 'ROOT', root), patch.object(cache, 'INPUTS', root / 'inputs.json'), \
                    patch.object(cache, 'output'), patch.object(cache.shutil, 'which', return_value=str(root / 'fake-compiler')), \
                    patch.object(cache.subprocess, 'check_output', side_effect=check_output):
                original = cache.make_keys()
                (root / 'tools/build-host-wine-unix.py').write_text('changed Wine recipe')
                changed = cache.make_keys()
                self.assertNotEqual(original['wine']['key'], changed['wine']['key'])
                self.assertEqual(original['graphics']['key'], changed['graphics']['key'])
                (root / 'tools/stage-wine-i386.py').write_text('changed required staging modules')
                declarations_changed = cache.make_keys()
                self.assertNotEqual(changed['wine']['key'], declarations_changed['wine']['key'])
                self.assertEqual(changed['graphics']['key'], declarations_changed['graphics']['key'])
                changed = declarations_changed
                (root / 'tools/vk-h0/patch.py').write_text('changed graphics recipe')
                graphics_changed = cache.make_keys()
                self.assertNotEqual(changed['graphics']['key'], graphics_changed['graphics']['key'])
                self.assertEqual(changed['wine']['key'], graphics_changed['wine']['key'])
                # launcher sources are later steps' inputs; the telemetry header is read by a graphics patch
                (root / 'native/wine_hardware.c').write_text('changed launcher')
                launcher_changed = cache.make_keys()
                self.assertEqual(graphics_changed['graphics']['key'], launcher_changed['graphics']['key'])
                (root / 'platform/ps4/pw_telemetry.h').write_text('changed telemetry schema')
                telemetry_changed = cache.make_keys()
                self.assertNotEqual(launcher_changed['graphics']['key'], telemetry_changed['graphics']['key'])


class DownloadTests(unittest.TestCase):
    def test_verified_download_is_reused_and_tampering_rejected(self):
        import hashlib
        import bootstrap
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloads = root / 'downloads'
            downloads.mkdir()
            digest = hashlib.sha256(b'archive').hexdigest()
            (downloads / digest).write_bytes(b'archive')
            spec = {'sha256': digest}
            def verified_download(spec, name):
                path = root / '.deps/downloads/ci' / name
                self.assertEqual(cache.sha(path), spec['sha256'])
                return path
            with patch.object(cache, 'ROOT', root), patch.object(cache, 'DOWNLOADS', downloads), \
                    patch.object(cache, 'DOWNLOAD_STATUS', root / 'download-status.json'), \
                    patch.object(bootstrap, 'download', side_effect=verified_download) as download:
                cache.product_download(spec, 'sdk.tar.gz')
                self.assertTrue(json.loads((root / 'download-status.json').read_text())['files'][digest]['reused'])
                (downloads / digest).write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    cache.product_download(spec, 'sdk.tar.gz')
                self.assertEqual(download.call_count, 1)


@unittest.skipUnless(os.name == 'posix', 'Native source mtimes are normalized on Linux')
class SourceTimeTests(unittest.TestCase):
    def test_only_clean_pinned_sources_are_normalized_without_touching_git_head(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / '.deps/wine/source'
            source.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            file = source / 'header.h'
            file.write_text('pinned source')
            subprocess.run(['git', '-C', str(source), 'add', 'header.h'], check=True)
            subprocess.run(['git', '-C', str(source), '-c', 'user.name=Cache test',
                            '-c', 'user.email=cache-test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
            commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            cache.write_json(root / 'sources.lock.json', {'sources': {'wine': {'commit': commit}}})
            head_mtime = (source / '.git/HEAD').stat().st_mtime_ns
            with patch.object(cache, 'ROOT', root):
                cache.normalize_wine_source()
                self.assertEqual(file.stat().st_mtime, 1000000000)
                self.assertEqual((source / '.git/HEAD').stat().st_mtime_ns, head_mtime)
                file.write_text('dirty source')
                with self.assertRaises(ValueError):
                    cache.normalize_wine_source()


if __name__ == '__main__':
    unittest.main()
