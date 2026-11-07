#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run with Windows Python: pack source once without per-header WSL/DrvFS I/O."""
import hashlib,io,json,os,pathlib,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1];source=ROOT/'.deps/shadPS4-fork'
files={};archive_path=ROOT/'build/shad-source-cache.tar'
with tarfile.open(archive_path,'w') as archive:
    for directory,dirs,names in os.walk(source):
        dirs[:]=[d for d in dirs if d!='.git']
        for name in names:
            if name=='.git':continue
            path=pathlib.Path(directory)/name;relative=path.relative_to(source).as_posix()
            if path.is_symlink():raise SystemExit('Unexpected source symlink: '+relative)
            data=path.read_bytes();files[relative]=hashlib.sha256(data).hexdigest()
            entry=tarfile.TarInfo(relative);entry.size=len(data);entry.mtime=path.stat().st_mtime
            entry.mode=0o644;archive.addfile(entry,io.BytesIO(data))
digest=hashlib.sha256()
with archive_path.open('rb') as stream:
    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
report={'files':files,'archive_sha256':digest.hexdigest(),
        'source_commit':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
        'source_patch_sha256':hashlib.sha256(subprocess.check_output(['git','-C',str(source),'diff','--ignore-submodules=all','HEAD','--binary'])).hexdigest(),
        'scope':'Byte-identical compiler read cache; original source remains authoritative'}
(ROOT/'build/shad-source-cache.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'files':len(files),'archive_bytes':archive_path.stat().st_size}))
