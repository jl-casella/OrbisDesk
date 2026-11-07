#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Install only the explicitly owned Linux compiler cache, verifying every file."""
import hashlib,json,pathlib,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
destination=pathlib.Path.home()/'.cache/orbisdesk/shad-source'
destination.mkdir(parents=True,exist_ok=True);destination=destination.resolve()
manifest=json.loads((ROOT/'build/shad-source-cache.json').read_text());archive_path=ROOT/'build/shad-source-cache.tar'
digest=hashlib.sha256()
with archive_path.open('rb') as stream:
    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
if digest.hexdigest()!=manifest['archive_sha256']:
    raise SystemExit('Source archive mismatch')
with tarfile.open(archive_path) as archive:
    seen=set()
    for entry in archive:
        target=(destination/entry.name).resolve()
        if not entry.isfile() or not target.is_relative_to(destination) or entry.name not in manifest['files']:
            raise SystemExit('Unexpected cache entry')
        data=archive.extractfile(entry).read()
        if hashlib.sha256(data).hexdigest()!=manifest['files'][entry.name]:raise SystemExit('Cache file mismatch')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);seen.add(entry.name)
if seen!=set(manifest['files']):raise SystemExit('Incomplete cache archive')
index=destination.parent/'shad-source-files.json'
previous=json.loads(index.read_text()) if index.exists() else []
for relative in set(previous)-seen:
    target=(destination/relative).resolve()
    if not target.is_relative_to(destination):raise SystemExit('Invalid prior cache index')
    if target.is_file():target.unlink()
index.write_text(json.dumps(sorted(seen))+'\n')
overlay={'version':0,'case-sensitive':True,'use-external-names':False,
         'roots':[{'type':'directory-remap','name':str(ROOT/'.deps/shadPS4-fork'),'external-contents':str(destination)}]}
(ROOT/'build/shad-source-vfs.json').write_text(json.dumps(overlay,indent=2)+'\n')
print(json.dumps({'files_verified':len(seen),'cache':str(destination)}))
