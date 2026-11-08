#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Compile exact Wine Unix recipes with a small PS4 overlay.
Reuse the saved OpenOrbis configure result, not Linux config.h. Preserve each
object/log and complete command. This does not link or boot ntdll.so.
"""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import shutil
import subprocess
import time
from sdk_libc import derive_libc

ROOT=pathlib.Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--harness-only',action='store_true')
    parser.add_argument('--diagnose-remaining',action='store_true')
    parser.add_argument('--boot',action='store_true')
    parser.add_argument('--all-unix',action='store_true')
    parser.add_argument('--server',action='store_true')
    parser.add_argument('--libraries-only',action='store_true')
    args=parser.parse_args()
    subprocess.run(['python3',str(ROOT/('tools/prepare-wine-boot.py' if args.boot else 'tools/prepare-wine-ps4.py'))],check=True)
    work=ROOT/'.deps/wine/ps4-unix'; overlay=ROOT/'.deps/wine/ps4-overlay'
    manifest=json.loads((overlay/('boot-manifest.json' if args.boot else 'manifest.json')).read_text())
    makefile=(work/'Makefile').read_text()
    output=ROOT/('build/wine-server' if args.server else 'build/wine-boot' if args.boot else 'build/wine-ps4');output.mkdir(parents=True,exist_ok=True)
    results=[]
    names=['harness','loader-harness'] if args.harness_only else ['virtual','file','env','loader','cdrom','harness','loader-harness']
    if args.diagnose_remaining: names=['signal_x86_64','socket','sync','system','thread']
    if args.all_unix:
        start=makefile.index('dlls/ntdll/ntdll.so: ')
        end=makefile.index('\n\t$(CC)',start)
        names=list(dict.fromkeys(names+re.findall(r'dlls/ntdll/unix/(\w+)\.o',makefile[start:end])))
    if args.server:
        start=makefile.index('server/wineserver: ');end=makefile.index('\n\t$(CC)',start)
        names=list(dict.fromkeys(re.findall(r'server/(\w+)\.o',makefile[start:end])))
    previous=None
    if args.libraries_only:
        previous=json.loads((output/'report.json').read_text())
        if previous['overlay']!=manifest:raise SystemExit('Overlay changed: rebuild units before relinking libraries')
        names=[]
    for name in names:
        recipe_name='virtual' if name=='harness' else 'loader' if name=='loader-harness' else name
        subdir='server' if args.server else 'dlls/ntdll/unix'
        target=subdir+'/'+recipe_name+'.o'
        lines=makefile.splitlines()
        index=next((i for i,line in enumerate(lines) if line.startswith(target+': ') and i+1<len(lines) and lines[i+1].startswith('\t$(CC)')),None)
        if index is None: raise SystemExit('Missing exact Wine recipe: '+target)
        parts=[];index+=1
        while True:
            line=lines[index];parts.append(line.rstrip().removesuffix('\\'))
            if not line.rstrip().endswith('\\'): break
            index+=1
        command=' '.join(parts).replace('$(CC)',str(work/'orbis-cc')).replace('$(CFLAGS)','-g -O2')
        command=shlex.split(command.replace('$@',str(output/(name+'.o'))))
        original=str(ROOT/'.deps/wine/source'/subdir/ (recipe_name+'.c'))
        generated=not pathlib.Path(original).is_file()
        if generated: original=subdir+'/'+recipe_name+'.c'
        selected=ROOT/'native/wine_virtual_harness.c' if name=='harness' else ROOT/'native/wine_loader_harness.c' if name=='loader-harness' else overlay/'dlls/ntdll/unix'/(name+'.c')
        if name not in ('harness','loader-harness') and ('dlls/ntdll/unix/'+name+'.c') not in manifest['files']: selected=pathlib.Path(original)
        if args.server: selected=overlay/subdir/(recipe_name+'.c') if subdir+'/'+recipe_name+'.c' in manifest['files'] else pathlib.Path(original)
        if generated: selected=work/original
        command=[str(selected) if arg==original else arg for arg in command]
        command+=['-D__ORBIS__','-I'+str(ROOT/'platform/ps4'),'-I'+str(ROOT/'.deps/wine/source/dlls/ntdll/unix'),'-ffunction-sections','-fdata-sections']
        if args.server: command+=['-DWINE_INPROCESS_SERVER','-DPW_WINE_SERVER_SIDE','-I'+str(ROOT/'.deps/wine/source/server')]
        if args.boot: command+=['-include',str(ROOT/'platform/ps4/pw_wine_posix.h')]
        if name in ('harness','loader-harness'): command[1:1]=['-I'+str(overlay/'dlls/ntdll/unix')]
        start=time.monotonic()
        with (output/(name+'.log')).open('w') as log:
            run=subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT)
        obj=output/(name+'.o')
        reduction=None
        roots={'harness':'pw_wine_test_tryfixed','loader-harness':'pw_wine_test_paths',
               'file':'get_device_info','cdrom':'cdrom_DeviceIoControl'}
        if not run.returncode and name in roots and not args.server:
            # OpenOrbis link.x KEEP's all data.rel.ro, which otherwise roots
            # Wine's unrelated syscall tables. Reduce the diagnostic object
            # first with a normal relocatable link; keep full objects for the
            # actual port. Never ignore unresolved symbols or stub services.
            reduced=output/(name+'.diagnostic.o')
            reduction=['ld.lld','-r','--gc-sections','--undefined='+roots[name],'-o',str(reduced),str(obj)]
            subprocess.run(reduction,check=True)
        results.append({'unit':name,'exit_code':run.returncode,'status':'compiled' if not run.returncode else 'blocked',
                        'command':command,'duration_seconds':round(time.monotonic()-start,3),
                        'diagnostic_reduction':reduction,
                        'source_sha256':hashlib.sha256(selected.read_bytes()).hexdigest(),
                        'diagnostic_sha256':hashlib.sha256(reduced.read_bytes()).hexdigest() if reduction else None,
                        'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest() if not run.returncode else None})
        print(name+': '+results[-1]['status'],flush=True)
    libc=None
    if not args.diagnose_remaining:
        original_lib=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain/lib/libc.a'
        libc=derive_libc(original_lib,output/'lib/libc.a',boot=args.boot)
    report={'schema_version':1,'wine_commit':manifest['wine_commit'],'overlay':manifest,'results':results,'libc':libc,
            'config_sha256':hashlib.sha256((work/'include/config.h').read_bytes()).hexdigest(),
            'environment':'PS4 cross-compile, not Wine startup','hardware_status':'pending'}
    if previous is not None:report['results']=previous['results']
    (output/('remaining-report.json' if args.diagnose_remaining else 'harness-build.json' if args.harness_only else 'report.json')).write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(1 if any(r['exit_code'] for r in results) else 0)
if __name__=='__main__': main()
