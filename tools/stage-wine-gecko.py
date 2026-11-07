#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Phase 9: Wine Gecko 2.47.4, the HTML engine of Wine's MSHTML ("IE" for programs that embed it).

The upstream tarballs (https://dl.winehq.org/wine/wine-gecko/2.47.4/, MPL-2.0), pinned by
SHA-256, unmodified: x86_64 for 64-bit programs and x86 for 32-bit ones. 2.47.4 is the version
the pinned Wine asks for (dlls/appwiz.cpl/addons.c, dlls/mshtml/nsembed.c).

mshtml looks first for HKLM\\Software\\Wine\\MSHTML\\2.47.4 GeckoPath (nsembed.c find_wine_gecko_reg);
without it, it starts "control.exe appwiz.cpl install_gecko" in a new process, which the
single-process title cannot run. tools/build-wine-hardware.py copies each tree to the place the
.msi would use (C:\\windows\\system32\\gecko\\2.47.4\\<dir>, syswow64 for x86) and writes GeckoPath in
both registry views.
Run with python3 -I: the archives are untrusted input and are only read here.
Output: out/wine-gecko/{x86_64,x86}/wine-gecko-2.47.4-<arch>/... and manifest.json.
"""
import hashlib,json,pathlib,shutil,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='2.47.4'
ARCHIVES={'x86_64':('.deps/downloads/wine-gecko-2.47.4-x86_64/wine-gecko-2.47.4-x86_64.tar.xz',
                    'fd88fc7e537d058d7a8abf0c1ebc90c574892a466de86706a26d254710a82814'),
          'x86':('.deps/downloads/wine-gecko-2.47.4-x86/wine-gecko-2.47.4-x86.tar.xz',
                 '2cfc8d5c948602e21eff8a78613e1826f2d033df9672cace87fed56e8310afb6')}
out=ROOT/'out/wine-gecko'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
if out.exists():shutil.rmtree(out)
trees={}
for arch,(relative,digest) in ARCHIVES.items():
    archive_path=ROOT/relative
    if sha(archive_path)!=digest:raise SystemExit('Wine Gecko %s archive differs from the pinned release'%arch)
    top='wine-gecko-%s-%s'%(VERSION,arch)
    files={}
    with tarfile.open(archive_path) as archive:
        for member in archive:
            path=pathlib.PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0]!=top:
                raise SystemExit('Unexpected archive entry: '+member.name)
            if member.isdir():continue
            if not member.isfile():raise SystemExit('Not a regular file: '+member.name)
            target=out/arch/path;target.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as source:target.write_bytes(source.read())
            files[str(path)]=sha(target)
    version=out/arch/top/'VERSION'
    # nsembed.c check_version: the tree's VERSION file must name this release
    if not version.is_file() or version.read_text().strip()!='Wine Gecko '+VERSION:
        raise SystemExit('Unexpected VERSION in '+top)
    if not (out/arch/top/'xul.dll').is_file():raise SystemExit('No xul.dll in '+top)
    trees[arch]={'directory':arch+'/'+top,'archive':relative,'archive_sha256':digest,'files':files,
                 'bytes':sum((out/arch/p).stat().st_size for p in files)}
manifest={'schema_version':1,'version':VERSION,'source':'https://dl.winehq.org/wine/wine-gecko/'+VERSION+'/',
          'license':'MPL-2.0','trees':trees,'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({arch:{'files':len(t['files']),'bytes':t['bytes']} for arch,t in trees.items()}))
