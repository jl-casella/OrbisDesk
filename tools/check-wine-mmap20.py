#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and run an independent OpenOrbis reproduction of the image-mapping blocker."""
import argparse,hashlib,json,os,pathlib,re,resource,shutil,signal,subprocess,tarfile,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--official',action='store_true');args=parser.parse_args()
out=ROOT/'reports/increment20/mmap-contract';out.mkdir(parents=True,exist_ok=True)
sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain';source=ROOT/'native/wine_mmap_probe.c'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
commands=[['clang','--target=x86_64-pc-freebsd12-elf','-fPIC','-O2','-g','-isysroot',str(sdk),'-isystem',str(sdk/'include'),'-c',str(source),'-o',str(out/'main.o')],
 ['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',str(sdk/'link.x'),'-o',str(out/'repro.elf'),str(out/'main.o'),str(sdk/'lib/crt1.o'),'-L'+str(sdk/'lib'),'-lc','-lkernel'],
 [str(sdk/'bin/linux/create-fself'),'-in='+str(out/'repro.elf'),'-out='+str(out/'repro.oelf'),'--eboot',str(out/'eboot.bin'),'--paid','0x3800000000000011']]
with (out/'build.log').open('w') as log:
    for command in commands:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk)))
shutil.copyfile(source,out/source.name)
runs={}
for name,options in ([('fork',['--fork']),('official',[])] if args.official else [('fork',['--fork'])]):
    directory=out/name;directory.mkdir(exist_ok=True)
    emulator=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text()) if name=='fork' else None
    if emulator:
        if sha(ROOT/'build/shadPS4-linux/shadps4')!=emulator['executable_sha256']:raise SystemExit('Emulator manifest mismatch')
        shutil.copyfile(ROOT/'build/shadPS4-linux/build-manifest.json',directory/'emulator-build.json')
    with tempfile.TemporaryDirectory(prefix='mmap-repro-') as temporary:
        root=pathlib.Path(temporary);data=root/'data';data.mkdir();(data/'image.bin').write_bytes(bytes(16384)+bytes([0x52])*49152)
        guest=root/'guest';guest.mkdir();shutil.copyfile(out/'eboot.bin',guest/'eboot.bin')
        command=['python3',str(ROOT/'tools/run-linux-shad.py'),*options,'--config-clean','--fullscreen','false','--mount',str(data),'/data','-g',str(guest/'eboot.bin'),'--','/app0/eboot.bin']
        start=time.monotonic();timeout=False
        with (directory/'stdout.log').open('w') as log:
            process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
            try:code=process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                timeout=True;os.killpg(process.pid,signal.SIGKILL);code=process.wait()
        text=(directory/'stdout.log').read_text(errors='replace')
        with tarfile.open(directory/'runtime.tar.gz','w:gz') as archive:archive.add(root,arcname='runtime')
        cases=[json.loads(item) for item in re.findall(r'PWMMAP (\{[^\r\n]+\})',text)]
        stubs=sorted(set(re.findall(r'\bStub: ([^\r\n(]+) \(nid:',text)))
        passed=len(cases)==6 and all(item['status']=='passed' for item in cases) and code==0 and not timeout and not stubs
        runs[name]={'status':'passed' if passed else 'blocked','exit_code':code,'timed_out':timeout,
            'cases':cases,'invoked_stubs':stubs,'emulator':emulator,'request_reached':'PWMMAP requesting' in text,
            'mmap_assertion':'mmap failed: Invalid argument' in text,
            'duration_seconds':round(time.monotonic()-start,3),'command':command,'elf_sha256':sha(out/'eboot.bin')}
        (directory/'report.json').write_text(json.dumps(runs[name],indent=2)+'\n')
        print(name+': '+runs[name]['status'],flush=True)
report={'scope':'Independent OpenOrbis mmap error contract; no Wine','runs':runs,'commands':commands,
    'inputs':{str(path.relative_to(ROOT)):sha(path) for path in (source,pathlib.Path(__file__),sdk/'include/orbis/libkernel.h',sdk/'lib/libc.a',sdk/'lib/libkernel.so')},
    'elf_sha256':sha(out/'eboot.bin'),'hardware_status':'pending'}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
if runs['fork']['status']!='passed':raise SystemExit('Fork mmap contract failed')
