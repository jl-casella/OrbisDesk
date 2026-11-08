#!/usr/bin/env python3
"""Prepare only diagnostic CI dependencies, with pinned downloads and timings."""
import argparse
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from common import ROOT, RESULTS, phase, run, revision, sha, write_json


def download(spec, name):
    if name in ('', '.', '..') or Path(name).name != name or '\\' in name:
        raise ValueError('Download name must be a basename')
    path = ROOT / '.deps/downloads/ci' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Download cache entry must not be a symlink')
    if path.exists() and sha(path) == spec['sha256']:
        print('Verified download cache hit: ' + name, flush=True)
        return path
    path.unlink(missing_ok=True)
    temporary = path.with_suffix(path.suffix + '.part')
    for attempt in range(1, 7):
        started = time.monotonic()
        print(f'Downloading {name}, attempt {attempt}/6', flush=True)
        try:
            req = urllib.request.Request(spec['url'], headers={'User-Agent': 'OrbisDesk-CI'})
            with urllib.request.urlopen(req, timeout=60) as source, temporary.open('wb') as target:
                import shutil
                shutil.copyfileobj(source, target)
                length = source.headers.get('Content-Length')
                if length and length.isdigit() and target.tell() != int(length):
                    raise http.client.IncompleteRead(b'', max(0, int(length) - target.tell()))
            if sha(temporary) != spec['sha256']:
                raise ValueError('Download hash differs: ' + name)
            temporary.replace(path)
            download_event(name, attempt, 'verified', started)
            return path
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as exc:
            temporary.unlink(missing_ok=True)
            code = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            transient = code is None or code in (408, 429, 500, 502, 503, 504)
            delay = min(60, 5 * 2 ** (attempt - 1))
            if isinstance(exc, urllib.error.HTTPError) and exc.headers:
                retry_after = exc.headers.get('Retry-After', '').strip()
                if retry_after.isdigit():
                    delay = min(60, max(delay, int(retry_after)))
            retry = transient and attempt < 6
            download_event(name, attempt, 'retry' if retry else 'failed', started,
                           error_type=type(exc).__name__, http_status=code, retry_delay_seconds=delay if retry else 0)
            if not retry:
                raise
            print(f'{name}: {type(exc).__name__}' + (f' HTTP {code}' if code else '') + f'; retry in {delay}s', flush=True)
            time.sleep(delay)
        except BaseException as exc:
            temporary.unlink(missing_ok=True)
            download_event(name, attempt, 'failed', started, error_type=type(exc).__name__)
            raise


def download_event(name, attempt, status, started, **details):
    RESULTS.mkdir(parents=True, exist_ok=True)
    event = {'file': name, 'attempt': attempt, 'status': status,
             'duration_seconds': round(time.monotonic() - started, 3), **details}
    with (RESULTS / 'download-attempts.jsonl').open('a') as stream:
        stream.write(json.dumps(event) + '\n')


