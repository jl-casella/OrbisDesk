#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validate real glyph rendering, fonts and the increment-24 regressions."""
import argparse,hashlib,json,pathlib,re,shutil,struct,subprocess,sys,tarfile,tempfile,zlib
from wine_fonts import stage_fonts
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--verify-only',action='store_true')
parser.add_argument('--collect-existing',type=pathlib.Path,help='Revalidate archived runs from a previous campaign into a new report directory')
parser.add_argument('--reuse-regressions',type=pathlib.Path,help='Verify a prior increment24 evidence directory for the same ELF instead of repeating unchanged runs')
parser.add_argument('--reuse-platform',type=pathlib.Path,help='Reuse unchanged native platform checks while rerunning all Wine regressions')
parser.add_argument('--report-dir',type=pathlib.Path,default=ROOT/'reports/increment25')
args=parser.parse_args();out=args.report_dir.resolve()
if args.collect_existing and args.reuse_regressions:parser.error('Choose --collect-existing or --reuse-regressions')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if args.verify_only:
    report=json.loads((out/'report.json').read_text());errors=[]
    for name,digest in report['artifacts'].items():
        if sha(out/name)!=digest:errors.append(name)
    for name,entry in report['runs'].items():
        if sha(ROOT/entry['report'])!=entry['report_sha256']:errors.append(name+' report')
        if sha(ROOT/entry['runtime'])!=entry['runtime_sha256']:errors.append(name+' runtime')
        if sha(ROOT/entry['stdout'])!=entry['stdout_sha256']:errors.append(name+' stdout')
    if errors:raise SystemExit('Evidence changed: '+', '.join(errors))
    if report['status']!='passed':raise SystemExit('Recorded result: '+report['status'])
    print('Increment25 evidence verified');raise SystemExit(0)
if (out/'report.json').exists():raise SystemExit('Report exists; choose a new --report-dir to preserve evidence')
out.mkdir(parents=True,exist_ok=True)
def execute(command,log):
    with log.open('w') as output:subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)
def export_frame(path,target,text_ink=None):
    with tarfile.open(path.parent/'runtime.tar.gz') as archive:
        frames=sorted(m for m in archive.getnames() if re.search(r'/frames/frame-.*\.bmp$',m))
        if not frames:raise ValueError('No frame evidence')
        bitmaps={name:archive.extractfile(name).read() for name in frames}
        # Closing the fixture presents a black desktop. Select its painted frame,
        # never that final black frame, and verify the DIB reached presentation.
        selected=frames[-1]
        data=bitmaps[selected]
    width,height=struct.unpack_from('<ii',data,18);height=abs(height)
    pixels=data[54:]
    if text_ink:
        # NONANTIALIASED_QUALITY gives a white client rectangle and black glyphs.
        # Find the full 480x160 DIB in the composed frame, independently of borders.
        found=False
        for candidate in frames:
            if found:break
            data=bitmaps[candidate];width,height=struct.unpack_from('<ii',data,18);height=abs(height);pixels=data[54:]
            rows3=[bytes(v for x in range(width) for v in pixels[(y*width+x)*4:(y*width+x)*4+3]) for y in range(height)]
            for y in range(height-159):
                if found:break
                for match in re.finditer(b'(?:\xff\xff\xff){480,}',rows3[y]):
                    x=match.start()//3
                    if x+480>width:continue
                    area=b''.join(row[x*3:(x+480)*3] for row in rows3[y:y+160])
                    ink=sum(area[i:i+3]==b'\0\0\0' for i in range(0,len(area),3))
                    white=sum(area[i:i+3]==b'\xff\xff\xff' for i in range(0,len(area),3))
                    if ink==text_ink and white+ink==480*160:
                        found=True;selected=candidate;break
        if not found:raise ValueError('Presented frame does not contain the rendered text DIB')
    label_pixels=None
    if not text_ink:
        # The pinned English explorer draws Start next to the wine icon. Ignore
        # the icon and the upper taskbar border; an icon-only bar must fail.
        label_pixels=sum(pixels[(y*width+x)*4:(y*width+x)*4+3]==b'\0\0\0'
                         for y in range(height-16,height-4) for x in range(28,75))
        if label_pixels<25:raise ValueError('Explorer has no visible Start label')
    rows=b''.join(b'\0'+bytes(v for x in range(width) for v in
        (pixels[(y*width+x)*4+2],pixels[(y*width+x)*4+1],pixels[(y*width+x)*4])) for y in range(height))
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    target.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
        chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))
    return {'archive_path':selected,'text_dib_ink':text_ink,'explorer_label_pixels':label_pixels}

