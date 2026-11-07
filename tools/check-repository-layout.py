#!/usr/bin/env python3
"""Reject external trees, gitlinks and generated binaries in source candidates."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.deps', 'upstream', 'build', 'out', 'reports', 'private-notes'}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    candidates = set(git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode().split('\0')) - {''}
    errors, total = [], 0
    for name in sorted(candidates):
        relative = Path(name)
        if relative.parts[0] in EXCLUDED:
            errors.append('Excluded tree is staged: ' + name)
        path = ROOT / relative
        if not path.is_file():
            continue
        total += path.stat().st_size
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic.startswith(b'MZ') or magic == b'\x7fELF' or magic.startswith(b'PK\x03\x04'):
            errors.append('Executable/archive candidate: ' + name)
        for parent in path.parents:
            if parent == ROOT:
                break
            if (parent / '.git').exists():
                errors.append('Nested repository candidate: ' + name)
                break
    for row in git('ls-files', '--stage').decode().splitlines():
        if row.startswith('160000 '):
            errors.append('Gitlink/submodule is staged: ' + row.split('\t', 1)[-1])
    report = {'candidate_files': len(candidates), 'candidate_bytes': total, 'errors': sorted(set(errors))}
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
