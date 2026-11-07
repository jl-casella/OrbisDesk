#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Package a verified native Wine prefix for a later PS4 preflight."""
import argparse
import hashlib
import json
import pathlib
import posixpath
import shutil
import subprocess
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('producer', type=pathlib.Path, help='Directory containing the producer report')
parser.add_argument('destination', type=pathlib.Path, help='New directory inside the workspace')
args = parser.parse_args()
source = args.producer.resolve()
destination = args.destination.resolve()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

report_path = source / 'report.json'
report = json.loads(report_path.read_text())
if (report.get('status') != 'passed' or not report.get('initialized_by_wineboot') or
        not report.get('console32_verified') or not report.get('prefix_ready_for_packaging')):
    raise SystemExit('Producer did not verify Wineboot and the PE32 console fixture')
commit = subprocess.check_output(['git', '-C', str(ROOT / '.deps/wine/source'),
                                  'rev-parse', 'HEAD'], text=True).strip()
if report['wine_commit'] != commit:
    raise SystemExit('Wine revision mismatch')
archive_path = source / 'prefix.tar.gz'
if sha(archive_path) != report['prefix_archive_sha256']:
    raise SystemExit('Prefix archive hash mismatch')
fixture = ROOT / 'out/console32-bare.exe'
if sha(fixture) != report['exe_sha256']:
    raise SystemExit('Console fixture hash mismatch')
if not destination.is_relative_to(ROOT) or destination == ROOT or destination.exists():
    raise SystemExit('Expected a new destination inside the workspace')

destination.parent.mkdir(parents=True, exist_ok=True)
changes = []
omitted = []
with tempfile.TemporaryDirectory(prefix='.prefix-package-', dir=destination.parent) as temporary:
    package = pathlib.Path(temporary)
    prefix = package / 'prefix'
    prefix.mkdir()
    links = []
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        names = set()
        symbolic = set()
        for member in members:
            name = pathlib.PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or not name.parts or
                    name.parts[0] != 'prefix' or member.name in names):
                raise SystemExit('Unsafe or duplicate archive path: ' + member.name)
            names.add(member.name)
            if member.issym():
                symbolic.add(name)
        for member in members:
            name = pathlib.PurePosixPath(member.name)
            if any(parent in symbolic for parent in name.parents):
                raise SystemExit('Archive member beneath a symlink: ' + member.name)
            relative = name.relative_to('prefix')
            path = prefix.joinpath(*relative.parts)
            if str(relative).lower() == 'drive_c/windows/system32/wow64cpu.dll':
                omitted.append({'path': str(relative), 'reason':
                    'Native host CPU provider is not the PS4 x86 translator'})
                continue
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                links.append((relative, member.linkname))
            elif member.isfile() or member.islnk():
                if member.islnk():
                    target = pathlib.PurePosixPath(member.linkname)
                    if target.is_absolute() or '..' in target.parts or target.parts[0] != 'prefix':
                        raise SystemExit('Unsafe hard link: ' + member.name)
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as data, path.open('wb') as output:
                    shutil.copyfileobj(data, output)
            else:
                raise SystemExit('Unsupported archive entry: ' + member.name)
    for relative, target in links:
        path = prefix.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        if (relative.parent.as_posix() == 'dosdevices' and
                relative.name.startswith('com') and relative.name[3:].isdigit() and
                target.startswith('/dev/tty')):
            omitted.append({'path': str(relative), 'reason': 'Host serial device mapping is not portable'})
            continue
        if str(relative) in ('dosdevices/c:', 'dosdevices/z:'):
            normalized = '../drive_c' if relative.name == 'c:' else '../..'
            path.symlink_to(normalized)
            changes.append({'path': str(relative), 'action': 'DOS drive rebased', 'target': normalized})
            continue
        normalized = pathlib.PurePosixPath(posixpath.normpath(posixpath.join(str(relative.parent), target)))
        if not normalized.is_absolute() and '..' not in normalized.parts:
            path.symlink_to(target)
        elif relative.parts[:2] == ('drive_c', 'users'):
            path.mkdir()
            changes.append({'path': str(relative), 'action': 'External profile directory made local'})
        else:
            raise SystemExit('External symlink requires explicit export policy: ' + str(relative))
    for name, digest in report['registry_hashes'].items():
        if name not in ('system.reg', 'user.reg', 'userdef.reg') or sha(prefix / name) != digest:
            raise SystemExit('Registry hash mismatch: ' + name)
    for drive, target in (('c:', '../drive_c'), ('z:', '../..')):
        path = prefix / 'dosdevices' / drive
        if not path.is_symlink() or path.readlink().as_posix() != target:
            raise SystemExit('Missing normalized DOS drive: ' + drive)
    app = prefix / 'drive_c/orbis/console32.exe'
    app.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, app)
    entries = {}
    for path in sorted(prefix.rglob('*')):
        relative = path.relative_to(prefix).as_posix()
        if path.is_symlink():
            entries[relative] = {'type': 'symlink', 'target': path.readlink().as_posix()}
        elif path.is_file():
            entries[relative] = {'type': 'file', 'sha256': sha(path), 'bytes': path.stat().st_size}
        elif path.is_dir():
            entries[relative] = {'type': 'directory'}
    with tarfile.open(package / 'prefix.tar.gz', 'w:gz', dereference=False) as archive:
        archive.add(prefix, arcname='prefix')
    result = {'schema_version': 1, 'status': 'packaged-for-preflight',
        'wine_commit': commit, 'producer_report_sha256': sha(report_path),
        'source_prefix_sha256': sha(archive_path),
        'archive_sha256': sha(package / 'prefix.tar.gz'),
        'native_console32_verified': True, 'ps4_runtime_ready': False,
        'windows_execution_verified_in_shadps4': False, 'hardware_status': 'pending',
        'placement': '/data/wine-prefix', 'exe': 'C:\\orbis\\console32.exe',
        'changes': changes, 'omitted': omitted, 'entries': entries,
        'remaining_requirements': ['Prepared-prefix startup policy', 'GS semantics',
                                   'PS4 WoW64 translator provider', 'PS4 runtime validation']}
    (package / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.rmtree(prefix)
    package.rename(destination)
print(destination / 'manifest.json')
