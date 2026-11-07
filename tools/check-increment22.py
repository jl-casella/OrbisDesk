#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify per-thread GS, guest signal contexts and the next Wine blocker (WoW64 CPU provider)."""
import argparse,hashlib,json,pathlib,subprocess,sys,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',action='store_true');args=parser.parse_args()
out=ROOT/'reports/increment22';out.mkdir(parents=True,exist_ok=True)
previous=json.loads((out/'report.json').read_text()) if args.verify_only else None
package=['--prepared-prefix','reports/increment15/prefix-package']
cases=[('preflight-fork',['--fork',*package,'--prefix-preflight']),
       ('prepared-wine',['--fork',*package]),('services',['--fork','--services']),
       ('gs',['--fork','--gs-services']),('gs-official',['--gs-services']),
       ('signal',['--fork','--signal-services']),('signal-official',['--signal-services']),
       ('segments',['--fork','--baseline','--case','segments']),
       ('exceptions',['--fork','--baseline','--case','exceptions']),
       ('exceptions-official',['--baseline','--case','exceptions']),
       ('empty-wine',['--fork','--exe','out/console32-bare.exe']),
       ('ipc',['--fork','--ipc-services']),('pipes',['--fork','--pipe-services']),
       ('filesystem',['--fork','--fs-services']),('metadata',['--fork','--metadata-services'])]
official={'gs-official','signal-official','exceptions-official'}
probe_elf={'segments','exceptions','exceptions-official'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def execute(command,path):
    with path.open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
if not args.verify_only and not args.collect_existing:
    execute([sys.executable,'tools/check-wine-file-mapping21.py','--official','--report-dir','reports/increment22/file-mapping-contract'],
            ROOT/'build/increment22-file-mapping-final.log')
    execute([sys.executable,'tools/check-wine-mmap21.py','--report-dir','reports/increment22/mmap-contract'],
            ROOT/'build/increment22-mmap-final.log')
    execute([sys.executable,'tools/check-increment18.py','--report-dir','reports/increment22/regressions-18'],
            ROOT/'build/increment22-regressions-final.log')
failures=[];runs={};reports={};logs={}
manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
lock=json.loads((ROOT/'fork.lock.json').read_text())
if manifest['source_dirty'] or manifest['commit']!=lock['commit'] or sha(ROOT/'build/shadPS4-linux/shadps4')!=manifest['executable_sha256']:
    failures.append('Emulator is not the pinned clean build')
for entry in lock['patches']:
    if sha(ROOT/entry['path'])!=entry['sha256']:failures.append('Fork patch changed: '+entry['path'])
wine_elf=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())['bootstrap_sha256']
probe=sha(ROOT/'out/eboot.bin')
for name,options in cases:
    if args.verify_only:path=ROOT/previous['runs'][name]['report']
    else:
        runner_log=ROOT/('build/increment22-'+name+'.log')
        if not args.collect_existing and name in ('ipc','pipes','filesystem','metadata'):
            path=ROOT/json.loads((out/'regressions-18/report.json').read_text())['runs'][name]['report']
        else:
            if not args.collect_existing:execute([sys.executable,'tools/run-linux-wine.py','--timeout','20',*options],runner_log)
            path=pathlib.Path(runner_log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report
    logs[name]=(path.parent/'stdout.log').read_text(errors='replace')
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),'status':report['status'],
                'stages':report['stages'],'guest_exit_status_hex':report['guest_exit_status_hex'],
                'service_results':report.get('service_results',[]),'invoked_stubs':report['invoked_stubs']}
    if args.verify_only and sha(path)!=previous['runs'][name]['report_sha256']:failures.append(name+': report changed')
    if report['Wine_booted'] or report['windows_execution_verified'] or report.get('host_ld_preload') or report.get('winedebug'):
        failures.append(name+': unexpected execution claim or diagnostic run')
    if name not in official and (report['timed_out'] or report['unhandled_access_violation'] or 'Assertion Failed' in logs[name]):
        failures.append(name+': timeout or fault')
    elf=probe if name in probe_elf else wine_elf
    if report['elf_sha256']!=elf:failures.append(name+': ELF mismatch')
    if name not in official and report['emulator_sha256']!=manifest['executable_sha256']:failures.append(name+': emulator mismatch')
    if name in official and report['emulator_kind']=='local Linux fork':failures.append(name+': not the official emulator')
def statuses(name):return {item['case']:item['status'] for item in reports[name]['service_results']}
if reports['gs']['status']!='passed' or statuses('gs')!={'gs-fsbase-contract':'passed','gs-memory-and-native-tls':'passed'}:
    failures.append('GS contract in the fork')
if reports['gs-official']['status']!='blocked' or 'sysarch' not in reports['gs-official']['invoked_stubs']:
    failures.append('GS official comparison changed')
signal_cases=('signal-read-page-fault','signal-write-page-fault','signal-fpu-state-read','signal-fpu-state-write','signal-mask-translation')
if reports['signal']['status']!='passed' or statuses('signal')!={case:'passed' for case in signal_cases}:
    failures.append('Signal context contract in the fork')
