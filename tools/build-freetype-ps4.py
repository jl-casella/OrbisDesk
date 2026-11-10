#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the pinned FreeType sources for Orbis, never the host FreeType library."""
import hashlib,json,pathlib,shutil,subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP='-ffile-prefix-map=%s=. -ffile-prefix-map=%s=vk-h0'%(ROOT,pathlib.Path.home()/'vk-h0')
source=ROOT/'.deps/shadPS4-fork/externals/freetype'
work=ROOT/'build/freetype-ps4';work.mkdir(parents=True,exist_ok=True)
sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
lock=json.loads((ROOT/'fork.lock.json').read_text())
commit=subprocess.check_output(['git','-C',str(ROOT/'.deps/shadPS4-fork'),'rev-parse','HEAD'],text=True).strip()
if commit!=lock['commit']:
    # Replaying the locked patches can change commit metadata, not the source tree.
    expected=json.loads((ROOT/'dependencies.lock.json').read_text())['shadps4_fork']['expected_head_tree']
    actual=subprocess.check_output(['git','-C',str(ROOT/'.deps/shadPS4-fork'),'rev-parse','HEAD^{tree}'],text=True).strip()
    if actual!=expected:raise SystemExit('FreeType parent tree is not the pinned fork tree')
source_commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
gitlink=subprocess.check_output(['git','-C',str(ROOT/'.deps/shadPS4-fork'),'ls-tree','HEAD','externals/freetype'],text=True).split()[2]
if source_commit!=gitlink:raise SystemExit('FreeType submodule differs from the pinned gitlink')
subprocess.run(['git','-C',str(source),'-c','core.autocrlf=true','-c','core.filemode=false',
                'diff','--exit-code','--ignore-submodules=all','HEAD','--'],check=True,stdout=subprocess.DEVNULL)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
inputs={str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*'))
        if p.is_file() and '.git' not in p.relative_to(source).parts}
flags=(f'--target=x86_64-pc-freebsd12-elf -fPIC -march=btver2 -isysroot {sdk} -isystem {sdk}/include '
       f'-include {ROOT}/platform/ps4/pw_freetype_posix.h -I{ROOT}/platform/ps4 '
       '-DFT_CONFIG_OPTIONS_H=\\\"pw_freetype_options.h\\\" '+PREFIX_MAP)
configure=['cmake','-S',str(source),'-B',str(work),'-G','Ninja','-DCMAKE_SYSTEM_NAME=FreeBSD',
           '-DCMAKE_SYSTEM_PROCESSOR=x86_64','-DCMAKE_C_COMPILER=clang','-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY',
           '-DCMAKE_C_FLAGS='+flags,'-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=OFF',
           *['-DFT_DISABLE_'+name+'=TRUE' for name in ('ZLIB','BZIP2','PNG','HARFBUZZ','BROTLI')]]
with (work/'configure.log').open('w') as log:subprocess.run(configure,stdout=log,stderr=subprocess.STDOUT,check=True)
with (work/'build.log').open('w') as log:subprocess.run(['cmake','--build',str(work),'--parallel','12'],stdout=log,stderr=subprocess.STDOUT,check=True)
library=work/'libfreetype.a'
licenses=work/'licenses';licenses.mkdir(exist_ok=True)
for name in ('LICENSE.TXT','docs/FTL.TXT'):
    shutil.copyfile(source/name,licenses/pathlib.Path(name).name)
manifest={'schema_version':1,'adapter_sha256':sha(ROOT/'platform/ps4/pw_freetype_posix.h'),'fork_commit':commit,
    'options_sha256':sha(ROOT/'platform/ps4/pw_freetype_options.h'),'mac_resource_forks':False,
    'source_commit':source_commit,'source_hashes':inputs,'configure':configure,
    'library':str(library.relative_to(ROOT)),'sha256':sha(library),'license':'FTL',
    'attribution':'Portions of this software are copyright © 2025 The FreeType Project (https://freetype.org). All rights reserved.',
    'licenses':{str(p.relative_to(ROOT)):sha(p) for p in licenses.iterdir()}}
(work/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'library':manifest['library'],'sha256':manifest['sha256']}))
