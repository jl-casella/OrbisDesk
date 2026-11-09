#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the complete configured host Wine tree (make -k) after its closures.

W303: a prefix made by wineboot from a closure-only tree left 141 DLLs unregistered (ATL's
IRegistrar, ShellLink, desktop icons). The prefix must come from the complete tree. Only the
unused native side of dlls/wineusb.sys may fail: libusb is not installed and the host Unix
closure omits that backend on purpose. Any other failed target fails this step.
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / '.deps/wine/runtime/build'
LOG = ROOT / '.deps/wine/runtime/make-complete-tree.log'
REPORT = ROOT / 'reports/increment15/host-build/tree-report.json'
FAILED = re.compile(r'^make(?:\[\d+\])?: \*\*\* \[(?:[^\]:]*:\d+: )?(?P<target>[^\]]+)\] Error \d+', re.M)


def allowed_failure(target):
    """The wineusb.sys Unix library and its objects; never its PE side (*-windows/)."""
    parts = pathlib.PurePosixPath(target).parts
    return (len(parts) >= 3 and parts[:2] == ('dlls', 'wineusb.sys') and
            not any(part.endswith('-windows') for part in parts) and target.endswith(('.o', '.so')))


def classify(log_text, exit_code):
    failed = sorted(set(FAILED.findall(log_text)))
    unexpected = [target for target in failed if not allowed_failure(target)]
    # a non-zero make without any failed-target line (killed, makefile error) is not a known outcome
    passed = not unexpected and (exit_code == 0 or bool(failed))
    return {'failed_targets': failed, 'unexpected_failures': unexpected, 'passed': passed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 2)
    args = parser.parse_args()
    if not (BUILD / 'Makefile').is_file():
        raise SystemExit('Configure the host tree first (tools/build-wine.py)')
    expected = json.loads((ROOT / 'sources.lock.json').read_text())['sources']['wine']['commit']
    commit = subprocess.check_output(['git', '-C', str(ROOT / '.deps/wine/source'), 'rev-parse', 'HEAD'],
                                     text=True).strip()
    if commit != expected:
        raise SystemExit('Wine source revision mismatch')
    start = time.monotonic()
    with LOG.open('w') as log:
        result = subprocess.run(['make', '-k', '-j' + str(args.jobs)], cwd=BUILD, stdout=log,
                                stderr=subprocess.STDOUT, env=dict(os.environ, LC_ALL='C', TZ='UTC'))
    outcome = classify(LOG.read_text(errors='replace'), result.returncode)
    report = {'schema_version': 1, 'status': 'passed' if outcome['passed'] else 'failed',
              'scope': 'Complete native host Wine tree for prefix creation; not PS4 validation',
              'wine_commit': commit, 'exit_code': result.returncode, 'jobs': args.jobs,
              'allowed_failures': 'dlls/wineusb.sys native objects/library (libusb absent; unused backend)',
              **outcome, 'log': str(LOG.relative_to(ROOT)),
              'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'duration_seconds': round(time.monotonic() - start, 3)}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    if not outcome['passed']:
        print('\n'.join(LOG.read_text(errors='replace').splitlines()[-60:]), flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
