#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build an external PS4 loader research artifact. Never deploy or execute it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--llvm-config',default='/usr/bin/llvm-config-19')
    args=parser.parse_args()
    pins=json.loads((ROOT/'tools/process-loader.lock.json').read_text())
    deps=ROOT/'.deps/process-loader';deps.mkdir(parents=True,exist_ok=True)
    archives={}
    for name,filename in (('sdk','sdk-v0.9.zip'),('elfldr','elfldr-source.tar.gz')):
        path=deps/filename;spec=pins[name]
        if not path.exists():
            if not args.fetch:raise RuntimeError('Missing archive; use --fetch: '+str(path))
            for attempt in range(3):
                try:
                    request=urllib.request.Request(spec['url'],headers={'User-Agent':'OrbisDesk-process-research'})
                    with urllib.request.urlopen(request,timeout=90) as src:path.with_suffix('.part').write_bytes(src.read())
                    if sha(path.with_suffix('.part'))!=spec['sha256']:raise RuntimeError('Download hash mismatch')
                    path.with_suffix('.part').replace(path);break
                except (OSError,TimeoutError):
                    if attempt==2:raise
                    time.sleep(2)
        if sha(path)!=spec['sha256']:raise RuntimeError('Archive hash mismatch: '+str(path))
        archives[name]=path
    sdkroot=deps/'sdk'
    with zipfile.ZipFile(archives['sdk']) as z:
        for entry in z.infolist():
            if not (sdkroot/entry.filename).resolve().is_relative_to(sdkroot.resolve()):raise RuntimeError('Unsafe SDK entry')
        z.extractall(sdkroot)
    sdk=sdkroot/'ps4-payload-sdk'
    for path in (sdk/'bin').iterdir():path.chmod(0o755)
    work=ROOT/'build/process-loader';work.mkdir(parents=True,exist_ok=True)
    # A new source directory each run avoids stale generated source or edited upstream code.
    import tempfile
    source_root=Path(tempfile.mkdtemp(prefix='source-',dir=work))
    with tarfile.open(archives['elfldr']) as archive:
        for entry in archive:
            if entry.issym() or entry.islnk() or not (source_root/entry.name).resolve().is_relative_to(source_root.resolve()):
                raise RuntimeError('Unsafe source entry')
        archive.extractall(source_root)
    source=source_root/('elfldr-'+pins['elfldr']['commit'])
    command=['make','-C',str(source),'-j2']
    env=dict(os.environ,PS4_PAYLOAD_SDK=str(sdk),LLVM_CONFIG=args.llvm_config)
    with (work/'build.log').open('w') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    out=ROOT/'out/process-loader';out.mkdir(parents=True,exist_ok=True)
    artifacts={}
    for name in ('elfldr.bin','elfldr.elf','socksrv.elf'):
        target=out/name;shutil.copy2(source/name,target)
        artifacts[name]={'sha256':sha(target),'bytes':target.stat().st_size}
    shutil.copy2(archives['elfldr'],out/'upstream-source.tar.gz')
    manifest={'classification':'external_loader_research','pins':pins,'command':command,
              'llvm_config':args.llvm_config,'compiler':subprocess.check_output([sdk/'bin/orbis-clang','--version'],env=env,text=True),
              'artifacts':artifacts,'bootstrap_changes_kernel_state':True,'console_execution':'not_performed',
              'goldhen_9090_compatibility':'pending',
              'firmware_source_cases':{'12.50':'source_branch_present_not_hardware_validated',
                                       '12.52':'source_branch_present_not_hardware_validated'},
              'source_archive':'upstream-source.tar.gz','license':'GPL-3.0-or-later',
              'sdk_archive_sha256':sha(archives['sdk'])}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'output':str(out),'artifacts':artifacts}))
if __name__=='__main__':main()
