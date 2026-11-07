#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify console32-bare.exe through Wine with the translator WoW64 backend, and the regressions."""
import argparse,hashlib,json,pathlib,subprocess,sys,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',action='store_true');args=parser.parse_args()
out=ROOT/'reports/increment23';out.mkdir(parents=True,exist_ok=True)
previous=json.loads((out/'report.json').read_text()) if args.verify_only else None
package=['--prepared-prefix','reports/increment15/prefix-package']
wow=[*package,'--wow64-cpu','wowprospero']
cases=[('wine-wowprospero-1',['--fork',*wow]),('wine-wowprospero-2',['--fork',*wow]),('wine-wowprospero-3',['--fork',*wow]),
       ('wine-wowprospero-official',wow),('prepared-no-cpu',['--fork',*package]),
       ('preflight-fork',['--fork',*package,'--prefix-preflight']),('services',['--fork','--services']),
       ('gs',['--fork','--gs-services']),('gs-official',['--gs-services']),
       ('signal',['--fork','--signal-services']),('signal-official',['--signal-services']),
       ('wine-memory',['--fork','--baseline','--case','wine-memory']),
       ('segments',['--fork','--baseline','--case','segments']),
       ('exceptions',['--fork','--baseline','--case','exceptions']),
       ('exceptions-official',['--baseline','--case','exceptions']),
       ('empty-wine',['--fork','--exe','out/console32-bare.exe']),
       ('ipc',['--fork','--ipc-services']),('pipes',['--fork','--pipe-services']),
       ('filesystem',['--fork','--fs-services']),('metadata',['--fork','--metadata-services'])]
official={'wine-wowprospero-official','gs-official','signal-official','exceptions-official'}
probe_elf={'wine-memory','segments','exceptions','exceptions-official'}
wine_runs=('wine-wowprospero-1','wine-wowprospero-2','wine-wowprospero-3')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def execute(command,path):
    with path.open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
if not args.verify_only and not args.collect_existing:
    execute([sys.executable,'tools/check-wine-file-mapping21.py','--official','--report-dir','reports/increment23/file-mapping-contract'],
            ROOT/'build/increment23-file-mapping-final.log')
    execute([sys.executable,'tools/check-wine-mmap21.py','--report-dir','reports/increment23/mmap-contract'],
            ROOT/'build/increment23-mmap-final.log')
    execute([sys.executable,'tools/check-increment18.py','--report-dir','reports/increment23/regressions-18'],
            ROOT/'build/increment23-regressions-final.log')
failures=[];runs={};reports={};logs={}
manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
lock=json.loads((ROOT/'fork.lock.json').read_text())
if manifest['source_dirty'] or manifest['commit']!=lock['commit'] or sha(ROOT/'build/shadPS4-linux/shadps4')!=manifest['executable_sha256']:
    failures.append('Emulator is not the pinned clean build')
for entry in lock['patches']:
    if sha(ROOT/entry['path'])!=entry['sha256']:failures.append('Fork patch changed: '+entry['path'])
wowprospero=json.loads((ROOT/'out/wowprospero-ps4/manifest.json').read_text())
for name,entry in wowprospero['modules'].items():
    if sha(ROOT/'out/wowprospero-ps4'/entry['path'])!=entry['sha256']:failures.append('wowprospero module changed: '+name)
for item in wowprospero['adaptations']:
    if sha(ROOT/item['original'])!=item['original_sha256'] or sha(ROOT/item['adapted'])!=item['adapted_sha256']:
        failures.append('wowprospero adaptation changed: '+item['adapted'])
link=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())
for path,digest in wowprospero['unix_objects'].items():
    if link['object_hashes'].get(path)!=digest:failures.append('Boot ELF does not link the built object: '+path)