def check_download_cache():
    specs = {'openorbis.tar.gz': json.loads((ROOT / 'artifacts.lock.json').read_text())['openorbis'],
             'shadps4-linux.zip': json.loads((ROOT / 'linux-emulator.lock.json').read_text()),
             'libc6.deb': json.loads((ROOT / 'linux-runtime.lock.json').read_text())}
    verified = {}
    for name, spec in specs.items():
        path = ROOT / '.deps/downloads/ci' / name
        if path.is_symlink():
            raise ValueError('Unexpected symlink in download cache: ' + name)
        if path.exists():
            if sha(path) != spec['sha256']:
                raise ValueError('Refusing to cache unverified download: ' + name)
            verified[name] = spec['sha256']
    write_json(RESULTS / 'download-cache.json', {'verified_files': verified, 'count': len(verified)})
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write('ready=' + str(bool(verified)).lower() + '\ncount=' + str(len(verified)) + '\n')
    print('Verified downloadable cache entries: ' + str(len(verified)), flush=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fixtures', action='store_true')
    mode.add_argument('--prepare-only', action='store_true', help='Prepare inputs/diagnostics before restoring the emulator cache')
    mode.add_argument('--check-download-cache', action='store_true', help='Verify completed archives before saving the download cache')
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.check_download_cache:
        check_download_cache()
        return
    if args.fixtures:
        with phase('fixture-build'):
            run([sys.executable, ROOT / 'tools/build.py', '--fixtures-only'], RESULTS / 'fixtures-build.log')
            manifest = json.loads((ROOT / 'out/build.json').read_text())
            write_json(ROOT / 'out/ci-fixtures.json', {
                'source_sha': revision(), 'artifacts': manifest['artifacts'],
                'producer': manifest['tools'], 'scope': 'Own PE32 fixtures, not product binaries'})
        return
    with phase('sources'):
        # The existing diagnostic builder checks all original reference HEADs.
        run([sys.executable, ROOT / 'tools/fetch_sources.py'], RESULTS / 'sources.log')
        run([sys.executable, ROOT / 'tools/restore-dependencies.py', '--fetch', '--only', 'shadps4-fork'],
            RESULTS / 'fork-restore.log')
    with phase('sdk-download-extract'):
        spec = json.loads((ROOT / 'artifacts.lock.json').read_text())['openorbis']
        archive = download(spec, 'openorbis.tar.gz')
        sdk = ROOT / '.deps/sdk'
        sdk.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as source:
            source.extractall(sdk, filter='data')
    with phase('official-download-extract'):
        spec = json.loads((ROOT / 'linux-emulator.lock.json').read_text())
        archive = download(spec, 'shadps4-linux.zip')
        target = ROOT / '.deps/shadPS4-linux'
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                if not (target / entry.filename).resolve().is_relative_to(target.resolve()):
                    raise ValueError('Archive path escapes destination')
            source.extractall(target)
        images = list(target.rglob('*.AppImage'))
        if len(images) != 1:
            raise ValueError('Expected exactly one official AppImage')
        images[0].chmod(0o755)
        with (RESULTS / 'official-extract.log').open('w') as log:
            subprocess.run([str(images[0]), '--appimage-extract'], cwd=target,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        libc = json.loads((ROOT / 'linux-runtime.lock.json').read_text())
        archive = download(libc, 'libc6.deb')
        run(['dpkg-deb', '-x', archive, ROOT / '.deps/linux-runtime'], RESULTS / 'libc-extract.log')
    # Never rebuild the fixture binaries after Windows has tested them.
    fixture = json.loads((ROOT / 'out/ci-fixtures.json').read_text())
    if fixture['source_sha'] != revision():
        raise ValueError('Fixture source SHA differs')
    for name, record in fixture['artifacts'].items():
        if sha(ROOT / 'out' / name) != record['sha256']:
            raise ValueError('Fixture changed: ' + name)
    with phase('diagnostic-build'):
        run([sys.executable, ROOT / 'tools/build.py', '--diagnostics-only',
             '--cc', 'clang-19', '--ld', 'ld.lld-19'], RESULTS / 'diagnostic-build.log')
    run([sys.executable, ROOT / 'tools/ci/build-services.py'], RESULTS / 'services-build-driver.log')
    if not args.prepare_only:
        with phase('emulator-build'):
            run([sys.executable, ROOT / 'tools/build-shad-linux.py', '--jobs', '2'],
                RESULTS / 'emulator-build-driver.log', timeout=3600)
    write_json(RESULTS / 'environment.json', {
        'source_sha': revision(), 'cache_mode': os.environ.get('CI_CACHE_MODE', 'local'),
        'locks': {p.name: sha(p) for p in ROOT.glob('*.lock.json')},
        'packages': subprocess.check_output(['dpkg-query', '-W'], text=True).splitlines(),
        'disk': subprocess.check_output(['df', '-h', str(ROOT)], text=True)})


if __name__ == '__main__':
    main()
