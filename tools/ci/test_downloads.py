"""Network failure-path tests; no archive is extracted or treated as emulator evidence."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import bootstrap


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data))}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.results = self.root / 'reports'
        self.payload = b'verified test archive bytes'
        self.spec = {'url': 'https://example.invalid/sdk', 'sha256': hashlib.sha256(self.payload).hexdigest()}
        self.archive = self.root / '.deps/downloads/ci/openorbis.tar.gz'
        for name, value in [('ROOT', self.root), ('RESULTS', self.results)]:
            manager = patch.object(bootstrap, name, value)
            manager.start()
            self.addCleanup(manager.stop)

    def error(self, code):
        return urllib.error.HTTPError(self.spec['url'], code, 'test HTTP error', {}, None)

    def test_gateway_timeout_retries_then_verifies(self):
        with patch.object(bootstrap.urllib.request, 'urlopen', side_effect=[self.error(504), Response(self.payload)]) as opener, \
                patch.object(bootstrap.time, 'sleep') as sleep, redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.download(self.spec, self.archive.name).read_bytes(), self.payload)
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once_with(5)
        events = [json.loads(line) for line in (self.results / 'download-attempts.jsonl').read_text().splitlines()]
        self.assertEqual([event['status'] for event in events], ['retry', 'verified'])
        self.assertEqual(events[0]['http_status'], 504)

    def test_permanent_http_error_does_not_loop(self):
        with patch.object(bootstrap.urllib.request, 'urlopen', side_effect=self.error(404)) as opener, \
                patch.object(bootstrap.time, 'sleep') as sleep, redirect_stdout(io.StringIO()):
            with self.assertRaises(urllib.error.HTTPError):
                bootstrap.download(self.spec, self.archive.name)
        self.assertEqual(opener.call_count, 1)
        sleep.assert_not_called()

    def test_retries_are_bounded_and_leave_no_partial_archive(self):
        with patch.object(bootstrap.urllib.request, 'urlopen', side_effect=self.error(504)) as opener, \
                patch.object(bootstrap.time, 'sleep') as sleep, redirect_stdout(io.StringIO()):
            with self.assertRaises(urllib.error.HTTPError):
                bootstrap.download(self.spec, self.archive.name)
        self.assertEqual(opener.call_count, 6)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10, 20, 40, 60])
        self.assertFalse(self.archive.exists())
        self.assertFalse(list(self.archive.parent.glob('*.part')))

    def test_wrong_hash_never_becomes_a_completed_download(self):
        with patch.object(bootstrap.urllib.request, 'urlopen', return_value=Response(b'wrong content')), \
                patch.object(bootstrap.time, 'sleep') as sleep, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                bootstrap.download(self.spec, self.archive.name)
        sleep.assert_not_called()
        self.assertFalse(self.archive.exists())
        self.assertFalse(list(self.archive.parent.glob('*.part')))

    def test_valid_cache_skips_network_and_corrupt_cache_is_replaced(self):
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(self.payload)
        with patch.object(bootstrap.urllib.request, 'urlopen') as opener, redirect_stdout(io.StringIO()):
            bootstrap.download(self.spec, self.archive.name)
        opener.assert_not_called()
        self.archive.write_bytes(b'altered cached file')
        with patch.object(bootstrap.urllib.request, 'urlopen', return_value=Response(self.payload)) as opener, \
                redirect_stdout(io.StringIO()):
            bootstrap.download(self.spec, self.archive.name)
        opener.assert_called_once()
        self.assertEqual(self.archive.read_bytes(), self.payload)

    def test_cache_save_accepts_only_completed_verified_files(self):
        (self.root / 'artifacts.lock.json').write_text(json.dumps({'openorbis': self.spec}))
        for name in ('linux-emulator.lock.json', 'linux-runtime.lock.json'):
            (self.root / name).write_text(json.dumps(self.spec))
        self.archive.parent.mkdir(parents=True)
        self.archive.write_bytes(self.payload)
        (self.archive.parent / 'shadps4-linux.zip.part').write_bytes(b'incomplete')
        with patch.dict(bootstrap.os.environ, {'GITHUB_OUTPUT': str(self.root / 'outputs')}), redirect_stdout(io.StringIO()):
            bootstrap.check_download_cache()
            record = json.loads((self.results / 'download-cache.json').read_text())
            self.assertEqual(record['count'], 1)
            (self.archive.parent / 'libc6.deb').write_bytes(b'wrong cached download')
            with self.assertRaisesRegex(ValueError, 'unverified download'):
                bootstrap.check_download_cache()


if __name__ == '__main__':
    unittest.main()
