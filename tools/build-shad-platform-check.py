# SPDX-License-Identifier: LGPL-2.1-or-later
import pathlib,subprocess,shutil,json,hashlib,os
from orbis_self import set_exec_type
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
work=ROOT/'build/shad-platform-check';app=work/'app';app.mkdir(parents=True,exist_ok=True)
script=work/'link.x';script.write_text((sdk/'link.x').read_text().replace('SECTIONS\n{','SECTIONS\n{\n . = 0x1100000000;'))
flags=['--target=x86_64-pc-freebsd12-elf','-fPIC','-march=btver2','-O2','-g','-Wall','-Wextra','-Werror','-isysroot',str(sdk),'-isystem',str(sdk/'include')]
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
with (work/'build.log').open('w') as log:
 def run(args):subprocess.run(list(map(str,args)),cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 run(['clang',*flags,'-c',ROOT/'native/shad_platform_check.c','-o',work/'check.o'])
 run(['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',script,'-o',work/'check.elf',work/'check.o',sdk/'lib/crt1.o','-L',sdk/'lib','-lkernel','-lc'])
 run([sdk/'bin/linux/create-fself','-in='+str(work/'check.elf'),'-out='+str(work/'check.oelf'),'--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
(work/'check.exec.oelf').write_bytes(set_exec_type(work/'check.oelf',app/'eboot.bin'))
(app/'sce_module').mkdir(exist_ok=True)
shutil.copyfile(sdk/'samples/hello_world/sce_module/libc.prx',app/'sce_module/libc.prx')
proof={'source':'native/shad_platform_check.c','source_sha256':hashlib.sha256((ROOT/'native/shad_platform_check.c').read_bytes()).hexdigest(),'eboot':str((app/'eboot.bin').relative_to(ROOT)),'eboot_sha256':hashlib.sha256((app/'eboot.bin').read_bytes()).hexdigest(),'type':'ET_SCE_EXEC','result':'/data/orbisdesk-platform-check.json','hardware':'pending'}
(work/'manifest.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
