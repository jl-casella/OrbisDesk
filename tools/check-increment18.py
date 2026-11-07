#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run console32.exe (mingw CRT) without Wine in both emulators and repeat the regressions."""
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
parser.add_argument('--report-dir', type=pathlib.Path, default=ROOT/'reports/increment18')
args = parser.parse_args()
if os.environ.get('LD_PRELOAD'):
    raise SystemExit('Final checks require the linked binary without LD_PRELOAD')
out = args.report_dir.resolve()
if not out.is_relative_to(ROOT/'reports'):
    raise SystemExit('Report directory must be inside reports')
out.mkdir(parents=True, exist_ok=True)
previous = json.loads((out / 'report.json').read_text()) if args.verify_only else None
reference = json.loads((ROOT / 'reports/increment18-windows-reference/report.json').read_text())
result = {'schema_version': 1, 'Wine_booted': False, 'Wine_used': False,
          'windows_execution_verified': False, 'hardware_status': 'pending',
          'windows_reference': reference, 'runs': {},
          'scope': 'console32.exe with the mingw CRT through the own PE32 loader, a minimal kernel32 and a '
                   'minimal msvcrt; no Wine'}
# The official Linux release completes the guest, then asserts in process.cpp exit and never terminates.
cases = [('console32', ['--fork', '--baseline', '--case', 'console32'], 'passed'),
         ('console32-official', ['--baseline', '--case', 'console32'], 'blocked'),
         ('console-bare', ['--fork', '--baseline', '--case', 'console-bare'], 'passed'),
         ('lifecycle-host', ['--fork', '--baseline', '--case', 'lifecycle-host'], 'passed')]
# Loader (sections, EXE TLS), lifecycle and CPU fallback changed: repeat every PE case of increments 4-7.
cases += [(name, ['--fork', '--baseline', '--case', name], 'passed') for name in
          ('pe-preferred', 'pe-relocated', 'pe-invalid', 'pe-collision', 'pe-fourk-preferred', 'pe-fourk-relocated',
           'pe-subpage', 'pe-dll-preferred', 'pe-dll-relocated', 'pe-dll-missing', 'pe-dll-symbol', 'pe-dll-ordinal',
           'pe-dll-invalid', 'pe-dll-dependency', 'pe-init-order', 'pe-init-relocated', 'pe-init-failure',
           'pe-tls-threads', 'pe-tls-invalid', 'pe-process',
           'files', 'threads-adapter', 'vm-stress')]
# dispatcher-mixed fails on the Linux fork with the increment 17 ELF as well (same
# detail line); it was validated on the Windows fork in increment 3 and is
# tracked separately, not as a regression of this increment.
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
# Host-visible calls of the mingw start-up, main and exit paths, from the
# successful fork run; any change means the CRT took a different path.
expected_calls = {'InitializeCriticalSection': 1, '__set_app_type': 1, '__p__fmode': 1, '__p__commode': 1,
                  '__lconv_init': 1, '_initterm': 2, '__getmainargs': 1, 'SetUnhandledExceptionFilter': 1,
                  '__p__acmdln': 1, 'malloc': 2, 'strlen': 1, 'memcpy': 1, 'GetModuleHandleA': 1, '_onexit': 2,
                  'CreateThread': 1, 'EnterCriticalSection': 2, 'LeaveCriticalSection': 2, 'WaitForSingleObject': 1,
                  'GetExitCodeThread': 1, 'CloseHandle': 2, 'LoadLibraryA': 1, 'GetProcAddress': 1, 'FreeLibrary': 1,
                  'CreateFileA': 1, 'WriteFile': 1, 'exit': 1, 'DeleteCriticalSection': 1}
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
    if name.startswith('console32'):
        trace = report.get('k32_trace', [])
        calls = {}
        for entry in trace:
            if 'call' in entry:
                calls[entry['call']] = calls.get(entry['call'], 0) + 1
        detail = [line.split('PWPS4 ', 1)[-1] for line in log.splitlines()
                  if '"case":"console32","status":"passed"' in line]
        refusals = [entry for entry in trace if 'refused' in entry or 'fault' in entry]
        result['runs'][name].update({'guest_exit_code': report['guest_exit_code'], 'calls': calls,
                                     'invoked_stubs': report['invoked_stubs'], 'crt_output': report.get('crt_output'),
                                     'result_matches_windows_reference': report['console_result_matches_windows_reference'],
                                     'refusals': refusals, 'detail': detail[0] if detail else None})
        if (report['console_exe_sha256'] != reference['exe_sha256'] or not report['console_result_matches_windows_reference'] or
                calls != expected_calls or report['invoked_stubs'] or refusals or not detail or
                'refused=0 leaked=0' not in detail[0] or 'live=0' not in detail[0]):
            failures.append(name + ': differs from the Windows reference contract')
        if not official and (report['guest_exit_code'] != reference['exit_code'] or report['exit_code'] != reference['exit_code']):
            failures.append(name + ': exit code differs from Windows')
        if official and (not report['baseline_guest_passed'] or not report['timed_out'] or
                         'process.cpp:312 exit: Unreachable code!' not in log):
            failures.append(name + ': unexpected official blocker')
    result['failures'] = failures
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(name + ': ' + report['status'] + ' (' + str(report_path) + ')', flush=True)

manifest = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
if any(entry['emulator_sha256'] != manifest['executable_sha256'] for entry in result['runs'].values()
       if entry['emulator_kind'] == 'local Linux fork'):
    failures.append('Runs do not match the current emulator')
build = json.loads((ROOT / 'out/build.json').read_text())
if build['artifacts']['console32.exe']['sha256'] != reference['exe_sha256']:
    failures.append('Built console32.exe differs from the Windows reference')
elf = hashlib.sha256((ROOT / 'out/eboot.bin').read_bytes()).hexdigest()
baseline = [name for name, options, _ in cases if '--baseline' in options]
if any(result['runs'][name]['elf_sha256'] != elf for name in baseline):
    failures.append('Baseline runs do not match the current out/eboot.bin')
result['emulator'] = manifest
result['emulator_patches_added'] = 0
result['official_blocker'] = 'Guest passes; emulator asserts in process.cpp exit and times out'
result['console32_passed_in_fork'] = result['runs']['console32']['status'] == 'passed' and not [
    item for item in failures if item.startswith('console32:')]
result['known_limits'] = ['msvcrt subset: start-up, exit, heap, memcpy/strlen/strncmp, stdout/stderr text only',
                          'printf conversions limited to %s %d %i %u %x %X %p %c', 'VirtualProtect refused',
                          'SetUnhandledExceptionFilter recorded, never invoked (no SEH)', 'TlsAlloc not served',
                          'DLL providers must be import-free (pw_pe32_link)', 'Wine path still blocked (increment 15)']
result['focused_regressions_passed'] = not failures
result['failures'] = failures
(out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
if failures:
    raise SystemExit('Unexpected result: ' + ', '.join(failures))
