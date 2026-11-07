#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Repeat the focused regressions and retain blocked Wine services explicitly."""
import hashlib
import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--verify-only', action='store_true', help='Check the saved run reports without executing again')
args = parser.parse_args()
if os.environ.get('LD_PRELOAD'):
    raise SystemExit('Final checks require the linked binary without LD_PRELOAD')
out = ROOT / 'reports/increment14'
out.mkdir(parents=True, exist_ok=True)
previous = json.loads((out / 'report.json').read_text()) if args.verify_only else None
result = {'schema_version': 1, 'Wine_booted': False,
          'windows_execution_verified': False, 'hardware_status': 'pending',
          'runs': {}, 'scope': 'PS4 directory adapters and explicit single-process limits; EXE execution remains blocked'}
cases = [(name, ['--baseline', '--case', name], 'passed') for name in
         ('files', 'threads-adapter', 'pe-dll-relocated', 'vm-stress')]
cases += [('services', ['--services'], 'blocked'),
          ('ipc', ['--ipc-services'], 'passed'),
          ('pipes', ['--pipe-services'], 'passed'),
          ('filesystem', ['--fs-services'], 'passed'),
          ('gs', ['--gs-services'], 'blocked'),
          ('wine', ['--exe', 'out/console32-bare.exe'], 'blocked')]
expected_services = {
    'services': {**{key: 'passed' for key in ('fixture', 'dup-shared-offset',
        'dup-independent-flags', 'dup-close-survival', 'fcntl-cloexec', 'socket-poll-eof')},
        'fstatfs-output': 'blocked', 'gs-query-output': 'blocked',
        'pipe-basic': 'passed', 'pipe-error-contract': 'passed'},
    'pipes': {key: 'passed' for key in ('pipe-basic-fifo-eof', 'pipe-access-errors',
        'pipe-vectors', 'pipe-nonblocking-backpressure', 'pipe-dup-last-writer',
        'pipe-scm-rights', 'pipe-blocking-wakeup', 'pipe-atomic-writers',
        'pipe-broken-reader', 'pipe-allocation-rollback')},
    'filesystem': {key: 'passed' for key in ('fs-fixtures', 'fs-openat-namespaces',
        'fs-openat-duplicate', 'fs-invalid-paths-ownership', 'fs-untracked-dirfd-rejected',
        'fs-directory-pages', 'fs-directory-rewind', 'fs-directory-close-reuse',
        'fs-empty-directory', 'fs-directory-rename-rejected', 'fs-cpu-query-error-contract')},
    'ipc': {key: 'passed' for key in ('msg-vectors', 'msg-nonblocking', 'scm-rights',
        'scm-queued-owner', 'scm-truncation', 'scm-zero-control', 'scm-stream-boundary',
        'scm-discard-and-peek', 'scm-socket-close-survival', 'socket-dup-shared-status',
        'scm-invalid-no-data', 'scm-cycle-rejected', 'scm-indirect-cycle-rejected',
        'scm-concurrent-order', 'scm-descriptor-reclamation')},
    'gs': {'gs-memory-and-native-tls': 'blocked'}}
failures = []
for name, options, expected in cases:
    command = [sys.executable, str(ROOT / 'tools/run-linux-wine.py'),
               '--fork', '--timeout', '20', *options]
    if args.verify_only:
        report_path = ROOT / previous['runs'][name]['report']
    else:
        completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        (out / (name + '-runner.log')).write_text(completed.stdout + completed.stderr)
        report_path = pathlib.Path(completed.stdout.rsplit('Report: ', 1)[1].strip())
    report = json.loads(report_path.read_text())
    result['runs'][name] = {'report': str(report_path.relative_to(ROOT)),
                            'status': report['status'],
                            'elf_sha256': report['elf_sha256'],
                            'emulator_sha256': report['emulator_sha256']}
    if report['status'] != expected or report['timed_out'] or report['unhandled_access_violation']:
        failures.append(name)
    if report['Wine_booted'] or report['windows_execution_verified']:
        failures.append(name + ': unexpected execution claim')
    if report.get('host_ld_preload'):
        failures.append(name + ': final run used LD_PRELOAD')
    if name in expected_services and {entry['case']: entry['status'] for entry in
            report['service_results']} != expected_services[name]:
        failures.append(name + ': unexpected diagnostic results')
    if name == 'wine':
        log = (report_path.parent / 'stdout.log').read_text(errors='replace')
        if (report['guest_exit_status_hex'] != '0xc0000135' or report['exit_code'] != 53 or
                report['invoked_stubs'] or
                'first_teb_ready' not in report['stages'] or
                'inprocess_channel_ready' not in report['stages'] or
                'server_ready' not in report['stages'] or
                'ntdll_pe64_ready' in report['stages'] or
                'process_spawn_blocked' not in report['stages'] or
                'wineboot.exe' not in log or 'run_wineboot failed to start wineboot c00000bb' not in log):
            failures.append(name + ': unexpected startup stage')
        result['startup_exit_zero_is_execution_success'] = False
        result['server_process_initialization_verified'] = 'server_ready' in report['stages']
        result['single_process_rejection_verified'] = 'process_spawn_blocked' in report['stages']
        result['requested_child_process'] = 'C:\\windows\\system32\\wineboot.exe'
        result['prefix_prepared'] = False
        result['startup_failure'] = 'Wineboot child rejected; empty prefix has no DOS drive mapping, STATUS_DLL_NOT_FOUND'
    result['failures'] = failures
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(name + ': ' + report['status'] + ' (' + str(report_path) + ')', flush=True)

manifest = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
if any(entry['emulator_sha256'] != manifest['executable_sha256'] for entry in result['runs'].values()):
    failures.append('Runs do not match the current emulator')
result['emulator'] = manifest
result['host_toolchain_sha256'] = hashlib.sha256(
    (ROOT / 'tools/shad-linux-toolchain.cmake').read_bytes()).hexdigest()
result['known_blockers'] = ['External prefix initialization and DOS drive layout', 'Wineboot startup policy for a prepared prefix', 'GS per-thread semantics',
                          'complete external Wine prefix', 'WoW64 translator provider integration']
result['focused_regressions_passed'] = not failures
result['functional_wine_status'] = 'blocked'
(out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
if failures:
    raise SystemExit('Unexpected regression: ' + ', '.join(failures))
