#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Package a standalone process diagnostic; capability and launch behavior vary by build."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
from orbis_package import package_app
from orbis_self import set_exec_type

ROOT=Path(__file__).resolve().parents[1]
SDK=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',choices=['P001','P002','P003','P004','P005','P007','P009','P012','P013'],default='P001')
    parser.add_argument('--inspection-source',type=Path,help='P003 physical run folder with report.jsonl and snapshot; P004 only')
    args=parser.parse_args();build=args.build
    WORK=ROOT/('build/process-hardware-'+build.lower());APP=WORK/'app';OUT=ROOT/('out/process-hardware-'+build.lower())
    APP.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    commands=[]
    def run(command):
        command=list(map(str,command));commands.append(command)
        with (WORK/'build.log').open('a') as log:
            subprocess.run(command,cwd=ROOT,env=dict(os.environ,OO_PS4_TOOLCHAIN=str(SDK)),
                           stdout=log,stderr=subprocess.STDOUT,check=True)
    flags=['--target=x86_64-pc-freebsd12-elf','-fPIC','-march=btver2','-O2','-g',
           '-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections',
           '-isysroot',SDK,'-isystem',SDK/'include','-I',ROOT/'platform/ps4','-DPW_SINK_MAX_DUMPS=0']
    if build in ('P009','P012'):flags+=['-DP009']
    if build=='P013':flags+=['-DP013']
    if build in ('P003','P004'):flags+=['-DPROBE_BUILD="'+build+'"','-DPROBE_TAG="'+build.lower()+'"','-DPROBE_INSPECT_ONLY=1']
    if build=='P012':
        loader=json.loads((ROOT/'out/process-loader-p011/manifest.json').read_text())
        binary=ROOT/'out/process-loader-p011/elfldr.elf'
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=loader['artifacts']['elfldr.elf']['sha256']:raise RuntimeError('P011 differs from manifest')
        (WORK/'p012_expected_loader.h').write_text('#define PW_EXPECTED_LOADER_RECIPE "'+loader['recipe_sha256']+'"\n')
        flags+=['-DP012','-I',WORK]
    inspection=None
    if build=='P004':
        if not args.inspection_source:parser.error('P004 requires --inspection-source from P003')
        reference=args.inspection_source.resolve()
        rows=[json.loads(line) for line in (reference/'report.jsonl').read_text().splitlines() if line.strip()]
        snapshot=next(r for r in rows if r['event']=='spawn_code_snapshot' and r['saved'])
        raw=(reference/('posix-spawn-'+str(snapshot['module'])+'.bin')).read_bytes()
        if len(raw)!=512:raise RuntimeError('Expected a complete 512-byte P003 snapshot')
        base=int(snapshot['address'],16)
        listing=subprocess.check_output(['objdump','-D','-b','binary','-m','i386:x86-64',
            '--adjust-vma='+hex(base),reference/('posix-spawn-'+str(snapshot['module'])+'.bin')],text=True)
        targets=[]
        for line in listing.splitlines():
            if re.search(r'\bud2\b',line):break
            match=re.match(r'^\s*([0-9a-f]+):.*\bcall\s+(0x[0-9a-f]+)',line)
            if match:
                target=int(match[2],16)
                if not base<=target<base+len(raw) and target-base not in targets:targets.append(target-base)
        if not 1<=len(targets)<=8:raise RuntimeError('Unexpected external-call plan')
        fingerprint=14695981039346656037
        for value in raw:fingerprint=((fingerprint^value)*1099511628211)&0xffffffffffffffff
        plan=WORK/'inspection_plan.h'
        plan.write_text('#define P004_REFERENCE_BYTES 512\n#define P004_REFERENCE_FNV UINT64_C('+hex(fingerprint)+')\n'+
            'static const int64_t p004_calls[] = {'+','.join(map(str,targets))+'};\n')
        inspection={'reference_sha256':hashlib.sha256(raw).hexdigest(),'reference_bytes':len(raw),
                    'fingerprint_fnv64':hex(fingerprint),'relative_call_targets':targets}
        flags+=['-DPROBE_INSPECT_CALLEES=1','-I',WORK]
    sources=[ROOT/('native/process_loader_observer.c' if build=='P005' else 'native/process_p007_observer.c' if build in ('P007','P009','P012','P013') else
                   'native/process_hardware_probe.c' if build=='P001' else 'native/process_hardware_probe_v2.c'),
             ROOT/'platform/ps4/pw_wine_sink_ps4.c']
    if build!='P005':sources.insert(1,ROOT/'platform/ps4/pw_wine_net.c')
    objects=[]
    for source in sources:
        # OpenOrbis's CMSG_NXTHDR macro compares size_t to ptrdiff_t in the existing adapter.
        extra=['-Wno-sign-compare'] if source.name=='pw_wine_net.c' else []
        compiled_source=source
        if build not in ('P001','P007','P009','P012','P013') and source.name=='pw_wine_net.c':
            text=source.read_text()
            signature='static void trace(const char *call,const char *stage,int error,const PwMessage *wire)\n{'
            if text.count(signature)!=1:raise RuntimeError('Network adapter trace context changed')
            text=text.replace(signature,'extern void p002_net_trace(const char *,const char *,int,int,unsigned);\n'+signature+
                '\n    p002_net_trace(call,stage,error,wire?wire->flags:0,wire?wire->controllen:0);')
            compiled_source=WORK/'net-instrumented.c';compiled_source.write_text(text)
        obj=WORK/(source.stem+'.o');run(['clang',*flags,*extra,'-c',compiled_source,'-o',obj]);objects.append(obj)
    elf=WORK/'process.elf'
    run(['ld.lld','-pie','--gc-sections','--no-undefined','--eh-frame-hdr','--script',SDK/'link.x',
         '-o',elf,*objects,SDK/'lib/crt1.o','-L',SDK/'lib','-lc','-lkernel','-lSceVideoOut',*(['-lSceNet'] if build in ('P005','P007','P009','P012','P013') else [])])
    run([SDK/'bin/linux/create-fself','-in='+str(elf),'-out='+str(WORK/'process.oelf'),
         '--eboot',APP/'eboot.bin','--paid','0x3800000000000011'])
    if build in ('P005','P007'):
        helper=WORK/'payload.o'
        run(['clang','--target=x86_64-pc-freebsd12-elf','-O2','-Wall','-Wextra','-Werror',
             '-ffreestanding','-fno-builtin','-fno-stack-protector','-fPIC','-mno-red-zone',
             '-c',ROOT/('native/process_p007_helper.c' if build=='P007' else 'native/process_loader_helper.c'),'-o',helper])
        run(['ld.lld','-pie','--no-dynamic-linker','--no-undefined','-z','max-page-size=16384',
             '-e','_start',helper,'-o',APP/'process-helper.elf'])
        undefined=subprocess.check_output(['llvm-nm-14','--undefined-only',APP/'process-helper.elf'],text=True)
        if undefined.strip():raise RuntimeError('Freestanding helper has unresolved imports')
    if build=='P013':
        # The child is a dynamically-linked ELF built with the PS4 PAYLOAD SDK toolchain, exactly like the
        # samples elfldr is designed to load (hello_stdio, ps, mntinfo): its CRT self-resolves the NEEDED
        # .sprx modules (__rtld_init) and puts main at the offset elfldr's breakpoint expects. The earlier
        # P013 child, built with OpenOrbis crt1.o, stalled elfldr_spawn at kevent. Sent as process-helper.elf.
        PSDK=ROOT/'.deps/process-loader/sdk/ps4-payload-sdk'
        payload=['-Wall','-g','-I',ROOT/'native','-o',APP/'process-helper.elf',ROOT/'native/process_p013_payload_child.c']
        command=[PSDK/'bin/orbis-clang',*map(str,payload)];commands.append(list(map(str,command)))
        with (WORK/'build.log').open('a') as log:
            subprocess.run(list(map(str,command)),cwd=ROOT,env=dict(os.environ,PS4_PAYLOAD_SDK=str(PSDK)),
                           stdout=log,stderr=subprocess.STDOUT,check=True)
        kind=subprocess.check_output(['llvm-readelf-14','-h',str(APP/'process-helper.elf')],text=True)
        if 'DYN (' not in kind:raise RuntimeError('P013 payload child is not a PIE ELF')
    if build in ('P009','P012'):
        # The child is linked as the Wine eboot is (tools/build-wine-hardware.py, W217): the SDK's link.x
        # starting at 0x1100000000, ET_SCE_EXEC, static libc, the same system libraries as DT_NEEDED.
        script=(SDK/'link.x').read_text()
        for old,new in (('*(.init_array);','KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*))); KEEP(*(.init_array));'),
                        ('*(.data)','*(.data .data.*)'),('*(.tdata)','*(.tdata .tdata.*)'),('*(.tbss)','*(.tbss .tbss.*)')):
            if old not in script:raise RuntimeError('unexpected SDK link.x: no '+old)
            script=script.replace(old,new)
        if not script.startswith('SECTIONS\n{'):raise RuntimeError('unexpected SDK link.x start')
        script='SECTIONS\n{\n\t. = 0x1100000000;\n\tHIDDEN(__dso_handle = .);\n'+script[len('SECTIONS\n{'):]
        (WORK/'child-link.x').write_text(script)
        child_objects=[]
        for source in (ROOT/'native/process_p009_child.c',ROOT/'platform/ps4/pw_wine_net.c'):
            obj=WORK/('child-'+source.stem+'.o');extra=['-Wno-sign-compare'] if source.name=='pw_wine_net.c' else []
            run(['clang',*[f for f in flags if f!='-DP009'],*extra,'-I',ROOT/'native','-c',source,'-o',obj]);child_objects.append(obj)
        child_elf=WORK/'child.elf'
        run(['ld.lld','-pie','--gc-sections','--no-undefined','--eh-frame-hdr','--script',WORK/'child-link.x',
             '-o',child_elf,*child_objects,SDK/'lib/crt1.o','-L',SDK/'lib','-lc','-lkernel','-lkernel_sys','-lSceNet',
             '-lSceVideoOut','-lSceAudioOut','-lSceSysmodule','-lSceSystemService','-lScePad','-lSceUserService','-lSceRtc'])
        # an app SELF (the default "fake" type: system_exec/npdrm_exec got ENOEXEC on the console), run by the
        # P010 loader inside this title's sandbox root
        run([SDK/'bin/linux/create-fself','-in='+str(child_elf),'-out='+str(WORK/'child.oelf'),
             '--eboot',APP/'process-child.self','--paid','0x3800000000000011'])
        (WORK/'child.exec.oelf').write_bytes(set_exec_type(WORK/'child.oelf',APP/'process-child.self'))
    if build=='P002':
        child=WORK/'child.o';child_elf=WORK/'child.elf'
        run(['clang',*flags,'-c',ROOT/'native/process_probe_child.c','-o',child])
        run(['ld.lld','-pie','--gc-sections','--no-undefined','--eh-frame-hdr','--script',SDK/'link.x',
             '-o',child_elf,child,SDK/'lib/crt1.o','-L',SDK/'lib','-lc','-lkernel'])
        run([SDK/'bin/linux/create-fself','-in='+str(child_elf),'-out='+str(WORK/'child.oelf'),
             '--eboot',APP/'process-child.bin','--paid','0x3800000000000011'])
    title='OrbisDesk Process Check '+build
    version={'P001':'01.00','P002':'01.01','P003':'01.02','P004':'01.03','P005':'01.04','P007':'01.06','P009':'01.11','P012':'01.12','P013':'01.16'}[build]
    pkg=package_app(ROOT,APP,OUT,title,'ORBP00001','IV0000-ORBP00001_00-ORBISDESKPROC001',
                    version=version,filename='OrbisDesk-Process-Check-'+build+'.pkg')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    extra_sources=[ROOT/'native/process_probe_shared.h',WORK/'net-instrumented.c'] if build in ('P002','P003','P004') else []
    if build=='P005':extra_sources += [ROOT/'native/process_loader_helper.c',ROOT/'native/process_loader_protocol.h']
    if build=='P007':extra_sources += [ROOT/'native/process_p007_helper.c',ROOT/'native/process_p007_protocol.h',ROOT/'native/process_loader_protocol.h']
    if build in ('P009','P012'):extra_sources += [ROOT/'native/process_p009_child.c',ROOT/'native/process_p007_protocol.h',ROOT/'native/process_loader_protocol.h',WORK/'child-link.x']
    if build=='P012':extra_sources += [ROOT/'native/process_loader_identity.h',WORK/'p012_expected_loader.h']
    if build=='P002':extra_sources.append(ROOT/'native/process_probe_child.c')
    if build=='P004':extra_sources += [ROOT/'native/process_probe_inspect.h',WORK/'inspection_plan.h']
    manifest={'build':build,'version':version,'title':title,'title_id':'ORBP00001',
              'package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),'package_bytes':pkg.stat().st_size,
              'eboot_sha256':sha(APP/'eboot.bin'),'commands':commands,
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'sources':{str(p.relative_to(ROOT)):sha(p) for p in [*sources,*extra_sources,ROOT/'native/hw_text.h',Path(__file__).resolve()]},
              'imports':subprocess.check_output(['llvm-nm-14','--undefined-only',elf],text=True).splitlines(),
              'report_root':'/data/orbisdesk/process-'+build.lower(),'hardware_status':'pending',
              'cross_process_ipc_verified':False,'native_spawn_attempted':False,
              'native_spawn_probe_enabled':build=='P002','no_wine_execution':True,
              'spawn_inspection_only':build in ('P003','P004'),'inspection_plan':inspection,
              'external_loader_request_enabled':build in ('P005','P007','P009','P012','P013'),'bootstrap_executed_by_title':False,
              'helper_elf_sha256':sha(APP/'process-helper.elf') if build in ('P005','P007','P013') else None,
              'child_sha256':sha(APP/'process-child.bin') if build=='P002' else sha(APP/'process-child.self') if build in ('P009','P012') else None}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('build','package','package_sha256','package_bytes','title_id')}))


if __name__=='__main__':
    main()
