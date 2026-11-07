#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the 64-bit GUI fixture and stage the PE64 closure of the GUI targets.

The closure is every module the targets import, directly or through other modules,
taken from the pinned host Wine build. Modules already staged by out/wine-pe64 and
api-set names (resolved by apisetschema) are left out. Nothing is patched.
"""
import hashlib,json,pathlib,re,struct,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';out=ROOT/'out/wine-gui';(out/'x86_64-windows').mkdir(parents=True,exist_ok=True)
wine_commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if wine_commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('GUI and fonts require the pinned Wine revision')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
fixture=ROOT/'out/gui-window64.exe'
subprocess.run(['x86_64-w64-mingw32-gcc','-O2','-mwindows','-Wall','-Wextra','-Werror','-Wl,--no-insert-timestamp',
                '-o',str(fixture),str(ROOT/'fixtures/win32/gui_window.c'),'-lgdi32','-luser32'],check=True)
text_fixture=ROOT/'out/gui-text64.exe'
subprocess.run(['x86_64-w64-mingw32-gcc','-O2','-mwindows','-Wall','-Wextra','-Werror','-Wl,--no-insert-timestamp',
                '-o',str(text_fixture),str(ROOT/'fixtures/win32/gui_text.c'),'-lgdi32','-luser32'],check=True)
def locate(name):
    stem=name[:-4]
    for candidate in (BUILD/'dlls'/stem/'x86_64-windows'/name,BUILD/'programs'/stem/'x86_64-windows'/name):
        if candidate.is_file():return candidate
    return None
def imports(path):
    """Names in the import (directory 1) and delay-import (directory 13) tables of a PE32+."""
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
    # Wine's mingw-built modules resolve DELAYIMPORTS at run time (ResolveDelayLoadedAPI)
    # without a delay-import directory, so their Makefile.in is the source of truth.
    stem=path.name.rsplit('.',1)[0]
    for makefile in (SOURCE/'dlls'/stem/'Makefile.in',SOURCE/'programs'/stem/'Makefile.in'):
        if makefile.is_file() and path.parent.parent.parent.name in ('dlls','programs'):
            for line in makefile.read_text().splitlines():
                match=re.match(r'^(?:DELAY)?IMPORTS\s*=\s*(.*)$',line)
                if match:
                    for library in match.group(1).split():
                        if locate(library+'.dll'):names.add(library+'.dll')
    return sorted(names)
already={name.lower() for name in json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())['modules']}
targets={'gui-window64.exe':fixture,'gui-text64.exe':text_fixture,'explorer.exe':locate('explorer.exe')}
closure={};missing=set();edges={}
pending=list(targets.values())
while pending:
    module=pending.pop()
    for name in imports(module):
        edges.setdefault(module.name,[]).append(name)
        if name in already or name in closure or re.match(r'^(api|ext)-ms-',name):continue
        found=locate(name)
        if not found:missing.add(name);continue
        closure[name]=found;pending.append(found)
staged={}
for name,path in sorted({**closure,'explorer.exe':targets['explorer.exe']}.items()):
    target=out/'x86_64-windows'/name;target.write_bytes(path.read_bytes())
    staged[name]={'path':'x86_64-windows/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT))}
manifest={'schema_version':1,'wine_commit':wine_commit,'targets':{name:{'path':str(path.relative_to(ROOT)),'sha256':sha(path)} for name,path in targets.items()},
          'modules':staged,'import_edges':edges,'unresolved_imports':sorted(missing),
          'excluded':'modules of out/wine-pe64 and api-set names','source_patches':False}
fonts=out/'fonts';fonts.mkdir(exist_ok=True)
manifest['fonts']={}
for name in ('tahoma.ttf','tahomabd.ttf','marlett.ttf'):
    pinned=subprocess.check_output(['git','-C',str(SOURCE),'show',wine_commit+':fonts/'+name])
    if (SOURCE/'fonts'/name).read_bytes()!=pinned:raise SystemExit('Font differs from pinned Wine source: '+name)
    target=fonts/name;target.write_bytes((SOURCE/'fonts'/name).read_bytes())
    manifest['fonts'][name]={'path':'fonts/'+name,'sha256':sha(target),'source':str((SOURCE/'fonts'/name).relative_to(ROOT))}
for name,path in [('WINE-LICENSE.txt',SOURCE/'LICENSE'),('COPYING.LIB',SOURCE/'COPYING.LIB'),
                  ('tahoma.sfd',SOURCE/'fonts/tahoma.sfd'),('tahomabd.sfd',SOURCE/'fonts/tahomabd.sfd'),
                  ('marlett.sfd',SOURCE/'fonts/marlett.sfd')]:
    target=fonts/name;target.write_bytes(path.read_bytes())
    manifest['fonts'][name]={'path':'fonts/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':len(staged),'unresolved':sorted(missing)}))
