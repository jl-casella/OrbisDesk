#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run lifecycle-host.exe without Wine in both emulators and repeat the regressions."""
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
out = ROOT / 'reports/increment17'
out.mkdir(parents=True, exist_ok=True)
previous = json.loads((out / 'report.json').read_text()) if args.verify_only else None
reference = json.loads((ROOT / 'reports/increment17-windows-reference/report.json').read_text())
result = {'schema_version': 1, 'Wine_booted': False, 'Wine_used': False,
          'windows_execution_verified': False, 'hardware_status': 'pending',
          'windows_reference': reference, 'runs': {},
          'scope': 'lifecycle-host.exe loads DLLs from /data through the own PE32 loader, the dynamic '
                   'lifecycle and a minimal kernel32; no Wine'}
# The official Linux release completes the guest, then asserts in process.cpp exit and never terminates.
cases = [('lifecycle-host', ['--fork', '--baseline', '--case', 'lifecycle-host'], 'passed'),
         ('lifecycle-host-official', ['--baseline', '--case', 'lifecycle-host'], 'blocked'),
         ('console-bare', ['--fork', '--baseline', '--case', 'console-bare'], 'passed')]
# The lifecycle changed: repeat every increment 7 case, then the increment 16 set.
cases += [(name, ['--fork', '--baseline', '--case', name], 'passed') for name in
          ('pe-init-order', 'pe-init-relocated', 'pe-init-failure', 'pe-tls-threads', 'pe-tls-invalid',
           'files', 'threads-adapter', 'pe-dll-relocated', 'vm-stress')]
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
# The EXE checks DLL event order itself; these are the host-visible calls.
expected_calls = {'LoadLibraryA': 2, 'GetProcAddress': 3, 'CreateThread': 1, 'WaitForSingleObject': 1,
                  'GetExitCodeThread': 1, 'CloseHandle': 1, 'FreeLibrary': 1, 'SetLastError': 1, 'GetLastError': 1}
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
    log = (report_path.parent / 'stdout.log').read_text(errors='replace')
    result['runs'][name] = {'report': str(report_path.relative_to(ROOT)), 'status': report['status'],
                            'emulator_kind': report['emulator_kind'], 'elf_sha256': report['elf_sha256'],
                            'emulator_sha256': report.get('emulator_sha256')}
    official = name.endswith('-official')
    if report['status'] != expected or (report['timed_out'] and not official):
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
    if name.startswith('lifecycle-host'):
        trace = report.get('k32_trace', [])
        calls = {}
        for entry in trace:
            if 'call' in entry:
                calls[entry['call']] = calls.get(entry['call'], 0) + 1
        detail = [line.split('PWPS4 ', 1)[-1] for line in log.splitlines()
                  if '"case":"lifecycle-host","status":"passed"' in line]
        result['runs'][name].update({'guest_exit_code': report['guest_exit_code'], 'kernel32_calls': calls,
                                     'invoked_stubs': report['invoked_stubs'],
                                     'windows_reference_inputs_match': report.get('windows_reference_inputs_match'),
                                     'refusals': [entry for entry in trace if 'refused' in entry or 'fault' in entry],
                                     'detail': detail[0] if detail else None})
        if (not report.get('windows_reference_inputs_match') or calls != expected_calls or report['invoked_stubs'] or
                result['runs'][name]['refusals'] or not detail or 'exit=42' not in detail[0] or
                'notifications=12' not in detail[0] or 'refused=0 leaked=0' not in detail[0] or
                'init_failures=1' not in detail[0] or 'live=0' not in detail[0]):
            failures.append(name + ': differs from the Windows reference contract')
        if not official and (report['guest_exit_code'] != reference['exit_code'] or report['exit_code'] != reference['exit_code']):
            failures.append(name + ': exit code differs from Windows')
        if official and (not report['baseline_guest_passed'] or not report['timed_out'] or
                         'process.cpp:312 exit: Unreachable code!' not in log):
            failures.append(name + ': unexpected official blocker')
    if name == 'console-bare' and not report['console_result_matches_windows_reference']:
        failures.append(name + ': result.txt differs from Windows')
    result['failures'] = failures
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(name + ': ' + report['status'] + ' (' + str(report_path) + ')', flush=True)

manifest = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
if any(entry['emulator_sha256'] != manifest['executable_sha256'] for entry in result['runs'].values()
       if entry['emulator_kind'] == 'local Linux fork'):
    failures.append('Runs do not match the current emulator')
build = json.loads((ROOT / 'out/build.json').read_text())
for filename, digest in reference['inputs'].items():
    if build['artifacts'][filename]['sha256'] != digest:
        failures.append('Built ' + filename + ' differs from the Windows reference')
elf = hashlib.sha256((ROOT / 'out/eboot.bin').read_bytes()).hexdigest()
baseline = [name for name, options, _ in cases if '--baseline' in options]
if any(result['runs'][name]['elf_sha256'] != elf for name in baseline):
    failures.append('Baseline runs do not match the current out/eboot.bin')
result['emulator'] = manifest
result['emulator_patches_added'] = 0
result['official_blocker'] = 'Guest passes; emulator asserts in process.cpp exit and times out'
result['lifecycle_host_passed_in_fork'] = result['runs']['lifecycle-host']['status'] == 'passed' and not [
    item for item in failures if item.startswith('lifecycle-host:')]
result['known_limits'] = ['DLL providers must be import-free (pw_pe32_link)', 'No loader re-entry from DllMain',
                          'Translated-block cache is not invalidated when a DLL is unloaded',
                          'No PEB, SEH, heap or console handles', 'Wine path still blocked (increment 15)']
result['focused_regressions_passed'] = not failures
result['failures'] = failures
(out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
if failures:
    raise SystemExit('Unexpected result: ' + ', '.join(failures))
