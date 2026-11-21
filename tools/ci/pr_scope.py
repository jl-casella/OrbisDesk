#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Decide whether a pull request needs the platform matrix.

The matrix builds the diagnostic ELF (tools/build.py), the own Windows fixtures and the emulator, then runs
the platform-v1 cases. Files that none of those read cannot change its result. A PR whose every changed file
is in OUTSIDE_MATRIX skips the matrix. Any other file, an empty diff, or a git failure runs it.
"""
import argparse
import fnmatch
import os
import subprocess
import sys

# Keep this list to files the matrix provably does not read. When in doubt, leave a path out: it then runs.
OUTSIDE_MATRIX = (
    # public documentation and license texts
    'docs/*', '*.md', 'LICENSES/*',
    # the hardware launcher, its runtime installer and its manage menu (product package only)
    'native/hw_install.h', 'native/hw_manage.h', 'native/wine_hardware.c',
    # console delivery and evidence collection
    'tools/upload-hardware.py', 'tools/fetch-hardware.py', 'tools/watch-hardware-run.py',
    'tools/console_state.py', 'tools/ask-server.js',
    # product package builders
    'tools/build-wine-hardware.py', 'tools/build-pop-wine-child.py',
)


def needs_matrix(paths):
    paths = [p.strip() for p in paths if p.strip()]
    if not paths:
        return True, 'no changed files listed'
    inside = [p for p in paths if not any(fnmatch.fnmatchcase(p, pattern) for pattern in OUTSIDE_MATRIX)]
    if inside:
        return True, 'matrix inputs changed: ' + ', '.join(inside[:5]) + (' ...' if len(inside) > 5 else '')
    return False, 'only files outside the matrix changed (%d)' % len(paths)


def changed_paths(base, head):
    out = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', base, head], text=True)
    return out.splitlines()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='HEAD^1')
    parser.add_argument('--head', default='HEAD')
    args = parser.parse_args()
    try:
        paths = changed_paths(args.base, args.head)
        needed, why = needs_matrix(paths)
    except (subprocess.CalledProcessError, OSError) as error:
        paths, needed, why = [], True, 'cannot list changes (%s)' % error
    for path in paths:
        print(path)
    print(('matrix needed: ' if needed else 'matrix skipped: ') + why)
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a') as stream:
            stream.write('matrix=%s\n' % ('true' if needed else 'false'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
