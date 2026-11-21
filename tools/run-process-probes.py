#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run bounded process probes; never interpret emulator discovery as native spawning."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'out/process-probes'
TEMP_BASE = Path('/var/tmp') if os.name == 'posix' else Path(tempfile.gettempdir())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_records(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['windows', 'host-wine', 'shad-capabilities', 'shad-family'], required=True)
    parser.add_argument('--build', default='W303')
    parser.add_argument('--control', action='store_true', help='Use a relocatable parent at 0x24000000')
    parser.add_argument('--resume-from', type=Path, help='Reuse only the private data of a previous shad-family report')
    parser.add_argument('--timeout', type=int, default=45)
    args = parser.parse_args()
    if not 5 <= args.timeout <= 180:
        parser.error('timeout must be 5..180 seconds')
    if args.target == 'windows' and os.name != 'nt':
        parser.error('windows reference requires Windows Python')
    if args.target != 'windows' and os.name != 'posix':
        parser.error('use WSL Python for Wine/shadPS4')
    if not (args.build.startswith('W') and args.build[1:].isdigit()):
        parser.error('build must be W followed by digits')
    if args.resume_from and args.target != 'shad-family':
        parser.error('resume-from is only for shad-family')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_dir = ROOT / 'reports/process-probes' / stamp
    report_dir.mkdir(parents=True)
    inputs = json.loads((ARTIFACTS / 'manifest.json').read_text())
    for name, expected in inputs['artifacts'].items():
        if sha(ARTIFACTS / name) != expected:
            raise RuntimeError('Changed artifact: ' + name)
    shutil.copyfile(ARTIFACTS / 'manifest.json', report_dir / 'probe-build.json')
    prior = json.loads(args.resume_from.read_text()) if args.resume_from else None
    if prior:
        work = Path(prior['working_directory']).resolve()
        if (prior['target'] != 'shad-family' or work.parent != TEMP_BASE.resolve()
                or not work.name.startswith('orbisdesk-process-') or not (work / 'data').is_dir()
                or prior['fixture_build']['artifacts'] != inputs['artifacts']):
            raise RuntimeError('Resume input is not a matching private process-probe run')
    else:
        work = Path(tempfile.mkdtemp(prefix='orbisdesk-process-', dir=TEMP_BASE))
    data = work / 'data'
    family = data / 'wine-prefix/drive_c/orbis/process-probe'
    emulator = None
    if args.target == 'shad-family':
        release = json.loads((ROOT / f'out/wine-hardware-{args.build.lower()}/manifest.json').read_text())
        app = ROOT / f'build/wine-hardware-{args.build.lower()}/app'
        if sha(app / 'eboot.bin') != release['eboot_sha256']:
            raise RuntimeError('Release eboot differs from manifest')
        shutil.copyfile(ROOT / f'out/wine-hardware-{args.build.lower()}/manifest.json', report_dir / 'product-build.json')
        if prior:
            previous_release = json.loads((args.resume_from.parent / 'product-build.json').read_text())
            if previous_release['eboot_sha256'] != release['eboot_sha256']:
                raise RuntimeError('Cannot resume data from a different release')
        else:
            shutil.copytree(ROOT / release['runtime_root'], data, symlinks=True)
    family.mkdir(parents=True, exist_ok=True)
    for name in ('family-parent.exe', 'family-child.exe', 'family-control.exe'):
        shutil.copyfile(ARTIFACTS / name, family / name)
    for name in ('parent.jsonl', 'child.jsonl'):
        if (family / name).exists():
            shutil.move(str(family / name), str(report_dir / ('previous-' + name)))
    parent = 'family-control.exe' if args.control else 'family-parent.exe'
    env = dict(os.environ)
    wine = ROOT / '.deps/wine/runtime/build'
    if args.target == 'windows':
        command = [str(family / parent)]
    elif args.target == 'host-wine':
        env.update(WINEPREFIX=str(work / 'host-prefix'), WINEDEBUG='-all,err+all', WINEDLLOVERRIDES='winemenubuilder.exe=d')
        command = [str(wine / 'loader/wine'), str(family / parent)]
    else:
        emulator = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
        if sha(ROOT / 'build/shadPS4-linux/shadps4') != emulator['executable_sha256']:
            raise RuntimeError('Emulator binary differs from manifest')
        if prior and prior['emulator']['executable_sha256'] != emulator['executable_sha256']:
            raise RuntimeError('Cannot resume data with a different emulator')
        shutil.copyfile(ROOT / 'build/shadPS4-linux/build-manifest.json', report_dir / 'emulator-build.json')
        # LoadExec restarts currently drop CLI mounts. Keep even that path inside this run.
        user = work / 'xdg/shadPS4'
        user.mkdir(parents=True, exist_ok=True)
        default_data = user / 'data'
        if default_data.is_symlink():
            if default_data.resolve() != data.resolve():
                raise RuntimeError('Private emulator data link points outside this run')
        elif default_data.exists():
            raise RuntimeError('Unexpected existing private emulator data directory')
        else:
            default_data.symlink_to(data, target_is_directory=True)
        env['XDG_DATA_HOME'] = str(work / 'xdg')
        if args.target == 'shad-family':
            (data / 'orbisdesk').mkdir(exist_ok=True)
            (data / 'orbisdesk/launch.txt').write_text('C:\\orbis\\process-probe\\' + parent + '\n')
            game = app / 'eboot.bin'
        else:
            game = ARTIFACTS / 'eboot.bin'
        command = ['python3', str(ROOT / 'tools/run-linux-shad.py'), '--fork', '--config-clean',
                   '--fullscreen', 'false', '--mount', str(data), '/data', '-g', str(game)]
    start = time.monotonic()
    (report_dir / 'preparation.json').write_text(json.dumps({
        'target': args.target, 'working_directory': str(work), 'command': command,
        'resumed_from': str(args.resume_from) if args.resume_from else None,
    }, indent=2) + '\n')
    timed_out = False
    with (report_dir / 'stdout.log').open('w') as out, (report_dir / 'stderr.log').open('w') as err:
        def no_core():
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        proc = subprocess.Popen(command, cwd=work, env=env, stdout=out, stderr=err,
                                start_new_session=os.name == 'posix',
                                preexec_fn=no_core if os.name == 'posix' else None)
        try:
            code = proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'posix':
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            code = proc.wait()
    if args.target == 'host-wine':
        subprocess.run([str(wine / 'server/wineserver'), '-k'], env=env, capture_output=True, timeout=10)
        subprocess.run([str(wine / 'server/wineserver'), '-w'], env=env, capture_output=True, timeout=10)
    parent_records = read_records(family / 'parent.jsonl')
    child_records = read_records(family / 'child.jsonl')
    native_records = read_records(data / 'process-capabilities.jsonl')
    for path in (family / 'parent.jsonl', family / 'child.jsonl', data / 'process-capabilities.jsonl'):
        if path.is_file():
            shutil.copyfile(path, report_dir / path.name)
    if emulator:
        user_log = work / 'xdg/shadPS4/log'
        if user_log.is_dir():
            shutil.copytree(user_log, report_dir / 'emulator-user-log')
    # The real fixture result is distinct from an emulator title's own exit or forced timeout.
    parent_ok = any(r['event'] == 'family_verified' for r in parent_records)
    child_ok = any(r['event'] == 'child_verified' for r in child_records)
    parent_exit = next((r['detail'] for r in reversed(parent_records) if r['event'] == 'exit'), None)
    child_exit = next((r['detail'] for r in reversed(child_records) if r['event'] == 'exit'), None)
    family_passed = parent_ok and child_ok and parent_exit == 0 and child_exit == 42
    source = ROOT / '.deps/shadPS4-fork/src/core/libraries'
    report = {
        'schema_version': 1, 'target': args.target, 'control': args.control,
        'status': 'passed' if family_passed else 'blocked',
        'classification': 'fork_emulator' if args.target.startswith('shad-') else 'host_reference',
        'hardware_status': 'pending', 'native_spawn_implemented': False,
        'family_contract_passed': family_passed,
        'capability_discovery_completed': any(r.get('event') == 'complete' for r in native_records),
        'ps4_native_child_started': False,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'fixture_build': inputs, 'command': command, 'exit_code': code, 'timed_out': timed_out,
        'duration_seconds': round(time.monotonic() - start, 3), 'working_directory': str(work),
        'resumed_from': str(args.resume_from) if args.resume_from else None,
        'parent_records': parent_records, 'child_records': child_records, 'native_records': native_records,
        'emulator': emulator,
        'emulator_user_directory': str(work / 'xdg/shadPS4') if emulator else None,
        'runner_sha256': sha(Path(__file__).resolve()),
        'emulator_process_source_sha256': sha(source / 'kernel/process.cpp') if emulator else None,
        'emulator_systemservice_source_sha256': sha(source / 'system/systemservice.cpp') if emulator else None,
    }
    (report_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('target', 'status', 'family_contract_passed',
          'capability_discovery_completed', 'exit_code', 'timed_out', 'duration_seconds')}))
    print(report_dir / 'report.json')
    return 0 if family_passed or report['capability_discovery_completed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
