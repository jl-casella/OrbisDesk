#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rebuild the proven boot links after a win32u-only producer change.

Validate every existing base object and every new win32u object, combine the new
win32u, and execute both saved linker commands and create-fself. No unchanged
adapter is recompiled and no report is updated without successful real links.
"""
import datetime,hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
work=ROOT/'build/wine-boot';path=work/'link-report.json'
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
base=json.loads(path.read_text());producer=json.loads((ROOT/'build/win32u-ps4/report.json').read_text())
assert base['exit_code']==base['bootstrap_exit_code']==0
assert not any(x['exit_code'] for x in producer['results'])
for name,h in base['object_hashes'].items():assert sha(ROOT/name)==h,name
for name,h in producer['objects'].items():assert sha(ROOT/name)==h,name
for name,h in producer['pixel_sources'].items():assert sha(ROOT/name)==h,name
assert sha(work/'eboot.bin')==base['bootstrap_sha256']
target=work/'win32u.o';key=str(target.relative_to(ROOT))
assert key in base['object_hashes']
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
evidence=work/'win32u-relinks'/stamp;evidence.mkdir(parents=True)
shutil.copyfile(path,evidence/'previous-link-report.json')
outputs=[target,work/'ntdll.so',work/'bootstrap.elf',work/'bootstrap.oelf',work/'eboot.bin']
for p in outputs:
    if p.exists():shutil.copyfile(p,evidence/p.name)
commands=[]
def run(command):
    commands.append(list(map(str,command)))
    with (evidence/'link.log').open('a') as log:
        subprocess.run(commands[-1],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,
                       env=dict(os.environ,OO_PS4_TOOLCHAIN=str(ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain')))
try:
    combined=work/'win32u-combined.o'
    run(['ld.lld','-r','-o',combined,*[ROOT/name for name in producer['objects']]])
    run(['objcopy','--localize-hidden','--redefine-sym','__wine_unix_lib_init=pw_win32u_unix_lib_init',combined,target])
    assert base['command'].count(str(target))==base['bootstrap_command'].count(str(target))==1
    run(base['command'])
    run(base['bootstrap_command'])
    sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
    run([sdk/'bin/linux/create-fself','-in='+str(work/'bootstrap.elf'),'-out='+str(work/'bootstrap.oelf'),
         '--eboot',work/'eboot.bin','--paid','0x3800000000000011'])
except Exception:
    for p in outputs:
        if (evidence/p.name).exists():shutil.copyfile(evidence/p.name,p)
    raise
base['object_hashes'][key]=sha(target)
base['bootstrap_sha256']=sha(work/'eboot.bin')
refresh={'previous_link_report_sha256':sha(evidence/'previous-link-report.json'),
         'producer_report_sha256':sha(ROOT/'build/win32u-ps4/report.json'),
         'builder_sha256':sha(pathlib.Path(__file__)),'commands':commands,
         'outputs':{str(p.relative_to(ROOT)):sha(p) for p in outputs},'hardware_validation':'pending'}
base['win32u_refresh']=refresh
path.write_text(json.dumps(base,indent=2)+'\n')
(evidence/'result.json').write_text(json.dumps(refresh,indent=2)+'\n')
print(json.dumps({'status':'relinked-unvalidated','win32u_sha256':sha(target),'evidence':str(evidence.relative_to(ROOT))}))
