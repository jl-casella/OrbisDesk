"""Prebuilt release blocks: lock/key matching, hash rejection and restoring the Wine block's prefix.

No network: the release download is replaced by a copy from a local "release" directory holding
assets made by the real seal and split functions.
"""
import contextlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import prebuilt
import product_cache as cache

KEY = 'a' * 64


@unittest.skipUnless(os.name == 'posix', 'Product snapshots preserve POSIX build metadata')
class PrebuiltTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(cache, 'revision', return_value='producer').start()
        patch.dict(os.environ, {'GITHUB_RUN_ID': '77', 'GITHUB_RUN_ATTEMPT': '1'}).start()
        self.key = {'key': KEY, 'inputs': {'block': 'wine', 'compiler': 'test'}}
        self.release = self.root / 'release'
        self.release.mkdir()
        self.downloads = []
        patch.object(prebuilt, 'download_asset', side_effect=self.download).start()

    def download(self, repository, tag, name, directory):
        self.downloads.append(name)
        shutil.copyfile(self.release / name, directory / name)
        return directory / name

    def wine_tree(self):
        """A small stand-in for the Wine block mounts, including the sealed prefix package."""
        source = self.root / 'source'
        mounts = {'runtime': source / 'runtime', 'pe': source / 'pe', 'closure': source / 'closure',
                  'prefix-package': source / 'prefix-package'}
        for path in mounts.values():
            path.mkdir(parents=True)
        (mounts['runtime'] / 'wineserver').write_bytes(b'\x7fELF server')
        (mounts['runtime'] / 'wineserver').chmod(0o755)
        (mounts['pe'] / 'kernel32.dll').write_bytes(b'MZ kernel32')
        (mounts['closure'] / 'tree-report.json').write_text('{"status": "passed"}')
        (mounts['prefix-package'] / 'prefix.tar.gz').write_bytes(b'sealed prefix archive')
        (mounts['prefix-package'] / 'manifest.json').write_text('{"status": "packaged-for-preflight"}')
        return mounts

    def publish_locally(self, mounts, part_bytes=10):
        """Seal, split and pin like `prebuilt.py publish`, without GitHub."""
        bundle = self.root / 'sealed'
        manifest = cache.seal(bundle, self.key, mounts, list(mounts.values()))
        stem = 'wine-' + KEY[:16]
        shutil.copyfile(bundle / 'manifest.json', self.release / (stem + '.manifest.json'))
        with patch.object(prebuilt, 'PART_BYTES', part_bytes):
            parts = prebuilt.split_payload(bundle / 'payload.tar.gz', self.release, stem)
        entry = {'key': KEY, 'repository': 'owner/repo', 'tag': 'prebuilt-' + stem + '-77',
                 'producer_sha': 'producer', 'run_id': '77',
                 'manifest': {'name': stem + '.manifest.json', 'sha256': cache.sha(bundle / 'manifest.json'),
                              'size': (bundle / 'manifest.json').stat().st_size},
                 'payload': {'sha256': manifest['payload_sha256'], 'size': sum(p['size'] for p in parts),
                             'parts': parts}}
        lock = self.root / 'prebuilt-blocks.lock.json'
        cache.write_json(lock, {'schema_version': 1, 'blocks': {'wine': prebuilt.validate_entry('wine', entry)}})
        return lock, entry

    def test_matching_key_restores_the_block_with_its_prefix_package(self):
        mounts = self.wine_tree()
        lock, entry = self.publish_locally(mounts)
        self.assertGreater(len(entry['payload']['parts']), 1, 'the payload must be split to test joining')
        bundle = self.root / 'cache/wine'
        status = prebuilt.fetch('wine', self.key, bundle, lock)
        self.assertTrue(status['fetched'], status)
        output = {name: self.root / 'restored' / name for name in mounts}
        cache.restore(bundle, self.key, output, list(output.values()))
        for name in ('prefix.tar.gz', 'manifest.json'):
            self.assertEqual((output['prefix-package'] / name).read_bytes(),
                             (mounts['prefix-package'] / name).read_bytes())
        self.assertEqual((output['runtime'] / 'wineserver').stat().st_mode & 0o777, 0o755)

    def test_key_mismatch_never_downloads_a_stale_asset(self):
        lock, _ = self.publish_locally(self.wine_tree())
        changed = {'key': 'b' * 64, 'inputs': {'block': 'wine', 'compiler': 'newer'}}
        status = prebuilt.fetch('wine', changed, self.root / 'cache/wine', lock)
        self.assertFalse(status['fetched'])
        self.assertEqual(status['reason'], 'key mismatch')
        self.assertEqual(self.downloads, [])
        self.assertFalse((self.root / 'cache/wine').exists())

    def test_missing_entry_or_lock_builds_instead(self):
        status = prebuilt.fetch('graphics', self.key, self.root / 'cache/graphics', self.root / 'absent.json')
        self.assertEqual((status['fetched'], status['reason']), (False, 'no lock entry'))

    def test_altered_part_is_rejected_without_leaving_a_bundle(self):
        lock, entry = self.publish_locally(self.wine_tree())
        part = self.release / entry['payload']['parts'][1]['name']
        data = bytearray(part.read_bytes())
        data[0] ^= 0xff
        part.write_bytes(bytes(data))
        status = prebuilt.fetch('wine', self.key, self.root / 'cache/wine', lock)
        self.assertFalse(status['fetched'])
        self.assertIn('hash or size differs', status['reason'])
        self.assertFalse((self.root / 'cache/wine').exists())
        self.assertEqual(list((self.root / 'cache').iterdir()), [])

    def test_locked_manifest_with_other_inputs_is_rejected(self):
        # The lock pins the bytes, but the sealed manifest must also carry this run's exact inputs.
        lock, _ = self.publish_locally(self.wine_tree())
        other = {'key': KEY, 'inputs': {'block': 'wine', 'compiler': 'other'}}
        status = prebuilt.fetch('wine', other, self.root / 'cache/wine', lock)
        self.assertFalse(status['fetched'])
        self.assertIn('inputs differ', status['reason'])
        self.assertFalse((self.root / 'cache/wine').exists())

    def test_lock_rejects_malformed_entries_and_merge_validates(self):
        lock, entry = self.publish_locally(self.wine_tree())
        for field, value in (('key', 'short'), ('tag', 'prebuilt-wine-other-77'), ('repository', 'no slash')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                prebuilt.validate_entry('wine', dict(entry, **{field: value}))
        broken = json.loads(json.dumps(entry))
        broken['payload']['parts'].reverse()
        with self.assertRaises(ValueError):
            prebuilt.validate_entry('wine', broken)
        status = prebuilt.fetch('wine', self.key, self.root / 'cache/wine',
                                self._write(self.root / 'bad.json', {'schema_version': 1, 'blocks': {'wine': broken}}))
        self.assertIn('invalid lock', status['reason'])
        fragment = self._write(self.root / 'fragment.json', {'wine': entry})
        target = self._write(self.root / 'merged.json', {'schema_version': 1, 'blocks': {}})
        self.assertEqual(prebuilt.merge([fragment], target)['blocks']['wine'], entry)
        self._write(fragment, {'wine': broken})
        with self.assertRaises(ValueError):
            prebuilt.merge([fragment], target)

    def _write(self, path, data):
        cache.write_json(path, data)
        return path

    def test_product_cache_uses_prebuilt_only_on_actions_cache_miss_in_reuse_mode(self):
        mounts = self.wine_tree()
        lock, _ = self.publish_locally(mounts)
        output = {name: self.root / 'workspace' / name for name in mounts}
        with patch.object(cache, 'make_keys', return_value={'wine': self.key}), \
                patch.object(cache, 'STATUS', self.root / 'status.json'), \
                patch.object(cache, 'BASE', self.root / 'product-cache'), \
                patch.object(cache, 'mounts', return_value=output), \
                patch.object(cache, 'allowed_links', return_value=list(output.values())), \
                patch.object(cache, 'validate_outputs') as validate, \
                patch.object(cache, 'phase', return_value=contextlib.nullcontext()), \
                patch.object(prebuilt, 'LOCK', lock):
            self.assertFalse(cache.ProductCache('cold').use('wine'))
            self.assertEqual(self.downloads, [])
            controller = cache.ProductCache('reuse')
            self.assertTrue(controller.use('wine'))
        validate.assert_called_once_with('wine')
        self.assertEqual(controller.status['blocks']['wine']['source'], 'prebuilt-release')
        self.assertEqual((output['prefix-package'] / 'prefix.tar.gz').read_bytes(), b'sealed prefix archive')


@unittest.skipUnless(os.name == 'posix', 'Wine block validation reads POSIX permissions')
class WineBlockValidationTests(unittest.TestCase):
    def test_prefix_with_another_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / '.deps/wine/runtime/build'
            for name in ('loader/wine', 'loader/wine-preloader', 'server/wineserver'):
                (build / name).parent.mkdir(parents=True, exist_ok=True)
                (build / name).write_bytes(b'\x7fELF')
                (build / name).chmod(0o755)
            (build / 'loader/wine.inf').write_text('inf')
            for name in ('out/wine/wine-runtime-manifest.json', 'out/wine-build.json',
                         'reports/increment15/host-build/unix-report.json'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text('{}')
            cache.write_json(root / 'sources.lock.json', {'sources': {'wine': {'commit': 'c' * 40}}})
            report = {'status': 'passed', 'unknown_imports': [], 'wine_commit': 'c' * 40}
            cache.write_json(root / 'reports/increment15/host-build/report.json', report)
            tree = {'status': 'passed', 'unexpected_failures': [], 'wine_commit': 'c' * 40}
            cache.write_json(root / 'reports/increment15/host-build/tree-report.json', tree)
            (root / 'out/console32-bare.exe').write_bytes(b'MZ fixture of this build')
            import wine_prefix
            with patch.object(cache, 'ROOT', root), \
                    patch.object(wine_prefix, 'validate_package', return_value={'exe_sha256': cache.sha(
                        root / 'out/console32-bare.exe')}):
                cache.validate_outputs('wine')
            with patch.object(cache, 'ROOT', root), \
                    patch.object(wine_prefix, 'validate_package', return_value={'exe_sha256': '0' * 64}):
                with self.assertRaisesRegex(ValueError, 'different console fixture'):
                    cache.validate_outputs('wine')
            cache.write_json(root / 'reports/increment15/host-build/tree-report.json',
                             dict(tree, status='failed', unexpected_failures=['dlls/user32/user32.dll']))
            with patch.object(cache, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'complete pinned host tree'):
                    cache.validate_outputs('wine')


class TreeFailureTests(unittest.TestCase):
    def test_only_the_wineusb_unix_side_may_fail(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'tree', Path(__file__).resolve().parents[1] / 'build-host-wine-tree.py')
        tree = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tree)
        allowed = 'make: *** [Makefile:401234: dlls/wineusb.sys/unixlib.o] Error 1\n'
        self.assertTrue(tree.classify(allowed, 2)['passed'])
        self.assertTrue(tree.classify('', 0)['passed'])
        self.assertFalse(tree.classify('', 2)['passed'], 'a failed make needs a known failed target')
        pe = 'make: *** [Makefile:9: dlls/wineusb.sys/x86_64-windows/wineusb.sys] Error 1\n'
        self.assertEqual(tree.classify(allowed + pe, 2)['unexpected_failures'],
                         ['dlls/wineusb.sys/x86_64-windows/wineusb.sys'])
        other = 'make: *** [Makefile:12: dlls/atl/x86_64-windows/atl.dll] Error 1\n'
        self.assertFalse(tree.classify(other, 2)['passed'])


if __name__ == '__main__':
    unittest.main()
