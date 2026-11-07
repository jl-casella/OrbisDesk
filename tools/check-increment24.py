#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify Wine GUI programs through the in-process user driver and sceVideoOut, and the regressions."""
import argparse,hashlib,json,pathlib,shutil,struct,subprocess,sys,tarfile,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',action='store_true')
parser.add_argument('--report-dir',type=pathlib.Path,default=ROOT/'reports/increment24')
parser.add_argument('--reuse-platform',type=pathlib.Path,help='Reuse verified native platform evidence; repeat every Wine case for the current ELF')
args=parser.parse_args()
out=args.report_dir;out.mkdir(parents=True,exist_ok=True)
log_root=ROOT/'build' if out.resolve()==(ROOT/'reports/increment24').resolve() else out/'logs'
log_root.mkdir(parents=True,exist_ok=True)
previous=json.loads((out/'report.json').read_text()) if args.verify_only else None
package=['--prepared-prefix','reports/increment15/prefix-package']
gui=[*package,'--wine-gui','--wine-exe','C:\\orbis\\gui-window64.exe']
explorer=[*package,'--wine-gui','--wine-exe','C:\\windows\\explorer.exe','--wine-arg','/desktop=shell,800x600']
cases=[('gui-window-1',['--fork',*gui]),('gui-window-2',['--fork',*gui]),('gui-window-3',['--fork',*gui]),
       ('gui-window-official',gui),('explorer-desktop',['--fork',*explorer]),
       ('wine-wowprospero',['--fork',*package,'--wow64-cpu','wowprospero']),('prepared-no-cpu',['--fork',*package]),
       ('preflight-fork',['--fork',*package,'--prefix-preflight']),('services',['--fork','--services']),
       ('gs',['--fork','--gs-services']),('signal',['--fork','--signal-services']),
       ('wine-memory',['--fork','--baseline','--case','wine-memory']),
       ('segments',['--fork','--baseline','--case','segments']),
       ('exceptions',['--fork','--baseline','--case','exceptions']),
       ('empty-wine',['--fork','--exe','out/console32-bare.exe']),
       ('ipc',['--fork','--ipc-services']),('pipes',['--fork','--pipe-services']),
       ('filesystem',['--fork','--fs-services']),('metadata',['--fork','--metadata-services'])]
official={'gui-window-official'}
long_running={'explorer-desktop'}  # explorer's desktop never exits: it ends at the runner timeout
probe_elf={'wine-memory','segments','exceptions'}
gui_runs=('gui-window-1','gui-window-2','gui-window-3')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def execute(command,path):
    with path.open('w') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
def bitmap(report_path,name):
    with tarfile.open(report_path.parent/'runtime.tar.gz','r:gz') as archive:
        return archive.extractfile('runtime/data/frames/'+name).read()
def png(data,target):
    width,height=struct.unpack_from('<ii',data,18);height=abs(height);pixels=data[54:]
    rows=b''.join(b'\0'+bytes(value for x in range(width) for value in
                  (pixels[(y*width+x)*4+2],pixels[(y*width+x)*4+1],pixels[(y*width+x)*4])) for y in range(height))
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    target.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
                       chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))
def colour_count(data,bgr,top=0):
    width,height=struct.unpack_from('<ii',data,18);height=abs(height);pixels=data[54:]
    return sum(1 for y in range(top,height) for x in range(width) if pixels[(y*width+x)*4:(y*width+x)*4+3]==bgr)
if not args.verify_only and not args.collect_existing:
    if args.reuse_platform:
        for folder in ('file-mapping-contract','mmap-contract','regressions-18'):
            shutil.copytree(args.reuse_platform/folder,out/folder)
        execute([sys.executable,'tools/check-increment18.py','--verify-only','--report-dir',str(out/'regressions-18')],
                log_root/'increment24-regressions-verified.log')
    else:
        execute([sys.executable,'tools/check-wine-file-mapping21.py','--official','--report-dir',str(out/'file-mapping-contract')],
                log_root/'increment24-file-mapping-final.log')
        execute([sys.executable,'tools/check-wine-mmap21.py','--report-dir',str(out/'mmap-contract')],
                log_root/'increment24-mmap-final.log')
        execute([sys.executable,'tools/check-increment18.py','--report-dir',str(out/'regressions-18')],
                log_root/'increment24-regressions-final.log')
failures=[];runs={};reports={};logs={};paths={}
manifest=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
lock=json.loads((ROOT/'fork.lock.json').read_text())
if manifest['source_dirty'] or manifest['commit']!=lock['commit'] or sha(ROOT/'build/shadPS4-linux/shadps4')!=manifest['executable_sha256']:
    failures.append('Emulator is not the pinned clean build')
