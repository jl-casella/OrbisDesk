#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify private mappings, ntdll relocation and the shared dispatcher slot; GS remains blocked."""
import argparse,hashlib,json,pathlib,subprocess,sys,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',action='store_true');args=parser.parse_args()
out=ROOT/'reports/increment21';out.mkdir(parents=True,exist_ok=True)
previous=json.loads((out/'report.json').read_text()) if args.verify_only else None
package=['--prepared-prefix','reports/increment15/prefix-package']
cases=[('preflight-fork',['--fork',*package,'--prefix-preflight']),
       ('prepared-dispatcher',['--fork',*package]),('services',['--fork','--services']),
       ('gs',['--fork','--gs-services']),('empty-wine',['--fork','--exe','out/console32-bare.exe']),
       ('ipc',['--fork','--ipc-services']),('pipes',['--fork','--pipe-services']),
       ('filesystem',['--fork','--fs-services']),('metadata',['--fork','--metadata-services'])]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def execute(command,path):
    with path.open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
if not args.verify_only and not args.collect_existing:
    execute([sys.executable,'tools/check-wine-file-mapping21.py','--official'],ROOT/'build/increment21-file-mapping-final.log')
    execute([sys.executable,'tools/check-wine-mmap21.py'],ROOT/'build/increment21-mmap-final.log')
    execute([sys.executable,'tools/check-increment18.py','--report-dir','reports/increment21/regressions-18'],ROOT/'build/increment21-regressions-final.log')
failures=[];runs={};reports={};logs={}
manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
lock=json.loads((ROOT/'fork.lock.json').read_text())
if manifest['source_dirty'] or manifest['commit']!=lock['commit'] or sha(ROOT/'build/shadPS4-linux/shadps4')!=manifest['executable_sha256']:
    failures.append('Emulator is not the pinned clean build')
elf=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())['bootstrap_sha256']
for name,options in cases:
    if args.verify_only:path=ROOT/previous['runs'][name]['report']
    else:
        runner_log=ROOT/('build/increment21-'+name+'.log')
        if not args.collect_existing and name in ('ipc','pipes','filesystem','metadata'):
            path=ROOT/json.loads((out/'regressions-18/report.json').read_text())['runs'][name]['report']
        else:
            if not args.collect_existing:execute([sys.executable,'tools/run-linux-wine.py',*options],runner_log)
            path=pathlib.Path(runner_log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report
    logs[name]=(path.parent/'stdout.log').read_text(errors='replace')
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),'status':report['status'],
                'stages':report['stages'],'guest_exit_status_hex':report['guest_exit_status_hex']}
    if args.verify_only and sha(path)!=previous['runs'][name]['report_sha256']:failures.append(name+': report changed')
    if (report['Wine_booted'] or report['windows_execution_verified'] or report.get('host_ld_preload') or
            report['timed_out'] or report['unhandled_access_violation'] or 'Assertion Failed' in logs[name]):
        failures.append(name+': unexpected execution, timeout or fault')
    if report['emulator_sha256']!=manifest['executable_sha256'] or report['elf_sha256']!=elf:
        failures.append(name+': binary mismatch')
preflight=reports['preflight-fork'];wine=reports['prepared-dispatcher'];empty=reports['empty-wine']
if preflight['status']!='passed' or len(preflight['service_results'])!=12 or preflight['unix_entry_reached']:
    failures.append('Prefix preflight')
if (not wine['prefix_preflight_passed'] or not wine['external_prefix_policy_used'] or
        'ntdll_pe64_ready' not in wine['stages'] or 'entering_windows_initialization' not in wine['stages'] or
        'dispatcher_slot_ready' not in wine['stages'] or 'process_spawn_blocked' in wine['stages'] or
        'mprotect failed:' in logs['prepared-dispatcher']):failures.append('Wine ntdll loading contract')
alignment=wine.get('anon_alignment_blocker')
if alignment or wine.get('dispatcher_slot')!={'address':'0x7ffe1000','host_page':16384}:
    failures.append('Dispatcher page invariant')
if (wine['guest_exit_status_hex']!='0x0000005d' or wine['invoked_stubs']!=['sysarch'] or
        'GS base could not be installed/verified' not in logs['prepared-dispatcher']):
    failures.append('Unexpected next GS blocker')