failures=[];runs={};reports={}
reference=json.loads((ROOT/'reports/increment25-windows-reference/report.json').read_text(encoding='utf-8-sig'))
gui=json.loads((ROOT/'out/wine-gui/manifest.json').read_text())
if reference['exit_code']!=0 or not reference['result'].startswith('passed=1;family_tahoma=1;'):
    failures.append('Windows reference failed')
if reference['exe_sha256']!=gui['targets']['gui-text64.exe']['sha256'] or reference['font_sha256']!=gui['fonts']['tahoma.ttf']['sha256']:
    failures.append('Windows reference inputs differ')
# Test staging failures without touching a real prefix or the evidence package.
staging={}
for case in ('valid','altered','missing'):
    with tempfile.TemporaryDirectory() as tmp:
        directory=pathlib.Path(tmp);bundle=directory/'bundle';bundle.mkdir()
        prefix=directory/'prefix';prefix.mkdir();(prefix/'system.reg').write_text('WINE REGISTRY Version 2\n')
        font=bundle/'tahoma.ttf';font.write_bytes((ROOT/'out/wine-gui/fonts/tahoma.ttf').read_bytes())
        manifest={'tahoma.ttf':{'path':'tahoma.ttf','sha256':sha(font)}}
        if case=='altered':font.write_bytes(b'altered')
        if case=='missing':font.unlink()
        before=(prefix/'system.reg').read_bytes()
        try:stage_fonts(ROOT,bundle,manifest,prefix);accepted=True
        except (ValueError,FileNotFoundError):accepted=False
        staging[case]=accepted==(case=='valid') and (accepted or (
            (prefix/'system.reg').read_bytes()==before and not (prefix/'drive_c').exists()))
        if not staging[case]:failures.append('Font staging '+case)
package=['--prepared-prefix','reports/increment15/prefix-package','--wine-gui']
cases=[('text-'+str(i),['--fork',*package,'--wine-exe','C:\\orbis\\gui-text64.exe']) for i in range(1,4)]
cases.append(('explorer',['--fork',*package,'--wine-exe','C:\\windows\\explorer.exe','--wine-arg','/desktop=shell,800x600']))
for name,options in cases:
    log=out/(name+'-runner.log')
    if args.collect_existing:shutil.copyfile(args.collect_existing/log.name,log)
    else:execute([sys.executable,'tools/run-linux-wine.py','--timeout','45',*options],log)
    path=pathlib.Path(log.read_text().rsplit('Report: ',1)[1].strip())
    report=json.loads(path.read_text());reports[name]=report
    stdout=path.parent/'stdout.log';runtime=path.parent/'runtime.tar.gz'
    runs[name]={'report':str(path.relative_to(ROOT)),'report_sha256':sha(path),
        'runtime':str(runtime.relative_to(ROOT)),'runtime_sha256':sha(runtime),
        'stdout':str(stdout.relative_to(ROOT)),'stdout_sha256':sha(stdout),
        'status':report['status'],'text_result':report.get('text_result'),'Wine_booted':report['Wine_booted'],
        'windows_execution_verified':report['windows_execution_verified'],'duration_seconds':report['duration_seconds']}
    if report['invoked_stubs'] or report['unhandled_access_violation'] or not report['video_out_ready']:
        failures.append(name+': fault, stub or no VideoOut')
    link=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())
    if report['elf_sha256']!=link['bootstrap_sha256']:failures.append(name+': ELF differs from current build')
    if report.get('host_ld_preload') or report.get('winedebug') or report.get('wineenv'):
        failures.append(name+': diagnostic overrides enabled')
    if name.startswith('text-'):
        if report['status']!='passed' or report.get('text_exe_sha256')!=reference['exe_sha256']:
            failures.append(name+': text contract failed')
    elif not report['timed_out'] or not report['frames_presented']:
        failures.append('Explorer must present and stay running until timeout')
    ink_match=re.search(r';ink=(\d+)',report.get('text_result') or '') if name.startswith('text-') else None
    if report['frame_dumps']:
        runs[name]['presented_frame']=export_frame(path,out/(name+'.png'),int(ink_match[1]) if ink_match else None)