for entry in lock['patches']:
    if sha(ROOT/entry['path'])!=entry['sha256']:failures.append('Fork patch changed: '+entry['path'])
link=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())
win32u=json.loads((ROOT/'build/win32u-ps4/report.json').read_text())
if any(item['exit_code'] for item in win32u['results']):failures.append('win32u units did not all compile')
for path,digest in win32u['objects'].items():
    if sha(ROOT/path)!=digest:failures.append('win32u object changed after its report: '+path)
gui_manifest=json.loads((ROOT/'out/wine-gui/manifest.json').read_text())
for name,entry in gui_manifest['modules'].items():
    if sha(ROOT/'out/wine-gui'/entry['path'])!=entry['sha256']:failures.append('GUI module changed: '+name)
wine_elf=link['bootstrap_sha256'];probe=sha(ROOT/'out/eboot.bin')
for name,options in cases:
    if args.verify_only:path=ROOT/previous['runs'][name]['report']
    else:
        runner_log=log_root/('increment24-'+name+'.log')
        if not args.collect_existing and not args.reuse_platform and name in ('ipc','pipes','filesystem','metadata'):
            path=ROOT/json.loads((out/'regressions-18/report.json').read_text())['runs'][name]['report']
        else:
            if not args.collect_existing:execute([sys.executable,'tools/run-linux-wine.py','--timeout','45',*options],runner_log)
            path=pathlib.Path(runner_log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report;paths[name]=path
    logs[name]=(path.parent/'stdout.log').read_text(errors='replace')
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),'status':report['status'],
                'stages':report['stages'],'guest_exit_status_hex':report['guest_exit_status_hex'],
                'service_results':report.get('service_results',[]),'invoked_stubs':report['invoked_stubs'],
                'frames_presented':report.get('frames_presented'),'frame_dumps':report.get('frame_dumps'),
                'Wine_booted':report['Wine_booted'],'windows_execution_verified':report['windows_execution_verified']}
    if args.verify_only and sha(path)!=previous['runs'][name]['report_sha256']:failures.append(name+': report changed')
    if report.get('host_ld_preload') or report.get('winedebug') or report.get('wineenv'):failures.append(name+': diagnostic run')
    if name not in official and name not in long_running and (report['timed_out'] or report['unhandled_access_violation'] or
                                                             'Assertion Failed' in logs[name]):
        failures.append(name+': timeout or fault')
    if report['elf_sha256']!=(probe if name in probe_elf else wine_elf):failures.append(name+': ELF mismatch')
    if name not in official and report['emulator_sha256']!=manifest['executable_sha256']:failures.append(name+': emulator mismatch')
    if name in official and report['emulator_kind']=='local Linux fork':failures.append(name+': not the official emulator')
def statuses(name):return {item['case']:item['status'] for item in reports[name]['service_results']}

reference=json.loads((ROOT/'reports/increment24-windows-reference/report.json').read_text())
evidence=out/'evidence';evidence.mkdir(exist_ok=True)
fill=bytes((140,60,20));client_pixels=464*280
for name in gui_runs:
    report=reports[name]
    if (report['status']!='passed' or not report['gui_result_matches_windows_reference'] or
            not report['gui_exe_matches_windows_reference'] or report['guest_exit_code']!=reference['exit_code'] or
            report['invoked_stubs'] or not report['video_out_ready']):
        failures.append(name+': GUI fixture differs from the Windows reference contract')
    if 'PWBOOT static_unixlib /data/wine/lib/wine/x86_64-unix/win32u.so' not in logs[name]:failures.append(name+': win32u not linked in')
    if not any(item['fixture_fill_pixels']==client_pixels for item in report['frame_dumps'].values()):
        failures.append(name+': no presented frame shows the whole client area')
first=reports['gui-window-1']
shown=next(frame for frame,item in sorted(first['frame_dumps'].items()) if item['fixture_fill_pixels']==client_pixels)
png(bitmap(paths['gui-window-1'],shown),evidence/'gui-window64.png')
if reports['gui-window-official']['status']=='passed':failures.append('Official GUI comparison changed')
desktop=reports['explorer-desktop']
if (not desktop['video_out_ready'] or desktop['frames_presented']<2 or desktop['invoked_stubs'] or
        desktop['unhandled_access_violation'] or desktop['Wine_booted']):failures.append('explorer desktop evidence')
last=sorted(desktop['frame_dumps'])[-1] if desktop['frame_dumps'] else None
taskbar=colour_count(bitmap(paths['explorer-desktop'],last),bytes((200,208,212)),580) if last else 0
if taskbar<15000:failures.append('explorer desktop: no taskbar in the last presented frame')
if last:png(bitmap(paths['explorer-desktop'],last),evidence/'explorer-desktop.png')

