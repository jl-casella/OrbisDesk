#!/usr/bin/env python3
"""Execute the versioned diagnostic contract with fresh processes and real outcomes."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from common import ROOT, RESULTS, phase, revision, sha, write_json

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def records(text, marker):
    return [json.loads(value) for value in re.findall(marker + r' (\{[^\r\n]+\})', text)]


def evaluate(spec, text, exit_code, timed_out, reference_matches=True):
    errors = []
    if re.search(r'\bStub: [^\r\n(]+ \(nid:', text):
        errors.append('invoked-emulator-stub')
    if re.search(r'unhandled access violation', text, re.I):
        errors.append('unhandled-access-violation')
    if not reference_matches:
        errors.append('windows-reference-output-differs')
    if spec['kind'] == 'baseline':
        events = records(text, 'PWPS4')
        starts = [v for v in events if v.get('event') == 'start' and v.get('case') == spec['case']]
        ends = [v for v in events if v.get('event') == 'result' and v.get('case') == spec['case']]
        if len(starts) != 1 or len(ends) != 1 or ends[0].get('status') != 'passed' or ends[0].get('code') != 0:
            errors.append('guest-result-contract')
        if spec['expected'] == 'blocked':
            if not timed_out or spec['blocker'] not in text:
                errors.append('official-blocker-signature-differs')
        elif timed_out or exit_code != spec['exit_code']:
            errors.append('process-exit-or-timeout')
    else:
        observed = records(text, 'PWSERVICE')
        names = [v.get('case') for v in observed]
        if (sorted(names) != sorted(spec['assertions']) or
                any(v.get('status') != 'passed' for v in observed)):
            errors.append('service-assertions-differ')
        end = records(text, 'PWCI')
        if end != [{'case': spec['case'], 'exit_code': 0}] or timed_out or exit_code != 0:
            errors.append('service-process-exit-or-timeout')
    return errors


def execute(spec, fixtures, references, emulator):
    folder = RESULTS / 'cases' / spec['id']
    folder.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='orbisdesk-ci-') as temporary:
        work = Path(temporary)
        data = work / 'data'
        (data / 'orbisdesk').mkdir(parents=True)
        for name in fixtures['artifacts']:
            if Path(name).name != name:
                raise ValueError('Invalid fixture filename')
            if Path(name).suffix in ('.exe', '.dll'):
                shutil.copyfile(ROOT / 'out' / name, data / name)
        for name, filename in [('console-bare', 'console-bare-reference.txt'), ('console32', 'console32-reference.txt')]:
            (data / filename).write_bytes(base64.b64decode(references['references'][name]['result_base64'], validate=True))
        if spec['case'] == 'metadata':
            meta = data / 'metadata'
            (meta / 'dir').mkdir(parents=True)
            (meta / 'sample.bin').write_bytes(b'payload')
            (meta / 'other.bin').write_bytes(b'payload')
            os.link(meta / 'sample.bin', meta / 'hard.bin')
            for name, target in [('file-link', 'sample.bin'), ('dir-link', 'dir'), ('dangling', 'missing')]:
                (meta / name).symlink_to(target)
        guest = work / 'guest'
        guest.mkdir()
        source = ROOT / ('out/eboot.bin' if spec['kind'] == 'baseline' else 'build/ci-services/eboot.bin')
        shutil.copyfile(source, guest / 'eboot.bin')
        # Keep the original compiler/SDK-import ELF byte-for-byte; no runtime patching.
        guest_args = ['--case', spec['case']] if spec['kind'] == 'baseline' else [spec['case']]
        command = [sys.executable, str(ROOT / 'tools/run-linux-shad.py')]
        if spec['emulator'] == 'fork':
            command += ['--fork']
        command += ['--config-clean', '--fullscreen', 'false', '--mount', str(data), '/data',
                    '-g', str(guest / 'eboot.bin'), '--', '/app0/eboot.bin', *guest_args]
        (work / 'config').mkdir()
        (work / 'share').mkdir()
        env = dict(os.environ, XDG_CONFIG_HOME=str(work / 'config'), XDG_DATA_HOME=str(work / 'share'))
        start = time.monotonic()
        with (folder / 'stdout.log').open('w') as stdout, (folder / 'stderr.log').open('w') as stderr:
            proc = subprocess.Popen(command, cwd=work, stdout=stdout, stderr=stderr, env=env,
                                    start_new_session=True,
                                    preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            timed_out = False
            try:
                proc.wait(timeout=spec['timeout_seconds'])
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        text = ANSI.sub('', (folder / 'stdout.log').read_text(errors='replace') +
                        (folder / 'stderr.log').read_text(errors='replace'))
        output_matches = True
        if spec['case'] in ('console32', 'console-bare'):
            produced = data / 'orbisdesk' / spec['case'] / 'result.txt'
            actual = produced.read_bytes() if produced.is_file() else None
            expected = base64.b64decode(references['references'][spec['case']]['result_base64'], validate=True)
            output_matches = actual == expected
            if actual is not None:
                (folder / 'result.txt').write_bytes(actual)
        errors = evaluate(spec, text, proc.returncode, timed_out, output_matches)
        result = {'id': spec['id'], 'expected': spec['expected'], 'errors': errors,
                  'outcome_as_expected': not errors, 'observed': spec['expected'] if not errors else 'failed',
                  'exit_code': proc.returncode, 'timed_out': timed_out,
                  'duration_seconds': round(time.monotonic() - start, 3),
                  'elf_sha256': sha(source), 'emulator_kind': spec['emulator'],
                  'emulator_sha256': emulator['executable_sha256'] if spec['emulator'] == 'fork' else
                      sha(ROOT / '.deps/shadPS4-linux/squashfs-root/usr/bin/shadps4'),
                  'reference_output_matches': output_matches}
        write_json(folder / 'report.json', result)
        print(json.dumps(result), flush=True)
        return result


def main():
    global RESULTS
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=('platform-v1', 'platform-core'), default='platform-v1')
    parser.add_argument('--case', action='append', help='Local focused run only; report is explicitly incomplete')
    parser.add_argument('--report-dir', type=Path, default=RESULTS)
    args = parser.parse_args()
    RESULTS = args.report_dir.resolve()
    if not RESULTS.is_relative_to(ROOT / 'reports'):
        parser.error('Report directory must be under reports/')
    import common
    common.RESULTS = RESULTS
    report = {'schema_version': 1, 'source_sha': revision(), 'profile': args.profile,
              'scope': 'Own PE translator/loader and native services, not Wine boot or product validation',
              'Wine_booted': False, 'hardware_status': 'pending', 'contract_passed': False,
              'complete_profile': not bool(args.case), 'cases': [], 'setup_error': None}
    try:
        fixtures = json.loads((ROOT / 'out/ci-fixtures.json').read_text())
        references = json.loads((ROOT / 'reports/ci/windows-reference.json').read_text(encoding='utf-8-sig'))
        if fixtures['source_sha'] != revision() or references['source_sha'] != revision():
            raise ValueError('Fixture/reference source revision differs from checkout')
        if references['fixture_manifest_sha256'] != sha(ROOT / 'out/ci-fixtures.json'):
            raise ValueError('Reference fixture manifest differs')
        for name, entry in fixtures['artifacts'].items():
            if Path(name).name != name or sha(ROOT / 'out' / name) != entry['sha256']:
                raise ValueError('Fixture differs: ' + name)
        for entry in references['references'].values():
            if sha(ROOT / 'out' / entry['exe']) != entry['exe_sha256']:
                raise ValueError('Reference EXE differs')
        emulator = json.loads((ROOT / 'build/shadPS4-linux/build-manifest.json').read_text())
        if sha(ROOT / 'build/shadPS4-linux/shadps4') != emulator['executable_sha256']:
            raise ValueError('Fork emulator binary differs')
        services = json.loads((ROOT / 'build/ci-services/manifest.json').read_text())
        if sha(ROOT / 'build/ci-services/eboot.bin') != services['elf_sha256']:
            raise ValueError('Service ELF differs')
        baseline = json.loads((ROOT / 'out/build.json').read_text())
        if sha(ROOT / 'out/eboot.bin') != baseline['artifacts']['eboot.bin']['sha256']:
            raise ValueError('Diagnostic ELF differs')
        contract_path = ROOT / 'tests/ci-matrix.json'
        report.update(contract_sha256=sha(contract_path), emulator=emulator,
                      official_emulator=json.loads((ROOT / 'linux-emulator.lock.json').read_text()),
                      locks={p.name: sha(p) for p in ROOT.glob('*.lock.json')},
                      fixture_manifest_sha256=sha(ROOT / 'out/ci-fixtures.json'),
                      checkout_dirty=bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'])))
        cases = json.loads(contract_path.read_text())['cases']
        if len(cases) != 31 or len({case['id'] for case in cases}) != 31:
            raise ValueError('platform-v1 must contain exactly 31 distinct top-level cases')
        if args.profile == 'platform-core':
            cases = [case for case in cases if case['kind'] == 'baseline']
        expected_count = len(cases)
        if args.case:
            if set(args.case) - {c['id'] for c in cases}:
                raise ValueError('Unknown case selector')
            cases = [case for case in cases if case['id'] in args.case]
        with phase('matrix-execution') as timing:
            for case in cases:
                report['cases'].append(execute(case, fixtures, references, emulator))
            timing['failed'] = any(not case['outcome_as_expected'] for case in report['cases'])
        report['contract_passed'] = (not args.case and len(report['cases']) == expected_count and
                                     all(case['outcome_as_expected'] for case in report['cases']))
    except Exception as exc:
        report['setup_error'] = str(exc)
        raise
    finally:
        write_json(RESULTS / 'matrix-report.json', report)
    raise SystemExit(0 if (not report['setup_error'] and report['cases'] and
                          all(c['outcome_as_expected'] for c in report['cases'])) else 1)


if __name__ == '__main__':
    main()
