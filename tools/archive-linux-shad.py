#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Preserve a built Linux emulator and its local build inputs."""
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('destination', type=pathlib.Path)
args = parser.parse_args()
destination = args.destination.resolve()
if not destination.is_relative_to(ROOT / 'reports') or destination.exists():
    raise SystemExit('Expected a new destination inside reports')
manifest = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
if sha(ROOT / 'build/shadPS4-linux/shadps4') != manifest['executable_sha256']:
    raise SystemExit('Emulator changed since its build manifest')
files = {ROOT / name for name in (
    'fork.lock.json', 'tools/build-shad-linux.py', 'tools/shad-linux-toolchain.cmake',
    'tools/run-linux-shad.py', 'tools/run-linux-wine.py', 'tools/wine_prefix.py', 'tools/check-increment11.py',
    'tools/prepare-linux-source.py', 'tools/archive-linux-shad.py', 'tests/fork-patches.ps1',
    'build/increment11-source-normalization.json', 'build/increment11-libcxx-thread-check.cpp')}
for name in ('shadps4', 'build-manifest.json', 'source.patch', 'configure.log', 'build.log',
             'CMakeCache.txt', 'build.ninja', 'CMakeFiles/rules.ninja'):
    files.add(ROOT / 'build/shadPS4-linux' / name)
files.update((ROOT / 'patches/shadPS4').glob('*.patch'))
files.update((ROOT / 'tools').glob('check-increment*.py'))
files.update((ROOT / 'build/shadPS4-linux/externals').glob('ffmpeg-*.zip'))
destination.mkdir(parents=True)
identities = {}
for source in sorted(files):
    relative = source.relative_to(ROOT)
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    identities[str(relative)] = {'sha256': sha(target), 'bytes': target.stat().st_size}
binary = ROOT / 'build/shadPS4-linux/shadps4'
for name, command in (
        ('dynamic-libraries.txt', ['ldd', str(binary)]),
        ('dynamic-section.txt', ['readelf', '-d', str(binary)]),
        ('tool-versions.txt', ['clang++-19', '--version'])):
    target = destination / name
    target.write_text(subprocess.check_output(command, text=True))
    identities[name] = {'sha256': sha(target), 'bytes': target.stat().st_size}
(destination / 'evidence.json').write_text(json.dumps({
    'schema_version': 1, 'files': identities, 'emulator': manifest,
    'scope': 'Linux emulator build inputs; Wine startup remains blocked',
    'hardware_status': 'pending'}, indent=2) + '\n')
print(destination / 'evidence.json')
