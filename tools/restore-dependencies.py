#!/usr/bin/env python3
"""Inspect or restore pinned sources without replacing existing working trees."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args, env=None):
    return subprocess.check_output(
        ['git', '-c', 'core.autocrlf=false', '-C', str(path), *args], env=env
    ).decode().strip()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def location(spec):
    if spec.get('location') == 'wsl-home':
        if os.name == 'nt':
            raise ValueError('Run this dependency in WSL, not Windows Python')
        return Path(spec['path']).expanduser()
    path = (ROOT / spec['path']).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Dependency path escapes project root')
    if not path.is_relative_to(ROOT / '.deps') and not path.is_relative_to(ROOT / 'upstream'):
        raise ValueError('Dependency destination must be ignored')
    return path


def repository(name, spec, fetch):
    path = location(spec)
    if not (path / '.git').exists():
        if path.exists() and any(path.iterdir()):
            revision = path / 'REVISION'
            if not fetch and revision.is_file() and revision.read_text().strip() == spec['commit']:
                return 'export-revision-only (content not verified)'
            raise ValueError('Existing non-Git directory; refusing to replace it')
        if not fetch:
            return 'missing'
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', str(path)], check=True)
        git(path, 'remote', 'add', 'origin', spec['url'])
        git(path, 'fetch', '--depth', '1', 'origin', spec['commit'])
        git(path, 'checkout', '--detach', 'FETCH_HEAD')
    actual = git(path, 'rev-parse', 'HEAD')
    if actual != spec['commit']:
        raise ValueError(f"Revision differs: {actual}; expected {spec['commit']}")
    return 'revision-matches (local edits not assessed)'


def fork(spec, fetch):
    lock = json.loads((ROOT / spec['lock']).read_text())
    overlay = spec['overlay']
    for patch in [*lock['patches'], overlay]:
        if digest(ROOT / patch['path']) != patch['sha256']:
            raise ValueError('Patch checksum differs: ' + patch['path'])
    path = ROOT / spec['checkout']
    if not (path / '.git').exists():
        if path.exists() and any(path.iterdir()):
            raise ValueError('Existing non-Git fork directory')
        if not fetch:
            return 'missing'
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', str(path)], check=True)
        git(path, 'remote', 'add', 'origin', lock['upstream'])
        git(path, 'fetch', '--depth', '1', 'origin', lock['base_commit'])
        git(path, 'checkout', '-b', lock['branch'], 'FETCH_HEAD')
        for patch in lock['patches']:
            # Commit identity can differ from the historical fork. Verify its tree below.
            git(path, '-c', 'user.name=OrbisDesk', '-c', 'user.email=orbisdesk@localhost',
                'am', '--committer-date-is-author-date', str(ROOT / patch['path']))
    if git(path, 'rev-parse', 'HEAD^{tree}') != spec['expected_head_tree']:
        raise ValueError('Fork HEAD tree differs from the locked 17-patch tree')
    diff = subprocess.check_output([
        'git', '-c', 'core.autocrlf=true', '-C', str(path), 'diff',
        '--ignore-submodules=all', 'HEAD', '--binary'])
    expected = (ROOT / overlay['path']).read_bytes()
    if not diff and fetch:
        git(path, 'apply', '--check', str(ROOT / overlay['path']))
        # Include added files in the complete working diff checked below.
        git(path, 'apply', '--intent-to-add', str(ROOT / overlay['path']))
        state = fork(spec, False)
        git(path, 'submodule', 'update', '--init', '--recursive', '--depth', '1')
        return state
    if diff != expected:
        raise ValueError('Fork working diff differs from the locked overlay; refusing to overwrite')
    if fetch:
        git(path, 'submodule', 'update', '--init', '--recursive', '--depth', '1')
    return 'HEAD tree and complete tracked overlay match; untracked files not assessed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='Create missing checkouts; never overwrite existing sources')
    parser.add_argument('--only', action='append', help='Repository name, or shadps4-fork; repeatable')
    parser.add_argument('--archives', action='store_true', help='Also verify the three graphics archive hashes')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'dependencies.lock.json').read_text())
    names = args.only or [*lock['repositories'], 'shadps4-fork']
    records, failed = [], False
    for name in names:
        try:
            if name == 'shadps4-fork':
                state = fork(lock['shadps4_fork'], args.fetch)
            else:
                state = repository(name, lock['repositories'][name], args.fetch)
        except (ValueError, KeyError, subprocess.CalledProcessError, OSError) as exc:
            state = 'error: ' + str(exc)
            failed = True
        if state == 'missing':
            failed = True
        records.append({'name': name, 'state': state})
        print(name + ': ' + state, flush=True)
    if args.archives:
        for name, spec in lock['archives'].items():
            path = ROOT / spec['path']
            valid = path.is_file() and digest(path) == spec['sha256']
            records.append({'name': name, 'state': 'archive-matches' if valid else 'archive-missing-or-changed'})
            failed |= not valid
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(records, indent=2) + '\n')
    raise SystemExit(int(failed))


if __name__ == '__main__':
    main()
