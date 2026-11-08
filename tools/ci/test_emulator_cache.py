"""Cache validation tests; synthetic ELF headers are never executed as an emulator."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from emulator_cache import fingerprint, validate_bundle
from common import sha, write_json


class EmulatorCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bundle = Path(self.directory.name)
        patch = b'locked patch bytes'
        (self.bundle / 'source.patch').write_bytes(patch)
        (self.bundle / 'shadps4').write_bytes(b'\x7fELF\x02' + bytes(100))
        source = {'commit': 'a' * 40, 'tree': 'b' * 40,
                  'patch_sha256': hashlib.sha256(patch).hexdigest(),
                  'submodules': [{'path': 'externals/example', 'commit': 'c' * 40}]}
        self.inputs = {'source': source, 'toolchain': {'compiler': 'LLVM19'}, 'recipes': {'builder': 'hash'}}
        self.record = {'key': fingerprint(self.inputs), 'inputs': self.inputs}
        self.manifest = {'commit': source['commit'], 'source_patch_sha256': source['patch_sha256'],
                         'submodules': [' ' + 'c' * 40 + ' externals/example (tag)'],
                         'executable_sha256': sha(self.bundle / 'shadps4')}
        write_json(self.bundle / 'build-manifest.json', self.manifest)
        write_json(self.bundle / 'cache-proof.json', {'key': self.record['key'], 'inputs': self.inputs,
                   'manifest_sha256': sha(self.bundle / 'build-manifest.json')})

    def test_exact_bundle_matches_and_altered_binary_is_rejected(self):
        self.assertEqual(validate_bundle(self.bundle, self.record), self.manifest)
        with (self.bundle / 'shadps4').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            validate_bundle(self.bundle, self.record)

    def test_patch_toolchain_and_recipe_changes_invalidate_identity(self):
        changes = [('source', 'patch_sha256'), ('toolchain', 'compiler'), ('recipes', 'builder')]
        for section, name in changes:
            changed = copy.deepcopy(self.inputs)
            changed[section][name] += 'changed'
            self.assertNotEqual(fingerprint(changed), self.record['key'])
            with self.assertRaises(ValueError):
                validate_bundle(self.bundle, {'key': fingerprint(changed), 'inputs': changed})
        changed = copy.deepcopy(self.inputs)
        changed['source']['submodules'][0]['commit'] = 'd' * 40
        self.assertNotEqual(fingerprint(changed), self.record['key'])

    def test_changed_manifest_or_extra_payload_is_rejected(self):
        with (self.bundle / 'build-manifest.json').open('a') as stream:
            stream.write(' ')
        with self.assertRaises(ValueError):
            validate_bundle(self.bundle, self.record)
        write_json(self.bundle / 'build-manifest.json', self.manifest)
        (self.bundle / 'extra-file').write_text('must not ship')
        with self.assertRaises(ValueError):
            validate_bundle(self.bundle, self.record)


if __name__ == '__main__':
    unittest.main()