image=wine['wine_main_image_load']
if not image or image['machine_hex']!='0x014c' or image['status_hex'] not in ('0x00000000','0x40000003'):
    failures.append('Main image mapping')
pe64=json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())
pe32=json.loads((ROOT/'out/wine/wine-runtime-manifest.json').read_text())
expected_modules={'x86_64-windows/ntdll.dll':pe64['modules']['ntdll.dll']['sha256'],
    'i386-windows/ntdll.dll':next(item['sha256'] for item in pe32['modules'] if item['name']=='ntdll.dll')}
module_integrity={}
with tarfile.open((ROOT/runs['prepared-dispatcher']['report']).parent/'runtime.tar.gz','r:gz') as archive:
    for name,digest in expected_modules.items():
        actual=hashlib.sha256(archive.extractfile('runtime/data/wine/lib/wine/'+name).read()).hexdigest()
        module_integrity[name]={'sha256':actual,'unchanged':actual==digest}
        if actual!=digest:failures.append('Wine modified the staged module file: '+name)
if (empty['guest_exit_status_hex']!='0xc0000135' or 'process_spawn_blocked' not in empty['stages'] or empty['external_prefix_policy_used']):
    failures.append('Empty prefix behavior')
historical=json.loads((ROOT/'reports/increment15/report.json').read_text())
for name in ('services','gs'):
    old=json.loads((ROOT/historical['runs'][name]['report']).read_text())
    if reports[name]['status']!=old['status'] or reports[name]['service_results']!=old['service_results']:
        failures.append(name+': service contract changed')
contracts=[out/'file-mapping-contract/report.json',out/'mmap-contract/report.json']
for path,count in zip(contracts,(10,6)):
    contract=json.loads(path.read_text());native=contract['runs']['fork']
    if native['status']!='passed' or len(native['cases'])!=count or native['emulator']['executable_sha256']!=manifest['executable_sha256']:
        failures.append(path.parent.name+': contract failed')
    for relative,digest in contract['inputs'].items():
        if sha(ROOT/relative)!=digest:failures.append('Contract input changed: '+relative)
official=json.loads(contracts[0].read_text())['runs']['official']
if official['status']!='blocked' or not official['mprotect_assertion']:
    failures.append('Official comparison changed')
regressions=json.loads((out/'regressions-18/report.json').read_text())
if not regressions['focused_regressions_passed'] or regressions['emulator']['executable_sha256']!=manifest['executable_sha256']:
    failures.append('Increment18 regressions')
for name in ('ipc','pipes','filesystem','metadata'):
    old=json.loads((ROOT/regressions['runs'][name]['report']).read_text())
    if reports[name]['status']!='passed' or {item['case']:item['status'] for item in reports[name]['service_results']}!={item['case']:item['status'] for item in old['service_results']}:
        failures.append(name+': final ELF service regression')
prefix_contract=ROOT/'reports/increment19/prefix-contract.json'
for relative,digest in json.loads(prefix_contract.read_text())['inputs'].items():
    if sha(ROOT/relative)!=digest:failures.append('Prefix validation input changed: '+relative)
result={'schema_version':1,'status':'passed' if not failures else 'failed','failures':failures,
    'scope':'Verification of Linux file mappings, protection permissions and Wine startup',
    'Wine_booted':False,'windows_execution_verified':False,'hardware_status':'pending',
    'runs':runs,'emulator':manifest,'main_image_load':image,
    'staged_ntdll_files':module_integrity,
    'ntdll_pe64_ready':'ntdll_pe64_ready' in wine['stages'],
    'entering_windows_initialization':'entering_windows_initialization' in wine['stages'],
    'dispatcher_slot':wine.get('dispatcher_slot'),
    'next_blocker':{'operation':'GS base installation and verification through sysarch',
        'guest_exit_status_hex':wine['guest_exit_status_hex'],'invoked_stubs':wine['invoked_stubs'],
        'unhandled_access_violation':wine['unhandled_access_violation']},
    'artifact_hashes':{str(path.relative_to(ROOT)):sha(path) for path in
        (*contracts,out/'regressions-18/report.json',prefix_contract)}}
if args.verify_only and result['artifact_hashes']!=previous['artifact_hashes']:
    failures.append('Evidence index changed');result['status']='failed'
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'report.json')
if failures:raise SystemExit('Unexpected results: '+', '.join(failures))
