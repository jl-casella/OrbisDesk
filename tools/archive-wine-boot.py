#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Snapshot the full Wine Unix experiment before another overlay is prepared."""
import argparse,hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('destination',type=pathlib.Path);args=parser.parse_args()
destination=args.destination.resolve()
if not destination.is_relative_to(ROOT/'reports') or destination.exists():
    raise SystemExit('Expected a new directory inside reports')
link=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())
if link.get('bootstrap_exit_code')!=0:raise SystemExit('Bootstrap was not linked')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for relative,digest in link['object_hashes'].items():
    if sha(ROOT/relative)!=digest:raise SystemExit('Changed object: '+relative)
if sha(ROOT/'build/wine-boot/eboot.bin')!=link['bootstrap_sha256']:raise SystemExit('Changed executable')
source_status=subprocess.check_output(['git','-C',str(ROOT/'.deps/wine/source'),'status','--porcelain'],text=True)
if source_status.strip():raise SystemExit('Wine source has unrecorded modifications')
client=json.loads((ROOT/'build/wine-boot/report.json').read_text())
server=json.loads((ROOT/'build/wine-server/report.json').read_text())
for build in (client,server):
    for path,entry in build['overlay']['files'].items():
        if sha(ROOT/'.deps/wine/ps4-overlay'/path)!=entry['patched_sha256']:
            raise SystemExit('Changed overlay: '+path)
files=set()
for directory in ('build/wine-boot','build/wine-server','platform/ps4','patches/wine','.deps/wine/ps4-overlay'):
    files.update(p for p in (ROOT/directory).rglob('*') if p.is_file())
for pattern in ('native/wine_*.c','fixtures/win32/console*.c','tests/wine_fs.c','tools/*wine*.py','tools/*wine*.ps1','tools/*shad*.py','tools/*linux*.py','tools/check-increment*.py','tools/shad-linux-toolchain.cmake'):
    files.update(ROOT.glob(pattern))
for name in ('sources.lock.json','linux-emulator.lock.json','linux-runtime.lock.json','out/wine-pe64/manifest.json',
             'out/wine/wine-runtime-manifest.json','.deps/wine/ps4-unix/include/config.h','.deps/wine/ps4-unix/orbis-cc'):
    files.add(ROOT/name)
for pattern in ('*.h','bits/*.h','orbis/_types/kernel.h'):
    files.update((ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain/include').glob(pattern))
for name in ('sys/socket.h','sys/uio.h','sys/statfs.h','sys/stat.h','orbis/libkernel.h'):
    files.add(ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain/include'/name)
for name in ('out/console32-bare.exe','out/console32-bare.json','fork.lock.json'):
    files.add(ROOT/name)
files.add(ROOT/'tools/prepare-host-prefix.py')
files.add(ROOT/'tools/package-wine-prefix.py')
identities={}
destination.mkdir(parents=True)
for path in sorted(files):
    relative=path.relative_to(ROOT);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,target);identities[str(relative)]={'sha256':sha(target),'bytes':target.stat().st_size}
versions={name:subprocess.check_output([name,'--version'],text=True).splitlines()[0] for name in ('clang','ld.lld','objcopy','ar')}
evidence={'schema_version':1,'files':identities,'tools':versions,'wine_commit':client['wine_commit'],
          'source_pristine':True,'Wine_booted':False,'hardware_status':'pending',
          'scope':'Full Unix ntdll and namespaced in-process wineserver, strict link; startup blocked at runtime'}
(destination/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(destination/'evidence.json')
