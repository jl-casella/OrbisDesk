#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wine Mono 11.3.0, the .NET runtime Wine's mscoree loads (2026-11-16: PES 2014's settings.exe, an IL-only
.NET program, stopped with "mscoree.dll not found, IL-only binary cannot be loaded", run-0121 and run-0163).

The upstream x86 tarball (https://dl.winehq.org/wine/wine-mono/11.3.0/, pinned by SHA-256 in
product-assets.lock.json, the same digest as the GitHub release asset), unmodified. Despite its name it holds both
runtimes, bin/libmono-2.0-x86.dll and bin/libmono-2.0-x86_64.dll, and the class libraries. 11.3.0 is the version
the pinned Wine asks for (dlls/mscoree/mscoree_private.h WINE_MONO_VERSION).

mscoree looks first in C:\\windows\\mono\\mono-2.0 (dlls/mscoree/metahost.c get_mono_path_local), where the .msi
would install it; tools/build-wine-hardware.py copies the tree there. The console's file system has no symbolic
links, so the 156 links of lib/mono (4.5/*.dll into gac/) become copies of their targets (about 57 MB more).
support/ is left out: the .msi helpers (installinf, createlinks, the fake .NET Framework DLLs and registry) that
Wine's appwiz.cpl runs at prefix creation, which this sealed prefix does not do.
Development tools are left out too (2026-11-20, the clean CI install measured 275 MB of Mono): the reference
assemblies of lib/mono/<version>-api (compile-time metadata only, about 98 MB), MSBuild, xbuild and the C#/VB
compilers (csc, vbc, mcs, ilasm, Roslyn's Microsoft.CodeAnalysis*, about 30 MB). A program that compiles code at run
time (CodeDom's CSharpCodeProvider) finds no compiler; running .NET programs needs none of them.
Run with python3 -I: the archive is untrusted input and is only read here.
Output: out/wine-mono/mono-2.0/..., out/wine-mono/licenses/COPYING and manifest.json.
"""
import hashlib,json,pathlib,posixpath,shutil,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='11.3.0'
TOP='wine-mono-'+VERSION
LEFT_OUT=('support/','lib/mono/msbuild/','lib/mono/xbuild/','lib/mono/xbuild-frameworks/','lib/mono/4.5/MSBuild/',
          'lib/mono/4.5/Microsoft.CodeAnalysis','lib/mono/4.5/VBCSCompiler.','lib/mono/4.5/WineMono.XBuild.',
          'lib/mono/4.5/csc.','lib/mono/4.5/vbc.','lib/mono/4.5/mcs.','lib/mono/4.5/ilasm.','lib/mono/4.5/xbuild.')
def left_out_path(relative):
    """support/, the development tools above and every lib/mono/<version>-api/ reference assembly folder."""
    parts=relative.split('/')
    return relative.startswith(LEFT_OUT) or (len(parts)>3 and parts[:2]==['lib','mono'] and parts[2].endswith('-api'))
out=ROOT/'out/wine-mono'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
downloads=json.loads((ROOT/'product-assets.lock.json').read_text())['downloads']
archive_spec,copying_spec=downloads['wine-mono-x86'],downloads['wine-mono-copying']
archive_path,copying_path=ROOT/archive_spec['path'],ROOT/copying_spec['path']
if sha(archive_path)!=archive_spec['sha256']:raise SystemExit('Wine Mono archive differs from product-assets.lock.json')
if sha(copying_path)!=copying_spec['sha256']:raise SystemExit("Wine Mono's COPYING differs from product-assets.lock.json")
if out.exists():shutil.rmtree(out)
files={};links={};left_out=0;members={};dropped=[]
# one pass in archive order (an xz stream cannot seek back), then the links as copies of what they point to
with tarfile.open(archive_path,'r:xz') as archive:
    for member in archive:
        path=pathlib.PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or path.parts[0]!=TOP:raise SystemExit('Unexpected archive entry: '+member.name)
        members[member.name.rstrip('/')]=member
        relative=member.name[len(TOP)+1:]
        if not relative or member.isdir() or member.issym():continue
        if left_out_path(relative):
            left_out+=1
            if not relative.startswith('support/'):dropped.append(relative)
            continue
        if not member.isfile():raise SystemExit('Not a regular file or a symbolic link: '+member.name)
        target=out/'mono-2.0'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        with archive.extractfile(member) as data:target.write_bytes(data.read())
        files[relative]=sha(target)
def resolve(member):
    for _ in range(16):
        if not member.issym():return member
        target=posixpath.normpath(posixpath.join(posixpath.dirname(member.name),member.linkname))
        if not target.startswith(TOP+'/') or target not in members:raise SystemExit('Link leaves the tree: '+member.name)
        member=members[target]
    raise SystemExit('Link loop: '+member.name)
for name,member in sorted(members.items()):
    relative=name[len(TOP)+1:]
    if not member.issym():continue
    if left_out_path(relative):
        left_out+=1
        if not relative.startswith('support/'):dropped.append(relative)
        continue
    source=resolve(member);source_relative=source.name[len(TOP)+1:]
    if left_out_path(source_relative):left_out+=1;dropped.append(relative);continue  # a link to a left-out file
    if not source.isfile() or source_relative not in files:raise SystemExit('Link to no staged file: '+name)
    target=out/'mono-2.0'/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(out/'mono-2.0'/source_relative,target)
    links[relative]=source_relative;files[relative]=files[source_relative]
files=dict(sorted(files.items()))
for runtime in ('bin/libmono-2.0-x86.dll','bin/libmono-2.0-x86_64.dll','lib/mono/4.5/mscorlib.dll'):
    if runtime not in files:raise SystemExit('No %s in %s'%(runtime,TOP))
(out/'licenses').mkdir(parents=True)
shutil.copyfile(copying_path,out/'licenses/COPYING')
manifest={'schema_version':1,'version':VERSION,'source':'https://dl.winehq.org/wine/wine-mono/'+VERSION+'/',
          'source_code':'https://dl.winehq.org/wine/wine-mono/%s/wine-mono-%s-src.tar.xz'%(VERSION,VERSION),
          'license':'MIT, LGPL, MS-PL, zlib and others (COPYING)','archive':archive_spec['path'],
          'archive_sha256':archive_spec['sha256'],'files':files,'links_copied':links,'left_out':list(LEFT_OUT),
          'left_out_files':left_out,
          # earlier builds shipped these (all but support/): build-wine-hardware.py deletes them on installed consoles
          'dropped_paths':sorted(dropped),'licenses':{'COPYING':sha(out/'licenses/COPYING')},
          'bytes':sum((out/'mono-2.0'/p).stat().st_size for p in files),'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'files':len(files),'links_copied':len(links),'left_out_files':left_out,'mb':round(manifest['bytes']/2**20,1)}))