wine_elf=link['bootstrap_sha256'];probe=sha(ROOT/'out/eboot.bin')
for name,options in cases:
    if args.verify_only:path=ROOT/previous['runs'][name]['report']
    else:
        runner_log=ROOT/('build/increment23-'+name+'.log')
        if not args.collect_existing and name in ('ipc','pipes','filesystem','metadata'):
            path=ROOT/json.loads((out/'regressions-18/report.json').read_text())['runs'][name]['report']
        else:
            if not args.collect_existing:execute([sys.executable,'tools/run-linux-wine.py','--timeout','40',*options],runner_log)
            path=pathlib.Path(runner_log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report
    logs[name]=(path.parent/'stdout.log').read_text(errors='replace')
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),'status':report['status'],
                'stages':report['stages'],'guest_exit_status_hex':report['guest_exit_status_hex'],
                'service_results':report.get('service_results',[]),'invoked_stubs':report['invoked_stubs'],
                'Wine_booted':report['Wine_booted'],'windows_execution_verified':report['windows_execution_verified']}
    if args.verify_only and sha(path)!=previous['runs'][name]['report_sha256']:failures.append(name+': report changed')
    if report.get('host_ld_preload') or report.get('winedebug') or report.get('wineenv'):
        failures.append(name+': diagnostic run')
    if name not in wine_runs and (report['Wine_booted'] or report['windows_execution_verified']):
        failures.append(name+': unexpected execution claim')
    if name not in official and (report['timed_out'] or report['unhandled_access_violation'] or 'Assertion Failed' in logs[name]):
        failures.append(name+': timeout or fault')
    if report['elf_sha256']!=(probe if name in probe_elf else wine_elf):failures.append(name+': ELF mismatch')
    if name not in official and report['emulator_sha256']!=manifest['executable_sha256']:failures.append(name+': emulator mismatch')
    if name in official and report['emulator_kind']=='local Linux fork':failures.append(name+': not the official emulator')
def statuses(name):return {item['case']:item['status'] for item in reports[name]['service_results']}

# The milestone: console32-bare.exe through Wine, three times, against the native Windows reference.
reference=json.loads((ROOT/'reports/increment11-windows-reference/report.json').read_text())
expected_result=sha(ROOT/'reports/increment11-windows-reference/result.txt')
pe64=json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())
pe32=json.loads((ROOT/'out/wine/wine-runtime-manifest.json').read_text())
staged={'x86_64-windows/ntdll.dll':pe64['modules']['ntdll.dll']['sha256'],
        'i386-windows/ntdll.dll':next(item['sha256'] for item in pe32['modules'] if item['name']=='ntdll.dll'),
        'x86_64-windows/wowprospero.dll':wowprospero['modules']['wowprospero.dll']['sha256'],
        'x86_64-windows/wow64.dll':wowprospero['modules']['wow64.dll']['sha256']}
module_integrity={}
for name in wine_runs:
    wine=reports[name];log=logs[name]
    if (wine['status']!='passed' or not wine['Wine_booted'] or not wine['windows_execution_verified'] or
            wine['guest_exit_status_hex']!='0x00000000' or wine['guest_exit_code']!=reference['exit_code'] or
            not wine['wine_result_matches_windows_reference'] or wine['wine_result_sha256']!=expected_result or
            not wine['wine_exe_matches_windows_reference'] or wine['invoked_stubs'] or wine['wow64_cpu']!='wowprospero'):
        failures.append(name+': console32-bare.exe through Wine differs from the Windows reference contract')
    for text in ('wow64: CPU wowprospero.dll from WINE_PS4_WOW64_CPU','PWBOOT static_unixlib','PWBOOT user_shared_data_ready system_call=1'):
        if text not in log:failures.append(name+': missing '+text)
    for text in ('load_64bit_module failed','Got unexpected trap','Invalid handle 0000000000000000','unable to dispatch exception'):
        if text in log:failures.append(name+': earlier blocker present: '+text)
    with tarfile.open((ROOT/runs[name]['report']).parent/'runtime.tar.gz','r:gz') as archive:
        names=set(archive.getnames())
        for module,digest in staged.items():
            actual=hashlib.sha256(archive.extractfile('runtime/data/wine/lib/wine/'+module).read()).hexdigest()
            module_integrity.setdefault(name,{})[module]=actual==digest
            if actual!=digest:failures.append(name+': staged module changed: '+module)
        if 'runtime/data/wine-prefix/drive_c/windows/system32/wowprospero.dll' not in names:
            failures.append(name+': backend not installed in the extracted prefix')
        if any(item.endswith('/wow64cpu.dll') for item in names):failures.append(name+': a wow64cpu.dll was staged')
if reports['wine-wowprospero-official']['status']=='passed':failures.append('Official comparison changed')
control=reports['prepared-no-cpu']
if (control['guest_exit_status_hex']!='0xc0000135' or 'wow:load_64bit_module failed to load dll c0000135' not in logs['prepared-no-cpu']
        or control['Wine_booted']):failures.append('Without the backend the increment 22 blocker must remain')

