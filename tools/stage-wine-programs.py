#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Stage Wine's own programs (notepad, regedit, cmd, taskmgr, winemine, conhost, winecfg, control) and joy.cpl for hardware.

W043. The programs are built as PE64 in the pinned host Wine tree
(make programs/<name>/x86_64-windows/<name>.exe). Their import closure is taken from
the same tree; modules already staged by out/wine-pe64 or out/wine-gui and api-set names
are left out, as in stage-wine-gui.py. Nothing is patched.
"""
import hashlib,json,pathlib,re,struct,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';out=ROOT/'out/wine-programs'
(out/'x86_64-windows').mkdir(parents=True,exist_ok=True)
PROGRAMS=('notepad','regedit','cmd','taskmgr','winemine','conhost',  # W058: winefile replaced by WFM
          'winecfg',  # W172: per-program Windows version and DLL overrides (phase 7)
          'ipconfig','ping',  # W174 (phase 8); ping's ICMP goes to nsiproxy.sys and fails with an error
          'control')  # W178 (phase 7): opens joy.cpl, the Game Controllers panel
wine_commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if wine_commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Programs require the pinned Wine revision')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def locate(name):
    stem=name[:-4]
    for candidate in (BUILD/'dlls'/stem/'x86_64-windows'/name,BUILD/'programs'/stem/'x86_64-windows'/name):
        if candidate.is_file():return candidate
    return None
def imports(path):
    """Names in the import (directory 1) and delay-import (directory 13) tables of a PE32+,
    plus the IMPORTS/DELAYIMPORTS of the module's Makefile.in (see stage-wine-gui.py)."""
    data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    sections_count=struct.unpack_from('<H',data,pe+6)[0];optional=pe+24
    optional_size=struct.unpack_from('<H',data,pe+20)[0]
    if struct.unpack_from('<H',data,optional)[0]!=0x20b:raise SystemExit('Not PE32+: '+str(path))
    sections=[struct.unpack_from('<IIII',data,optional+optional_size+40*i+8) for i in range(sections_count)]
    def offset(rva):
        for size,address,raw_size,raw in sections:
            if address<=rva<address+max(size,raw_size):return raw+rva-address
        return None
    def name_at(rva):
        at=offset(rva);return data[at:data.index(b'\0',at)].decode().lower() if at is not None else None
    names=set()
    for directory,entry_size,name_field in ((1,20,12),(13,32,4)):
        rva=struct.unpack_from('<I',data,optional+112+8*directory)[0]
        at=offset(rva) if rva else None
        while at is not None:
            entry=data[at:at+entry_size]
            if entry==bytes(entry_size):break
            name=name_at(struct.unpack_from('<I',entry,name_field)[0])
            if name:names.add(name)
            at+=entry_size
    stem=path.name.rsplit('.',1)[0]
    for makefile in (SOURCE/'dlls'/stem/'Makefile.in',SOURCE/'programs'/stem/'Makefile.in'):
        if makefile.is_file():
            for line in makefile.read_text().splitlines():
                match=re.match(r'^(?:DELAY)?IMPORTS\s*=\s*(.*)$',line)
                if match:
                    for library in match.group(1).split():
                        if locate(library+'.dll'):names.add(library+'.dll')
    return sorted(names)
already={name.lower() for name in json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())['modules']}
already|={name.lower() for name in json.loads((ROOT/'out/wine-gui/manifest.json').read_text())['modules']}
targets={}
for program in PROGRAMS:
    found=locate(program+'.exe')
    if not found:raise SystemExit('Not built: programs/%s (make programs/%s/x86_64-windows/%s.exe)'%(program,program,program))
    targets[program+'.exe']=found
# W178 (phase 7): the Game Controllers panel, a control panel module built in dlls/joy.cpl
targets['joy.cpl']=BUILD/'dlls/joy.cpl/x86_64-windows/joy.cpl'
if not targets['joy.cpl'].is_file():raise SystemExit('Not built: dlls/joy.cpl/x86_64-windows/joy.cpl')
closure={};missing=set();edges={}
pending=list(targets.values())
while pending:
    module=pending.pop()
    for name in imports(module):
        edges.setdefault(module.name,[]).append(name)
        if name in already or name in closure or name in targets or re.match(r'^(api|ext)-ms-',name):continue
        # W178: xinput comes patched from tools/build-xinput-hw.py (the console pad), not from here
        if name.startswith('xinput'):continue
        found=locate(name)
        if not found:missing.add(name);continue
        closure[name]=found;pending.append(found)
staged={}
for name,path in sorted({**closure,**targets}.items()):
    target=out/'x86_64-windows'/name;target.write_bytes(path.read_bytes())
    staged[name]={'path':'x86_64-windows/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT))}
manifest={'schema_version':1,'wine_commit':wine_commit,'programs':sorted(targets),'modules':staged,
          'import_edges':edges,'unresolved_imports':sorted(missing),
          'excluded':'modules of out/wine-pe64, out/wine-gui and api-set names','source_patches':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':len(staged),'programs':sorted(targets),'unresolved':sorted(missing)}))