wine=reports['wine-wowprospero']
if wine['status']!='passed' or not wine['wine_result_matches_windows_reference'] or wine['invoked_stubs']:
    failures.append('console32-bare.exe through Wine (increment 23) regressed')
control=reports['prepared-no-cpu']
if control['guest_exit_status_hex']!='0xc0000135' or 'wow:load_64bit_module failed to load dll c0000135' not in logs['prepared-no-cpu']:
    failures.append('Without the backend the increment 22 blocker must remain')
if reports['gs']['status']!='passed':failures.append('GS contract')
if reports['signal']['status']!='passed' or len(reports['signal']['service_results'])!=7:failures.append('Signal contract')
if reports['wine-memory']['status']!='passed' or 'kind=0 rc=0 checks=12' not in logs['wine-memory']:
    failures.append('wine-memory commit, madvise and getrusage contract')
if reports['segments']['status']!='passed':failures.append('segments')
if (reports['exceptions']['status']!='blocked' or
        '"detail":"signal=0 resumed=0 value=0 rip_offset=224"' not in logs['exceptions']):failures.append('exceptions')
historical=json.loads((ROOT/'reports/increment15/report.json').read_text())
old_services={item['case']:item['status'] for item in json.loads((ROOT/historical['runs']['services']['report']).read_text())['service_results']}
old_services['gs-query-output']='passed'
if statuses('services')!=old_services:failures.append('services: contract changed beyond gs-query-output')
if reports['preflight-fork']['status']!='passed' or len(reports['preflight-fork']['service_results'])!=12:failures.append('Prefix preflight')
empty=reports['empty-wine']
if empty['guest_exit_status_hex']!='0xc0000135' or 'process_spawn_blocked' not in empty['stages']:failures.append('Empty prefix behavior')
contracts=[out/'file-mapping-contract/report.json',out/'mmap-contract/report.json']
for path,count in zip(contracts,(10,6)):
    native=json.loads(path.read_text())['runs']['fork']
    if native['status']!='passed' or len(native['cases'])!=count or native['emulator']['executable_sha256']!=manifest['executable_sha256']:
        failures.append(path.parent.name+': contract failed')
regressions=json.loads((out/'regressions-18/report.json').read_text())
if not regressions['focused_regressions_passed'] or regressions['emulator']['executable_sha256']!=manifest['executable_sha256']:
    failures.append('Increment18 regressions')
if any(entry['elf_sha256']!=probe for name,entry in regressions['runs'].items()
       if name not in ('ipc','pipes','filesystem','metadata')):
    failures.append('Native platform ELF changed: cannot reuse these regressions')
for name in ('ipc','pipes','filesystem','metadata'):
    if reports[name]['status']!='passed':failures.append(name+': service regression')
result={'schema_version':1,'status':'passed' if not failures else 'failed','failures':failures,
    'platform_evidence_reused_from':str(args.reuse_platform) if args.reuse_platform else
        previous.get('platform_evidence_reused_from') if args.verify_only else None,
    'scope':'Wine GUI through win32u with an in-process user driver presenting to sceVideoOut, in the Linux fork',
    'hardware_status':'pending','windows_reference':'reports/increment24-windows-reference',
    'runs':runs,'emulator':manifest,'fork_patches':lock['patches'],'win32u':{'prospero_patches':win32u['prospero_patches'],
    'revisions':win32u['revisions']},'gui_modules':gui_manifest['modules'],'explorer_taskbar_pixels':taskbar,
    'evidence':{name:sha(evidence/name) for name in ('gui-window64.png','explorer-desktop.png') if (evidence/name).is_file()},
    'not_covered':['text: this regression suite checks coloured surfaces; glyph validation belongs to increment25',
                   'input: no source feeds pw_wine_next_input',
                   "explorer's folder browser: COM classes and services are not in the increment 15 prefix",
                   'official shadPS4','PS4 hardware'],
    'artifact_hashes':{str(path.relative_to(ROOT)):sha(path) for path in (*contracts,out/'regressions-18/report.json')}}
def artifact_contents(mapping):
    # Evidence directories may be copied to a new campaign without changing any
    # contract bytes. Check their stable contract names and hashes, not the root.
    return {'/'.join(pathlib.Path(name).parts[-2:]):digest for name,digest in mapping.items()}
if args.verify_only and artifact_contents(result['artifact_hashes'])!=artifact_contents(previous['artifact_hashes']):
    failures.append('Evidence index changed');result['status']='failed'
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'report.json')
if failures:raise SystemExit('Unexpected results: '+', '.join(failures))
