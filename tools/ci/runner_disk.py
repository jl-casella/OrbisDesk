#!/usr/bin/env python3
"""Disk telemetry and allowlisted cleanup of disposable GitHub-hosted runners."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from common import ROOT, RESULTS

GIB = 1024 ** 3
# No SDK/compiler used by this product, .NET, Python or Actions runtime here.
UNUSED_RUNNER_TREES = (
    '/usr/local/lib/android', '/usr/share/swift', '/opt/ghc',
    '/usr/local/.ghcup', '/opt/hostedtoolcache/CodeQL',
)


def record(label, minimum_gib=0):
    disk = shutil.disk_usage(ROOT)
    data = {'at': datetime.now(timezone.utc).isoformat(), 'label': label,
            'total_bytes': disk.total, 'used_bytes': disk.used, 'free_bytes': disk.free,
            'minimum_free_bytes': int(minimum_gib * GIB)}
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / 'product-disk.jsonl').open('a') as stream:
        stream.write(json.dumps(data) + '\n')
    print(json.dumps(data), flush=True)
    if disk.free < minimum_gib * GIB:
        raise OSError(f'Insufficient runner disk before {label}: '
                      f'{disk.free / GIB:.1f} GiB free; need {minimum_gib} GiB')
    return data


def prepare():
    if (sys.platform != 'linux' or os.environ.get('GITHUB_ACTIONS') != 'true' or
            os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise ValueError('Cleanup is restricted to disposable GitHub-hosted Linux runners')
    record('before-runner-cleanup')
    for name in UNUSED_RUNNER_TREES:
        path = Path(name)
        # Never traverse a substituted path or a symlinked ancestor.
        if any(p.is_symlink() for p in (path, *path.parents)):
            print('Skipping linked runner cleanup path: ' + name, flush=True)
            continue
        if path.exists():
            subprocess.run(['sudo', 'rm', '-rf', '--', name], check=True)
    subprocess.run(['sudo', 'apt-get', 'clean'], check=True)
    record('after-runner-cleanup', minimum_gib=25)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'record'))
    args = parser.parse_args()
    prepare() if args.action == 'prepare' else record('workflow-final')
