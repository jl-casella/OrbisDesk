#!/usr/bin/env python3
"""Prepare only diagnostic CI dependencies, with pinned downloads and timings."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from common import ROOT, RESULTS, phase, run, revision, sha, write_json


def download(spec, name):
    path = ROOT / '.deps/downloads/ci' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or sha(path) != spec['sha256']:
        import time
        temporary = path.with_suffix(path.suffix + '.part')
        for attempt in range(3):
            try:
                req = urllib.request.Request(spec['url'], headers={'User-Agent': 'OrbisDesk-CI'})
                with urllib.request.urlopen(req, timeout=60) as source, temporary.open('wb') as target:
                    import shutil
                    shutil.copyfileobj(source, target)
                if sha(temporary) != spec['sha256']:
                    raise ValueError('Download hash differs: ' + name)
                temporary.replace(path)
                break
            except Exception:
                temporary.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    return path


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--fixtures', action='store_true')
    mode.add_argument('--prepare-only', action='store_true', help='Prepare inputs/diagnostics before restoring the emulator cache')
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
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
