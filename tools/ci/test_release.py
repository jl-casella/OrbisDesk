"""Verify rejection of stale, altered and escaping release inputs."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('product_release', Path(__file__).with_name('release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'OrbisDesk.pkg').write_bytes(b'\x7fCNTtest-only')
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime/file').write_bytes(b'fresh')
        (self.root / 'source.c').write_text('source')
        self.product = {'package': 'OrbisDesk.pkg', 'package_sha256': release.sha(self.root / 'OrbisDesk.pkg'),
            'runtime_root': 'runtime', 'runtime_files': {'file': {'sha256': release.sha(self.root / 'runtime/file'), 'bytes': 5}},
            'source_hashes': {'source.c': release.sha(self.root / 'source.c')},
            'title_id': 'ORBW00002', 'product': {'name': 'OrbisDesk'}}

    def test_package_and_runtime_must_be_the_verified_inputs(self):
        release.verify_product(self.root, self.product)
        (self.root / 'runtime/file').write_bytes(b'altered')
        with self.assertRaises(ValueError):
            release.verify_product(self.root, self.product)

    def test_stale_source_and_extra_runtime_are_rejected(self):
        (self.root / 'source.c').write_text('new source')
        with self.assertRaises(ValueError):
            release.verify_product(self.root, self.product)
        (self.root / 'source.c').write_text('source')
        (self.root / 'runtime/secret').write_text('must not ship')
        with self.assertRaises(ValueError):
            release.verify_product(self.root, self.product)

    def test_escaping_paths_and_links_are_rejected(self):
        for name in ('../outside', '/etc/passwd', 'runtime/../../outside', 'runtime\\file'):
            with self.assertRaises(ValueError):
                release.contained(self.root, name)
        (self.root / 'runtime/link').symlink_to(self.root / 'source.c')
        with self.assertRaises(ValueError):
            release.contained(self.root, 'runtime/link')

    def test_invalid_package_is_not_published_as_pkg(self):
        (self.root / 'OrbisDesk.pkg').write_bytes(b'MZfake')
        self.product['package_sha256'] = release.sha(self.root / 'OrbisDesk.pkg')
        with self.assertRaises(ValueError):
            release.verify_product(self.root, self.product)

    def test_manual_dispatch_and_rerun_require_owner(self):
        env = {'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': 'owner/project',
               'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_ACTOR': 'writer',
               'GITHUB_TRIGGERING_ACTOR': 'writer'}
        with patch.dict(release.os.environ, env, clear=True), self.assertRaises(ValueError):
            release.publish()
        env['GITHUB_ACTOR'] = 'owner'
        with patch.dict(release.os.environ, env, clear=True), self.assertRaises(ValueError):
            release.publish()

    def test_large_assets_split_in_order(self):
        archive = self.root / 'big.tar'
        archive.write_bytes(b'abcdefghij')
        with patch.object(release, 'ASSET_LIMIT', 4):
            parts = release.split_asset(archive)
        self.assertEqual([p.name for p in parts], ['big.tar.part000', 'big.tar.part001', 'big.tar.part002'])
        self.assertEqual(b''.join(p.read_bytes() for p in parts), b'abcdefghij')
        self.assertFalse(archive.exists())
        small = self.root / 'small.tar'
        small.write_bytes(b'ab')
        self.assertEqual(release.split_asset(small), [small])

    def test_download_must_match_its_pin(self):
        source = self.root / 'source.c'
        url = source.as_uri()
        release.fetch(url, release.sha(source), self.root / 'copy', 6)
        with self.assertRaises(ValueError):
            release.fetch(url, '0' * 64, self.root / 'copy')
        with self.assertRaises(ValueError):
            release.fetch(url, release.sha(source), self.root / 'copy', 7)

    def test_sources_lock_names_pinned_inputs(self):
        lock = json.loads((release.ROOT / 'third-party-sources.lock.json').read_text())
        assets = json.loads((release.ROOT / 'product-assets.lock.json').read_text())['downloads']
        dependencies = json.loads((release.ROOT / 'dependencies.lock.json').read_text())
        for entry in lock['downloads'].values():
            self.assertRegex(entry['sha256'], '^[0-9a-f]{64}$')
            self.assertTrue(entry['url'].startswith('https://'))
        for key in lock['product_assets']:
            self.assertIn(key, assets)
        for key in lock['dependency_archives']:
            self.assertIn(key, dependencies['archives'])
        for key in lock['repositories']:
            self.assertRegex(dependencies['repositories'][key]['commit'], '^[0-9a-f]{40}$')

    def test_sources_archive_lists_every_source(self):
        candidate = self.root / 'candidate'
        candidate.mkdir()

        def fake_fetch(url, digest, path, size=None):
            path.write_text(url)

        def fake_archive(name, url, commit, path):
            path.write_text(commit)
        with patch.object(release, 'fetch', fake_fetch), patch.object(release, 'git_archive', fake_archive):
            files = release.third_party_sources(candidate, 'orbisdesk-04.02-0123456789ab', self.root / 'work')
        self.assertEqual([p.name for p in files], ['orbisdesk-04.02-0123456789ab-third-party-sources.tar'])
        with release.tarfile.open(files[0]) as tar:
            names = tar.getnames()
            listing = tar.extractfile('orbisdesk-04.02-0123456789ab-third-party-sources/SOURCES.txt').read().decode()
        self.assertIn('orbisdesk-04.02-0123456789ab-third-party-sources/vlc-source/vlc-3.0.24.tar.xz', names)
        self.assertIn('repositories/wine-490f6d5dcbb2.tar.gz', listing)
        self.assertFalse((self.root / 'work/orbisdesk-04.02-0123456789ab-third-party-sources').exists())

    def test_non_main_cannot_publish(self):
        with patch.dict(release.os.environ, {'GITHUB_REF': 'refs/heads/dev'}, clear=True):
            with self.assertRaises(ValueError):
                release.publish()


if __name__ == '__main__':
    unittest.main()