if reports['signal-official']['status']=='passed':failures.append('Signal official comparison changed')
if reports['segments']['status']!='passed' or reports['segments']['invoked_stubs']:failures.append('segments in the fork')
# exceptions reads a reserved range that a Linux host keeps readable; the official Linux
# release gives the same detail, so it is a recorded host difference, not a regression.
detail='"case":"exceptions","status":"failed","code":1,"detail":"signal=0 resumed=0 value=0 rip_offset=224"'
for name in ('exceptions','exceptions-official'):
    if reports[name]['status']!='blocked' or detail not in logs[name]:failures.append(name+': unexpected result')
historical=json.loads((ROOT/'reports/increment15/report.json').read_text())
old_services={item['case']:item['status'] for item in json.loads((ROOT/historical['runs']['services']['report']).read_text())['service_results']}
old_services['gs-query-output']='passed'
if statuses('services')!=old_services:failures.append('services: contract changed beyond gs-query-output')
preflight=reports['preflight-fork'];wine=reports['prepared-wine'];empty=reports['empty-wine']
if preflight['status']!='passed' or len(preflight['service_results'])!=12 or preflight['unix_entry_reached']:
    failures.append('Prefix preflight')
required=('prefix_preflight_passed','user_shared_data_ready','external_prefix_ready','ntdll_pe64_ready',
          'entering_windows_initialization','dispatcher_slot_ready','image_map_addr_unavailable')
log=logs['prepared-wine']
if (any(stage not in wine['stages'] for stage in required) or 'process_spawn_blocked' in wine['stages'] or
        'user_shared_data_ready system_call=1' not in log):failures.append('Wine start-up contract')
for text in ('GS base could not be installed/verified','Got unexpected trap','Invalid handle 0000000000000000','mprotect failed:'):
    if text in log:failures.append('Earlier Wine blocker still present: '+text)
if (wine['guest_exit_status_hex']!='0xc0000135' or wine['invoked_stubs'] or
        'wow:load_64bit_module failed to load dll c0000135' not in log):failures.append('Unexpected next Wine blocker')
pe64=json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())
pe32=json.loads((ROOT/'out/wine/wine-runtime-manifest.json').read_text())
expected_modules={'x86_64-windows/ntdll.dll':pe64['modules']['ntdll.dll']['sha256'],
    'i386-windows/ntdll.dll':next(item['sha256'] for item in pe32['modules'] if item['name']=='ntdll.dll')}
module_integrity={}
with tarfile.open((ROOT/runs['prepared-wine']['report']).parent/'runtime.tar.gz','r:gz') as archive:
    names=archive.getnames()
    for name,digest in expected_modules.items():
        actual=hashlib.sha256(archive.extractfile('runtime/data/wine/lib/wine/'+name).read()).hexdigest()
        module_integrity[name]={'sha256':actual,'unchanged':actual==digest}
        if actual!=digest:failures.append('Wine modified the staged module file: '+name)
    cpu_provider_staged=any(name.endswith('/wow64cpu.dll') for name in names)
if cpu_provider_staged:failures.append('A wow64cpu.dll was staged; the blocker would not be the missing provider')
if (empty['guest_exit_status_hex']!='0xc0000135' or 'process_spawn_blocked' not in empty['stages'] or empty['external_prefix_policy_used']):
    failures.append('Empty prefix behavior')
contracts=[out/'file-mapping-contract/report.json',out/'mmap-contract/report.json']
for path,count in zip(contracts,(10,6)):
    contract=json.loads(path.read_text());native=contract['runs']['fork']
    if native['status']!='passed' or len(native['cases'])!=count or native['emulator']['executable_sha256']!=manifest['executable_sha256']:
        failures.append(path.parent.name+': contract failed')
mapping_official=json.loads(contracts[0].read_text())['runs']['official']
if mapping_official['status']!='blocked' or not mapping_official['mprotect_assertion']:
    failures.append('File-mapping official comparison changed')
regressions=json.loads((out/'regressions-18/report.json').read_text())
if not regressions['focused_regressions_passed'] or regressions['emulator']['executable_sha256']!=manifest['executable_sha256']:
    failures.append('Increment18 regressions')
for name in ('ipc','pipes','filesystem','metadata'):
    if reports[name]['status']!='passed':failures.append(name+': service regression')
result={'schema_version':1,'status':'passed' if not failures else 'failed','failures':failures,
    'scope':'Per-thread GS and complete guest signal contexts in the Linux fork; Wine start-up up to the WoW64 CPU provider',
    'Wine_booted':False,'windows_execution_verified':False,'hardware_status':'pending',
    'runs':runs,'emulator':manifest,'fork_patches':lock['patches'],'staged_ntdll_files':module_integrity,
    'next_blocker':{'operation':'WoW64 CPU provider (wow64cpu.dll) not available',
        'guest_exit_status_hex':wine['guest_exit_status_hex'],'invoked_stubs':wine['invoked_stubs'],
        'timed_out':wine['timed_out'],'unhandled_access_violation':wine['unhandled_access_violation']},
    'recorded_host_differences':{'exceptions':'Linux keeps a reserved range readable; same detail on the official Linux release',
                                 'dispatcher-mixed':'Fails on the Linux fork since increment 17; tracked separately'},
    'artifact_hashes':{str(path.relative_to(ROOT)):sha(path) for path in (*contracts,out/'regressions-18/report.json')}}
if args.verify_only and result['artifact_hashes']!=previous['artifact_hashes']:
    failures.append('Evidence index changed');result['status']='failed'
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'report.json')
if failures:raise SystemExit('Unexpected results: '+', '.join(failures))
