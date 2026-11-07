#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validate mmap rejection and actual Wine image loading independently of EXE execution."""
import argparse,hashlib,json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',action='store_true');args=parser.parse_args()
out=ROOT/'reports/increment20';out.mkdir(parents=True,exist_ok=True)
previous=json.loads((out/'report.json').read_text()) if args.verify_only else None
package=['--prepared-prefix','reports/increment15/prefix-package']
cases=[('preflight-fork',['--fork',*package,'--prefix-preflight']),
       ('prepared-relocated',['--fork',*package]),('services',['--fork','--services']),
       ('gs',['--fork','--gs-services']),('empty-wine',['--fork','--exe','out/console32-bare.exe'])]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def execute(command,path):
    with path.open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
if not args.verify_only and not args.collect_existing:
    execute([sys.executable,'tools/check-wine-mmap20.py','--official'],ROOT/'build/increment20-mmap-final.log')
    execute([sys.executable,'tools/reproduce-wine-file-protect.py'],ROOT/'build/increment20-protect-reproduction.log')
    execute([sys.executable,'tools/check-increment18.py','--report-dir','reports/increment20/regressions-18'],ROOT/'build/increment20-regressions-18.log')
failures=[];runs={};reports={};logs={}
manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
lock=json.loads((ROOT/'fork.lock.json').read_text())
if manifest['source_dirty'] or manifest['commit']!=lock['commit'] or sha(ROOT/'build/shadPS4-linux/shadps4')!=manifest['executable_sha256']:
    failures.append('Emulator is not the pinned clean build')
for name,options in cases:
    if args.verify_only:path=ROOT/previous['runs'][name]['report']
    else:
        runner_log=ROOT/('build/increment20-'+name+'.log')
        if not args.collect_existing:execute([sys.executable,'tools/run-linux-wine.py',*options],runner_log)
        path=pathlib.Path(runner_log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report
    logs[name]=(path.parent/'stdout.log').read_text(errors='replace')
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),'status':report['status'],
                'stages':report['stages'],'guest_exit_status_hex':report['guest_exit_status_hex']}
    if args.verify_only and sha(path)!=previous['runs'][name]['report_sha256']:failures.append(name+': report changed')
    known_protection_block=name=='prepared-relocated' and 'mprotect failed: Permission denied' in logs[name]
    if (report['Wine_booted'] or report['windows_execution_verified'] or report.get('host_ld_preload') or
            report['unhandled_access_violation'] or
            (not known_protection_block and (report['timed_out'] or 'Assertion Failed' in logs[name]))):
        failures.append(name+': unexpected execution, timeout or fault')
    if report['emulator_sha256']!=manifest['executable_sha256']:failures.append(name+': emulator mismatch')
    if report['elf_sha256']!=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())['bootstrap_sha256']:
        failures.append(name+': Wine ELF mismatch')
preflight=reports['preflight-fork'];wine=reports['prepared-relocated'];empty=reports['empty-wine']
if preflight['status']!='passed' or len(preflight['service_results'])!=12 or preflight['unix_entry_reached']:
    failures.append('Prefix preflight')
if (not wine['prefix_preflight_passed'] or not wine['external_prefix_policy_used'] or
        'process_spawn_blocked' in wine['stages'] or 'failed to load start.exe' in logs['prepared-relocated']):
    failures.append('Prepared startup policy')
if ('mprotect failed: Permission denied' not in logs['prepared-relocated'] or
        'mmap failed: Invalid argument' in logs['prepared-relocated'] or wine['invoked_stubs']):
    failures.append('Unexpected next startup blocker')
image=wine['wine_main_image_load']
if not image or image['machine_hex']!='0x014c' or image['status_hex'] not in ('0x00000000','0x40000003'):
    failures.append('Main image was not mapped')
fallback=wine['image_read_fallbacks']
if not any(item['offset_hex']=='0xc00' and item['copied']==item['requested'] and item['copied']>0 and not item['errno'] for item in fallback):
    failures.append('Wine read fallback not verified')
if (empty['guest_exit_status_hex']!='0xc0000135' or 'process_spawn_blocked' not in empty['stages'] or empty['external_prefix_policy_used']):
    failures.append('Empty prefix behavior')
historical=json.loads((ROOT/'reports/increment15/report.json').read_text())
for name in ('services','gs'):
    old=json.loads((ROOT/historical['runs'][name]['report']).read_text())
    if reports[name]['status']!=old['status'] or reports[name]['service_results']!=old['service_results']:
        failures.append(name+': service contract changed')
contract=json.loads((out/'mmap-contract/report.json').read_text())
native=contract['runs']['fork'];official=contract['runs']['official']
if (native['status']!='passed' or len(native['cases'])!=6 or native['emulator']['executable_sha256']!=manifest['executable_sha256'] or
        official['status']!='blocked' or not official['mmap_assertion']):failures.append('Mmap error contract')
for relative,digest in contract['inputs'].items():
    if sha(ROOT/relative)!=digest:failures.append('Mmap input changed: '+relative)
protection=json.loads((out/'protect-reproducer/report.json').read_text())
for name,report in protection['runs'].items():
    if report['status']!='blocked' or not report['request_reached'] or report['return_reached'] or not report['mprotect_assertion']:
        failures.append(name+': protection reproduction changed')
for relative,digest in protection['inputs'].items():
    if sha(ROOT/relative)!=digest:failures.append('Protection reproduction input changed: '+relative)
regressions=json.loads((out/'regressions-18/report.json').read_text())
if not regressions['focused_regressions_passed'] or regressions['emulator']['executable_sha256']!=manifest['executable_sha256']:
    failures.append('Increment18 regressions')
package_contract=ROOT/'reports/increment19/prefix-contract.json'
for relative,digest in json.loads(package_contract.read_text())['inputs'].items():
    if sha(ROOT/relative)!=digest:failures.append('Prefix consumer input changed: '+relative)
result={'schema_version':1,'status':'passed' if not failures else 'failed','failures':failures,
    'scope':'Real mmap error return and Wine image read fallback; EXE execution remains blocked',
    'Wine_booted':False,'windows_execution_verified':False,'hardware_status':'pending',
    'runs':runs,'emulator':manifest,'main_image_load':image,'image_read_fallbacks':fallback,
    'ntdll_pe64_ready':'ntdll_pe64_ready' in wine['stages'],
    'entering_windows_initialization':'entering_windows_initialization' in wine['stages'],
    'startup_blocker':{'operation':'mprotect read-write during ntdll PE64 relocation',
        'emulator_assertion':True,'reproduction':'reports/increment20/protect-reproducer/report.json'},
    'regressions_report':'reports/increment20/regressions-18/report.json',
    'artifact_hashes':{str(path.relative_to(ROOT)):sha(path) for path in
        (out/'regressions-18/report.json',out/'mmap-contract/report.json',out/'protect-reproducer/report.json',package_contract)}}
if args.verify_only and result['artifact_hashes']!=previous['artifact_hashes']:
    failures.append('Evidence index changed');result['status']='failed'
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'report.json')
if failures:raise SystemExit('Unexpected results: '+', '.join(failures))
