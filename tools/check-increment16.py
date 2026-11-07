#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run console32-bare.exe without Wine in both emulators and repeat the regressions."""
import argparse
import hashlib
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
out = ROOT / 'reports/increment16'
out.mkdir(parents=True, exist_ok=True)
previous = json.loads((out / 'report.json').read_text()) if args.verify_only else None
reference_dir = ROOT / 'reports/increment11-windows-reference'
reference = json.loads((reference_dir / 'report.json').read_text())
reference_result = (reference_dir / 'result.txt').read_bytes()
result = {'schema_version': 1, 'Wine_booted': False, 'Wine_used': False,
          'windows_execution_verified': False, 'hardware_status': 'pending',
          'windows_reference': {'exe_sha256': reference['exe_sha256'], 'exit_code': reference['exit_code'],
                                'result_sha256': hashlib.sha256(reference_result).hexdigest()},
          'runs': {}, 'scope': 'console32-bare.exe through the own PE32 loader and a minimal kernel32; no Wine'}
# The official Linux release keeps the hostexec RX publication refusal recorded since increment 2.
cases = [('console-bare', ['--fork', '--baseline', '--case', 'console-bare'], 'passed'),
         ('console-bare-official', ['--baseline', '--case', 'console-bare'], 'blocked')]
cases += [(name, ['--fork', '--baseline', '--case', name], 'passed') for name in
          ('files', 'threads-adapter', 'pe-dll-relocated', 'vm-stress')]
cases += [(name, ['--fork', option], 'passed') for name, option in
          (('ipc', '--ipc-services'), ('pipes', '--pipe-services'), ('filesystem', '--fs-services'),
           ('metadata', '--metadata-services'))]
expected_services = {
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
    'metadata': {key: 'passed' for key in ('metadata-file-identity', 'metadata-stat-fstat',
        'metadata-link-follow', 'metadata-readlink-bounds', 'metadata-dangling-link',
        'metadata-readlink-errors', 'metadata-directory-identity',
        'metadata-open-file-rename', 'metadata-open-directory-rename')}}
# CloseHandle twice, then one call each; GetCurrentProcessId is only resolved, never called.
expected_calls = {'CloseHandle': 2, 'CreateFileA': 1, 'CreateThread': 1, 'ExitProcess': 1, 'FreeLibrary': 1,
                  'GetExitCodeThread': 1, 'GetProcAddress': 1, 'LoadLibraryA': 1,
                  'WaitForSingleObject': 1, 'WriteFile': 1}
failures = []
for name, options, expected in cases:
    command = [sys.executable, str(ROOT / 'tools/run-linux-wine.py'), '--timeout', '20', *options]
    if args.verify_only:
        report_path = ROOT / previous['runs'][name]['report']
    else:
        completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        (out / (name + '-runner.log')).write_text(completed.stdout + completed.stderr)
        report_path = pathlib.Path(completed.stdout.rsplit('Report: ', 1)[1].strip())
    report = json.loads(report_path.read_text())
    result['runs'][name] = {'report': str(report_path.relative_to(ROOT)),
                            'status': report['status'],
                            'emulator_kind': report['emulator_kind'],
                            'elf_sha256': report['elf_sha256'],
                            'emulator_sha256': report.get('emulator_sha256')}
    if report['status'] != expected or (report['timed_out'] and name != 'console-bare-official'):
        failures.append(name)
    if report['unhandled_access_violation'] and expected == 'passed':
        failures.append(name + ': unhandled access violation')
    if report['Wine_booted'] or report['windows_execution_verified']:
        failures.append(name + ': unexpected execution claim')
    if report.get('host_ld_preload'):
        failures.append(name + ': final run used LD_PRELOAD')
    if name in expected_services and {entry['case']: entry['status'] for entry in
            report['service_results']} != expected_services[name]:
        failures.append(name + ': unexpected diagnostic results')
    if name.startswith('console-bare'):
        trace = report.get('k32_trace', [])
        calls = {}
        for entry in trace:
            if 'call' in entry:
                calls[entry['call']] = calls.get(entry['call'], 0) + 1
        result['runs'][name].update({'guest_exit_code': report['guest_exit_code'],
                                     'result_matches_windows_reference': report['console_result_matches_windows_reference'],
                                     'kernel32_calls': calls, 'invoked_stubs': report['invoked_stubs'],
                                     'refusals': [entry for entry in trace if 'refused' in entry or 'fault' in entry]})
        if report['console_exe_sha256'] != reference['exe_sha256']:
            failures.append(name + ': EXE differs from the Windows reference')
    if name == 'console-bare':
        log = (report_path.parent / 'stdout.log').read_text(errors='replace')
        detail = [line for line in log.splitlines() if '"case":"console-bare","status":"passed"' in line]
        if (not report['console_result_matches_windows_reference'] or
                report['guest_exit_code'] != reference['exit_code'] or report['exit_code'] != reference['exit_code'] or
                report['invoked_stubs'] or result['runs'][name]['refusals'] or calls != expected_calls or
                not detail or 'refused=0 leaked=0' not in detail[0] or 'thread_failures=0' not in detail[0]):
            failures.append(name + ': output differs from the Windows reference contract')
        result['console_detail'] = detail[0].split('PWPS4 ', 1)[-1] if detail else None
    if name == 'console-bare-official':
        # Guest completes; the release build then asserts on exit(0) and never terminates.
        log = (report_path.parent / 'stdout.log').read_text(errors='replace')
        if (not report['baseline_guest_passed'] or not report['console_result_matches_windows_reference'] or
                not report['timed_out'] or 'process.cpp:312 exit: Unreachable code!' not in log):
            failures.append(name + ': unexpected official blocker')
        result['official_blocker'] = 'Guest passes; emulator asserts in process.cpp exit on status 0 and times out'
    result['failures'] = failures
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(name + ': ' + report['status'] + ' (' + str(report_path) + ')', flush=True)

manifest = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
if any(entry['emulator_sha256'] != manifest['executable_sha256'] for entry in result['runs'].values()
       if entry['emulator_kind'] == 'local Linux fork'):
    failures.append('Runs do not match the current emulator')
build = json.loads((ROOT / 'out/build.json').read_text())
if build['artifacts']['console32-bare.exe']['sha256'] != reference['exe_sha256']:
    failures.append('Built console32-bare.exe differs from the Windows reference')
elf = hashlib.sha256((ROOT / 'out/eboot.bin').read_bytes()).hexdigest()
if any(result['runs'][name]['elf_sha256'] != elf for name in
       ('console-bare', 'console-bare-official', 'files', 'threads-adapter', 'pe-dll-relocated', 'vm-stress')):
    failures.append('Baseline runs do not match the current out/eboot.bin')
result['emulator'] = manifest
result['emulator_patches_added'] = 0
result['console_bare_passed_in_fork'] = result['runs']['console-bare']['status'] == 'passed' and not [
    item for item in failures if item.startswith('console-bare')]
result['known_limits'] = ['Only preloaded modules for LoadLibraryA', 'Flat relative file names under /data',
                          'No PEB, SEH, heap or console handles', 'Wine path still blocked (increment 15)']
result['focused_regressions_passed'] = not failures
result['failures'] = failures
(out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
if failures:
    raise SystemExit('Unexpected result: ' + ', '.join(failures))
