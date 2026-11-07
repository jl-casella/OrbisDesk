#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validate and stage the real PE64 host modules built by Wine's Makefile."""
import hashlib,json,pathlib,shutil,struct,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
commit=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']
assert subprocess.check_output(['git','-C',str(ROOT/'.deps/wine/source'),'rev-parse','HEAD'],text=True).strip()==commit
modules={}
for name in ['ntdll','wow64','wow64win','apisetschema']:
    source=ROOT/'.deps/wine/runtime/build/dlls'/name/'x86_64-windows'/(name+'.dll')
    data=source.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    assert data[:2]==b'MZ' and data[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',data,pe+4)[0]==0x8664 and struct.unpack_from('<H',data,pe+24)[0]==0x20b
    relative='lib/x86_64-windows/'+source.name;out=ROOT/'out/wine-pe64'/relative
    out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,out)
    modules[source.name]={'path':relative,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'machine':'AMD64','format':'PE32+'}
manifest={'schema_version':1,'wine_commit':commit,'modules':modules,'source_patches':False,
          'build_command':['make','-j12',*[f'dlls/{n}/x86_64-windows/{n}.dll' for n in ['ntdll','wow64','wow64win','apisetschema']]],
          'build_log':'build/increment10-pe64.log','config_sha256':hashlib.sha256((ROOT/'.deps/wine/runtime/build/include/config.h').read_bytes()).hexdigest(),
          'wow64_cpu_backend_integrated':False,'Wine_booted':False}
(ROOT/'out/wine-pe64/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('Staged four verified PE64 modules')
