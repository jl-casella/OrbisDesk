#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify prefix consumption separately from Wine startup and Windows execution."""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',action='store_true',help='Collect the already executed increment19 build logs')
args=parser.parse_args()
out=ROOT/'reports/increment19';out.mkdir(parents=True,exist_ok=True)
previous=json.loads((out/'report.json').read_text()) if args.verify_only else None
package=['--prepared-prefix','reports/increment15/prefix-package']
cases=[('preflight-fork',['--fork',*package,'--prefix-preflight']),
       ('preflight-official',[*package,'--prefix-preflight']),
       ('prepared-wine',['--fork',*package]),('services',['--fork','--services']),
       ('gs',['--fork','--gs-services']),('empty-wine',['--fork','--exe','out/console32-bare.exe'])]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(command,log):
    with log.open('w') as output:subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)

if not args.verify_only and not args.collect_existing:
    run([sys.executable,'tools/check-wine-prefix.py'],ROOT/'build/increment19-prefix-contract-final.log')
    run([sys.executable,'tools/check-increment18.py','--report-dir','reports/increment19/regressions-18'],ROOT/'build/increment19-regressions-18.log')
    run([sys.executable,'tools/reproduce-wine-mmap.py'],ROOT/'build/increment19-mmap-reproduction.log')
failures=[];runs={};reports={}
for name,options in cases:
    if args.verify_only:
        path=ROOT/previous['runs'][name]['report']
    else:
        log=ROOT/('build/increment19-'+name+'.log')
        if not args.collect_existing:run([sys.executable,'tools/run-linux-wine.py',*options],log)
        path=pathlib.Path(log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),
                'status':report['status'],'stages':report['stages'],
                'guest_exit_status_hex':report['guest_exit_status_hex']}
    if args.verify_only and sha(path)!=previous['runs'][name]['report_sha256']:
        failures.append(name+': report changed')
    if report['Wine_booted'] or report['windows_execution_verified']:
        failures.append(name+': unexpected execution claim')
    if report.get('host_ld_preload'):failures.append(name+': LD_PRELOAD used')
    log=(path.parent/'stdout.log').read_text(errors='replace')
    known_mapping_block=name=='prepared-wine' and 'mmap failed: Invalid argument' in log and 'phys_addr = 0xc00' in log
    if name!='preflight-official' and not known_mapping_block and (report['timed_out'] or report['unhandled_access_violation']):
        failures.append(name+': timeout or unhandled fault')

expected={'prefix-'+name for name in ('system-registry','user-registry','userdef-registry',
    'drive-c','drive-z','drive-resolution','drive-z-resolution','file-identity','exe-pe32',
    'dll-pe64','dll-pe32','host-cpu-absent')}
preflight=reports['preflight-fork'];prepared=reports['prepared-wine'];official=reports['preflight-official']
prepared_log=(ROOT/runs['prepared-wine']['report']).parent.joinpath('stdout.log').read_text(errors='replace')
mapping_assertion='mmap failed: Invalid argument' in prepared_log and 'phys_addr = 0xc00' in prepared_log
if not mapping_assertion:failures.append('Prepared Wine did not reproduce the recorded mmap blocker')
if (preflight['status']!='passed' or not preflight['prefix_preflight_passed'] or
        preflight['unix_entry_reached'] or preflight['external_prefix_policy_used'] or
        {entry['case'] for entry in preflight['service_results']}!=expected or
        any(entry['status']!='passed' for entry in preflight['service_results'])):
    failures.append('Fork preflight contract')
if official['status']!='blocked' or official['unix_entry_reached']:
    failures.append('Official preflight contract')
if (prepared['status']!='blocked' or not prepared['prefix_preflight_passed'] or
        not prepared['unix_entry_reached'] or not prepared['external_prefix_policy_used'] or
        'process_spawn_blocked' in prepared['stages']):
    failures.append('Prepared prefix startup contract')
empty=reports['empty-wine']
if (empty['guest_exit_status_hex']!='0xc0000135' or 'process_spawn_blocked' not in empty['stages'] or
        empty['external_prefix_policy_used'] or empty['prefix_preflight_passed']):
    failures.append('Empty prefix behavior changed')
historical=json.loads((ROOT/'reports/increment15/report.json').read_text())
for name in ('services','gs'):
    old=json.loads((ROOT/historical['runs'][name]['report']).read_text())
    actual=reports[name]
    if actual['status']!=old['status'] or actual['service_results']!=old['service_results']:
        failures.append(name+': diagnostic changed')
manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
for name,report in reports.items():
    if report['elf_sha256']!=preflight['elf_sha256']:failures.append(name+': ELF mismatch')
    if name!='preflight-official' and report['emulator_sha256']!=manifest['executable_sha256']:
        failures.append(name+': emulator mismatch')
    if name in ('preflight-fork','preflight-official','prepared-wine') and report['prefix_package']!=preflight['prefix_package']:
        failures.append(name+': prefix mismatch')
contract=json.loads((out/'prefix-contract.json').read_text())
if contract['status']!='passed' or len(contract['cases'])!=9:failures.append('Package negative tests')
for relative,digest in contract['inputs'].items():
    if sha(ROOT/relative)!=digest:failures.append('Contract input changed: '+relative)
regressions=json.loads((out/'regressions-18/report.json').read_text())
if not regressions['focused_regressions_passed'] or regressions['failures']:failures.append('Increment18 regressions')
reproduction=json.loads((out/'mmap-reproducer/report.json').read_text())
for name,report in reproduction['runs'].items():
    if (report['status']!='blocked' or not report['request_reached'] or report['return_reached'] or
            not report['mmap_assertion'] or report['elf_sha256']!=reproduction['elf_sha256']):
        failures.append(name+': mmap reproduction changed')
for relative,digest in reproduction['inputs'].items():
    if sha(ROOT/relative)!=digest:failures.append('Mmap reproduction input changed: '+relative)
result={'schema_version':1,'status':'passed' if not failures else 'failed',
    'scope':'Prepared prefix verified in guest; Wine execution remains blocked',
    'prefix_preflight_passed':preflight['prefix_preflight_passed'],
    'external_prefix_policy_used':prepared['external_prefix_policy_used'],
    'Wine_booted':False,'windows_execution_verified':False,'hardware_status':'pending',
    'validation':{'prefix':'validated-in-fork','official':'blocked','hardware':'pending'},
    'runs':runs,'failures':failures,'emulator':manifest,
    'regressions_report':'reports/increment19/regressions-18/report.json',
    'regressions_report_sha256':sha(out/'regressions-18/report.json'),
    'prefix_contract_sha256':sha(out/'prefix-contract.json'),
    'mmap_reproduction_sha256':sha(out/'mmap-reproducer/report.json'),
    'startup_blocker':{'operation':'Private image file mmap at offset 0xc00','emulator_assertion':mapping_assertion,
        'ntdll_pe64_ready':'ntdll_pe64_ready' in prepared['stages'],
        'reproduction':'reports/increment19/mmap-reproducer/report.json'},
    'remaining_requirements':['Return mmap alignment errors instead of asserting; verify Wine read fallback',
        'Investigate dispatcher-mixed on Linux','GS per-thread semantics',
        'WoW64 CPU provider integration','Execute the console fixture through actual Wine DLLs']}
if args.verify_only and any(result[key]!=previous[key] for key in ('regressions_report_sha256','prefix_contract_sha256','mmap_reproduction_sha256')):
    failures.append('Saved regression or contract report changed');result['status']='failed'
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
print(out/'report.json')
if failures:raise SystemExit('Unexpected results: '+', '.join(failures))