if args.collect_existing or args.reuse_regressions:
    source=args.reuse_regressions or args.collect_existing/'regressions24'
    shutil.copytree(source,out/'regressions24')
    if args.collect_existing:shutil.copyfile(args.collect_existing/'regressions24.log',out/'regressions24.log')
    execute([sys.executable,'tools/check-increment24.py','--verify-only','--report-dir',str(out/'regressions24')],out/'regressions24-verify.log')
else:
    execute([sys.executable,'tools/check-increment24.py','--report-dir',str(out/'regressions24'),
             *(['--reuse-platform',str(args.reuse_platform)] if args.reuse_platform else [])],out/'regressions24.log')
regressions=json.loads((out/'regressions24/report.json').read_text())
if regressions['status']!='passed':failures.append('Increment24 regressions')
capsule=out/'artifacts';capsule.mkdir(exist_ok=True)
sources=['tools/build-freetype-ps4.py','tools/build-win32u-ps4.py','tools/link-wine-boot.py',
         'tools/prepare-wine-boot.py','build/wine-boot/report.json','.deps/wine/ps4-overlay/dlls/ntdll/unix/virtual.c',
         'tools/stage-wine-gui.py','tools/wine_fonts.py','tools/run-linux-wine.py','tools/check-increment25.py',
         'tools/check-increment24.py','tools/reference-text25.ps1','fixtures/win32/gui_text.c','platform/ps4/pw_freetype_posix.h',
         'docs/THIRD_PARTY_FONTS.md','platform/ps4/pw_freetype_options.h',
         'build/freetype-ps4/manifest.json','build/freetype-ps4/libfreetype.a','build/freetype-ps4/licenses/FTL.TXT',
         'build/freetype-ps4/licenses/LICENSE.TXT','build/win32u-ps4/report.json','build/wine-boot/link-report.json',
         'build/wine-boot/eboot.bin','out/wine-gui/manifest.json','out/gui-text64.exe','fork.lock.json','sources.lock.json',
         'reports/increment25-windows-reference/report.json','reports/increment25-windows-reference/text-result.txt']
sources += [str(p.relative_to(ROOT)) for p in (ROOT/'out/wine-gui/fonts').iterdir() if p.is_file()]
for name in sources:
    target=capsule/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
artifacts={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='report.json'}
# Include nested reports too; only the top-level report is self-referential.
for p in out.rglob('report.json'):artifacts[str(p.relative_to(out))]=sha(p)
result={'schema_version':1,'status':'failed' if failures else 'passed','failures':failures,
    'classification':'validated in Linux shadPS4 fork' if not failures else 'validation incomplete',
    'hardware_status':'pending','official_status':'blocked; see regressions24 GUI comparison',
    'staging_tests':staging,'windows_reference':reference,'runs':runs,'artifacts':artifacts,
    'not_covered':['input','PE32 GUI','folder browser COM/services','PS4 hardware']}
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
print(out/'report.json')
if failures:raise SystemExit('; '.join(failures))
