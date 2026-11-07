#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and run an independent OpenOrbis reproduction of the image-mapping blocker."""
import hashlib,json,os,pathlib,resource,shutil,signal,subprocess,tarfile,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'reports/increment20/protect-reproducer';out.mkdir(parents=True,exist_ok=True)
sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain';source=ROOT/'native/wine_file_protect_repro.c'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
commands=[['clang','--target=x86_64-pc-freebsd12-elf','-fPIC','-O2','-g','-isysroot',str(sdk),'-isystem',str(sdk/'include'),'-c',str(source),'-o',str(out/'main.o')],
 ['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',str(sdk/'link.x'),'-o',str(out/'repro.elf'),str(out/'main.o'),str(sdk/'lib/crt1.o'),'-L'+str(sdk/'lib'),'-lc','-lkernel'],
 [str(sdk/'bin/linux/create-fself'),'-in='+str(out/'repro.elf'),'-out='+str(out/'repro.oelf'),'--eboot',str(out/'eboot.bin'),'--paid','0x3800000000000011']]
with (out/'build.log').open('w') as log:
    for command in commands:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk)))
shutil.copyfile(source,out/source.name)
runs={}
for name,options in (('fork',['--fork']),('official',[])):
    directory=out/name;directory.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mmap-repro-') as temporary:
        root=pathlib.Path(temporary);data=root/'data';data.mkdir();(data/'image.bin').write_bytes(bytes([0x52])*65536)
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
        passed='PWPROTECT private-write=1' in text and code==0 and not timeout
        runs[name]={'status':'passed' if passed else 'blocked','exit_code':code,'timed_out':timeout,
            'request_reached':'PWPROTECT requesting' in text,'return_reached':'PWPROTECT returned' in text,
            'mprotect_assertion':'mprotect failed: Permission denied' in text,
            'duration_seconds':round(time.monotonic()-start,3),'command':command,'elf_sha256':sha(out/'eboot.bin')}
        (directory/'report.json').write_text(json.dumps(runs[name],indent=2)+'\n')
        print(name+': '+runs[name]['status'],flush=True)
report={'scope':'Independent OpenOrbis private file mapping protection contract; no Wine','runs':runs,'commands':commands,
    'inputs':{str(path.relative_to(ROOT)):sha(path) for path in (source,pathlib.Path(__file__),sdk/'include/orbis/libkernel.h',sdk/'lib/libc.a',sdk/'lib/libkernel.so')},
    'elf_sha256':sha(out/'eboot.bin'),'hardware_status':'pending'}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