if reports['gs']['status']!='passed' or statuses('gs')!={'gs-fsbase-contract':'passed','gs-memory-and-native-tls':'passed'}:
    failures.append('GS contract in the fork')
if reports['gs-official']['status']!='blocked' or 'sysarch' not in reports['gs-official']['invoked_stubs']:
    failures.append('GS official comparison changed')
signal_cases=('signal-read-page-fault','signal-write-page-fault','signal-fpu-state-read','signal-fpu-state-write',
              'signal-mask-translation','signal-onstack-without-altstack','signal-installed-altstack')
if reports['signal']['status']!='passed' or statuses('signal')!={case:'passed' for case in signal_cases}:
    failures.append('Signal context contract in the fork')
if reports['signal-official']['status']=='passed':failures.append('Signal official comparison changed')
if (reports['wine-memory']['status']!='passed' or
        'kind=0 rc=0 checks=10' not in logs['wine-memory']):failures.append('wine-memory commit and madvise contract')
if reports['segments']['status']!='passed' or reports['segments']['invoked_stubs']:failures.append('segments in the fork')
detail='"case":"exceptions","status":"failed","code":1,"detail":"signal=0 resumed=0 value=0 rip_offset=224"'
for name in ('exceptions','exceptions-official'):
    if reports[name]['status']!='blocked' or detail not in logs[name]:failures.append(name+': unexpected result')
historical=json.loads((ROOT/'reports/increment15/report.json').read_text())
old_services={item['case']:item['status'] for item in json.loads((ROOT/historical['runs']['services']['report']).read_text())['service_results']}
old_services['gs-query-output']='passed'
if statuses('services')!=old_services:failures.append('services: contract changed beyond gs-query-output')
preflight=reports['preflight-fork'];empty=reports['empty-wine']
if preflight['status']!='passed' or len(preflight['service_results'])!=12 or preflight['unix_entry_reached']:
    failures.append('Prefix preflight')
if (empty['guest_exit_status_hex']!='0xc0000135' or 'process_spawn_blocked' not in empty['stages'] or empty['external_prefix_policy_used']):
    failures.append('Empty prefix behavior')
contracts=[out/'file-mapping-contract/report.json',out/'mmap-contract/report.json']
for path,count in zip(contracts,(10,6)):
    contract=json.loads(path.read_text());native=contract['runs']['fork']
    if native['status']!='passed' or len(native['cases'])!=count or native['emulator']['executable_sha256']!=manifest['executable_sha256']:
        failures.append(path.parent.name+': contract failed')
if json.loads(contracts[0].read_text())['runs']['official']['status']!='blocked':failures.append('File-mapping official comparison changed')
regressions=json.loads((out/'regressions-18/report.json').read_text())
if not regressions['focused_regressions_passed'] or regressions['emulator']['executable_sha256']!=manifest['executable_sha256']:
    failures.append('Increment18 regressions')
for name in ('ipc','pipes','filesystem','metadata'):
    if reports[name]['status']!='passed':failures.append(name+': service regression')
result={'schema_version':1,'status':'passed' if not failures else 'failed','failures':failures,
    'scope':'console32-bare.exe through Wine in the Linux fork, with the prospero-win translator as WoW64 CPU backend',
    'Wine_booted':not failures,'windows_execution_verified':not failures,'hardware_status':'pending',
    'exe':'out/console32-bare.exe','windows_reference':'reports/increment11-windows-reference',
    'runs':runs,'emulator':manifest,'fork_patches':lock['patches'],'wowprospero':wowprospero,
    'staged_module_integrity':module_integrity,
    'not_covered':['console32.exe (mingw CRT) through Wine','official shadPS4 (blocked by stubs)','Windows host fork',
                   'PS4 hardware','graphics, input and audio'],
    'recorded_host_differences':{'exceptions':'Linux keeps a reserved range readable; same detail on the official Linux release',
                                 'dispatcher-mixed':'Fails on the Linux fork since increment 17; tracked separately'},
    'artifact_hashes':{str(path.relative_to(ROOT)):sha(path) for path in (*contracts,out/'regressions-18/report.json')}}
if args.verify_only and result['artifact_hashes']!=previous['artifact_hashes']:
    failures.append('Evidence index changed');result['status']='failed'
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'report.json')
if failures:raise SystemExit('Unexpected results: '+', '.join(failures))
