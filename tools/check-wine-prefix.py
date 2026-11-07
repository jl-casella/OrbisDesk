#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exercise the real package consumer with valid and corrupted portable prefixes."""
import copy
import io
import json
import pathlib
import struct
import tarfile
import tempfile
from wine_prefix import digest, stage_package, validate_package

ROOT=pathlib.Path(__file__).resolve().parents[1]
source=ROOT/'reports/increment15/prefix-package'
commit=json.loads((ROOT/'build/wine-boot/report.json').read_text())['wine_commit']
out=ROOT/'reports/increment19';out.mkdir(parents=True,exist_ok=True)
results=[]
with tempfile.TemporaryDirectory(prefix='prefix-contract-') as temporary:
    root=pathlib.Path(temporary)
    destination=root/'valid';destination.mkdir()
    verified=stage_package(source,destination,commit)
    assert (destination/'dosdevices/c:').readlink().as_posix()=='../drive_c'
    assert (destination/'dosdevices/z:').readlink().as_posix()=='../..'
    results.append({'case':'valid-package','status':'passed','verified':verified})
    for case in ('archive-hash','file-altered','registry-missing','unsafe-link','unsafe-path','wrong-architecture','wrong-revision','duplicate-entry'):
        directory=root/case;directory.mkdir()
        manifest=json.loads((source/'manifest.json').read_text())
        with tarfile.open(source/'prefix.tar.gz','r:gz') as original, tarfile.open(directory/'prefix.tar.gz','w:gz',compresslevel=1) as changed:
            for item in original:
                if case=='registry-missing' and item.name=='prefix/system.reg':
                    del manifest['entries']['system.reg'];continue
                data=original.extractfile(item).read() if item.isfile() else None
                item=copy.copy(item)
                if case=='unsafe-link' and item.name=='prefix/dosdevices/c:':
                    item.linkname='/tmp/escape';manifest['entries']['dosdevices/c:']['target']=item.linkname
                if item.name=='prefix/drive_c/orbis/console32.exe':
                    if case=='file-altered':data=data[:-1]+bytes([data[-1]^1])
                    if case=='wrong-architecture':
                        data=bytearray(data);offset=struct.unpack_from('<I',data,60)[0]
                        struct.pack_into('<H',data,offset+4,0x8664);struct.pack_into('<H',data,offset+24,0x20b)
                        data=bytes(data);manifest['entries']['drive_c/orbis/console32.exe']['sha256']=digest(data)
                changed.addfile(item,io.BytesIO(data) if data is not None else None)
                if case=='duplicate-entry' and item.name=='prefix/system.reg':changed.addfile(item,io.BytesIO(data))
            if case=='unsafe-path':
                item=tarfile.TarInfo('prefix/../escape');item.size=1
                changed.addfile(item,io.BytesIO(b'x'))
                manifest['entries']['../escape']={'type':'file','bytes':1,'sha256':digest(b'x')}
        manifest['archive_sha256']=digest((directory/'prefix.tar.gz').read_bytes())
        if case=='archive-hash':manifest['archive_sha256']='0'*64
        if case=='wrong-revision':manifest['wine_commit']='0'*40
        (directory/'manifest.json').write_text(json.dumps(manifest))
        target=root/('stage-'+case);target.mkdir()
        try:stage_package(directory,target,commit)
        except ValueError as error:
            assert not list(target.iterdir()),'Consumer wrote files before rejecting '+case
            results.append({'case':case,'status':'passed','rejection':str(error)})
        else:raise AssertionError('Invalid package accepted: '+case)
        print(case+': rejected',flush=True)
report={'status':'passed','scope':'Host package validation; no Wine or emulator execution','cases':results,
        'inputs':{str(path.relative_to(ROOT)):digest(path.read_bytes()) for path in
                  (pathlib.Path(__file__),ROOT/'tools/wine_prefix.py',source/'manifest.json',source/'prefix.tar.gz')}}
(out/'prefix-contract.json').write_text(json.dumps(report,indent=2)+'\n')
print(out/'prefix-contract.json')
