#!/usr/bin/env python3
"""Summarize actual phases and publish an allowlisted diagnostic bundle on full success."""
import json
import os
from pathlib import Path
import shutil
from common import ROOT, RESULTS, sha, write_json


def main():
    phases = [json.loads(row) for row in (RESULTS / 'timings.jsonl').read_text().splitlines()] if (RESULTS / 'timings.jsonl').exists() else []
    path = RESULTS / 'matrix-report.json'
    report = json.loads(path.read_text()) if path.exists() else {'contract_passed': False, 'setup_error': 'No completed matrix report'}
    write_json(RESULTS / 'phase-timings.json', phases)
    summary = '# Platform matrix\n\n'
    summary += f"Profile: **{report.get('profile', 'unavailable')}**; contract passed: **{report['contract_passed']}**.\n\n"
    summary += f"Execution completed: **{report.get('execution_completed', False)}**; pending cases: **{len(report.get('pending_cases', []))}**.\n\n"
    if report.get('active_case'):
        summary += 'Interrupted while executing: `' + report['active_case'] + '`.\n\n'
    summary += 'Scope: own PE translator/loader and native service probes; **not Wine boot, a product release or PS4 acceptance**.\n\n'
    summary += '| Phase | Result | Seconds |\n| --- | --- | --- |\n'
    summary += '\n'.join(f"| {p['phase']} | {p['status']} | {p['duration_seconds']} |" for p in phases) + '\n\n'
    summary += '| Case | Expected | Matched | Seconds |\n| --- | --- | --- | --- |\n'
    summary += '\n'.join(f"| {c['id']} | {c['expected']} | {c['outcome_as_expected']} | {c['duration_seconds']} |" for c in report.get('cases', [])) + '\n'
    if report.get('setup_error'):
        summary += '\nSetup error: `' + report['setup_error'].replace('`', "'") + '`\n'
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(summary)
    if report.get('contract_passed') and report.get('profile') == 'platform-v1' and report.get('complete_profile'):
        target = ROOT / 'out/ci-diagnostics'
        if target.exists():
            raise SystemExit('Diagnostic bundle already exists; refusing to overwrite evidence')
        target.mkdir(parents=True)
        selected = [ROOT / 'out/eboot.bin', ROOT / 'out/ci-fixtures.json',
                    ROOT / 'build/ci-services/eboot.bin', ROOT / 'build/ci-services/manifest.json',
                    ROOT / 'build/shadPS4-linux/build-manifest.json', ROOT / 'out/build.json',
                    RESULTS / 'windows-reference.json', path,
                    ROOT / 'THIRD_PARTY.md', ROOT / 'LICENSES/GPL-2.0.txt', ROOT / 'LICENSES/LGPL-2.1.txt']
        fixture = json.loads((ROOT / 'out/ci-fixtures.json').read_text())
        selected += [ROOT / 'out' / name for name in fixture['artifacts'] if Path(name).suffix in ('.exe', '.dll')]
        hashes = {}
        for source in selected:
            rel = source.relative_to(ROOT)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            hashes[rel.as_posix()] = sha(dest)
        write_json(target / 'manifest.json', {'source_sha': report['source_sha'], 'files': hashes,
                   'scope': 'Tested diagnostics only; not OrbisDesk.pkg or a physical hardware release'})
        (target / 'README.txt').write_text('Diagnostic artifacts for the source revision in manifest.json.\n'
            'Use the documented emulator runner with out/eboot.bin for baseline cases, or build/ci-services/eboot.bin for services.\n'
            'This is not the complete OrbisDesk product distribution. Physical PS4 validation remains pending.\n')
        (target / 'SHA256SUMS').write_text(''.join(value + '  ' + name + '\n' for name, value in sorted(hashes.items())))
    print(summary)


if __name__ == '__main__':
    main()
