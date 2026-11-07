#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W178 (phase 9): check that every import of the web stack resolves in a built runtime, transitively.

W177 failed because the import closure was only checked one level deep: xul.dll -> wintrust.dll was
present, but wintrust -> crypt32 -> bcrypt was not. This follows every import (not delay imports,
which load on first call and are listed apart) through the modules the loader would find, as the
console's Wine loads them: the importing program's own folder first, then system32 (syswow64 for
i386) and the builtin folder wine/lib/wine/<arch>-windows. api-ms-*/ext-ms-* names are api sets.

Usage: check-web-closure.py [--staged <x86_64 dir> <i386 dir>] <runtime dir> [<extra program folder>...]
  <runtime dir>: build/wine-hardware-wNNN/runtime (holds wine-prefix and wine/lib/wine)
  --staged: stager output folders (out/mshtml-hw/x86_64-windows and i386-windows) counted as part of
            system32/syswow64, to check a fix before the next build
  extra folders: other program folders to check, such as an extracted Pale Moon (the user's copy)
Checked by default: Wine Gecko (both), mshtml/ieframe/jscript/iexplore (both), webview64/32.exe.
Exit status 1 if anything does not resolve. Run it with python3 -I: it only reads PE headers.
"""
import json,pathlib,re,struct,sys
def imports(path):
    """(machine, import names, delay-import names) of a PE image, or None if it is not one."""
    data=path.read_bytes()
    if data[:2]!=b'MZ':return None
    at=struct.unpack_from('<I',data,0x3c)[0]
    if data[at:at+4]!=b'PE\0\0':return None
    machine=struct.unpack_from('<H',data,at+4)[0]
    count=struct.unpack_from('<H',data,at+6)[0];optional=at+24;size=struct.unpack_from('<H',data,at+20)[0]
    directories=optional+(96 if struct.unpack_from('<H',data,optional)[0]==0x10b else 112)
    sections=[struct.unpack_from('<IIII',data,optional+size+40*i+8) for i in range(count)]
    def offset(rva):
        for vsize,address,raw_size,raw in sections:
            if address<=rva<address+max(vsize,raw_size):return raw+rva-address
        return None
    result=[]
    for index,entry_size,name_field in ((1,20,12),(13,32,4)):
        names=set();rva=struct.unpack_from('<I',data,directories+8*index)[0]
        at=offset(rva) if rva else None
        while at is not None:
            entry=data[at:at+entry_size]
            if entry==bytes(entry_size):break
            name_at=offset(struct.unpack_from('<I',entry,name_field)[0])
            if name_at is not None:names.add(data[name_at:data.index(b'\0',name_at)].decode('ascii','replace').lower())
            at+=entry_size
        result.append(names)
    return machine,result[0],result[1]
args=sys.argv[1:];staged={}
if args[:1]==['--staged']:
    if len(args)<3:raise SystemExit(__doc__)
    staged={0x8664:pathlib.Path(args[1]),0x14c:pathlib.Path(args[2])};args=args[3:]
if not args:raise SystemExit(__doc__)
runtime=pathlib.Path(args[0]);prefix=runtime/'wine-prefix/drive_c'
VIEWS={0x8664:('x86_64',prefix/'windows/system32',runtime/'wine/lib/wine/x86_64-windows'),
       0x14c:('i386',prefix/'windows/syswow64',runtime/'wine/lib/wine/i386-windows')}
def listing(folder):return {p.name.lower():p for p in folder.iterdir() if p.is_file()} if folder.is_dir() else {}
system={machine:{**listing(builtin),**listing(windows),**(listing(staged[machine]) if staged else {})}
        for machine,(_,windows,builtin) in VIEWS.items()}
roots=[]   # (label, program folder, modules to start from)
for arch,windows in (('x86_64','system32'),('x86','syswow64')):
    for gecko in sorted((prefix/'windows'/windows/'gecko').glob('*/wine-gecko-*')):
        roots.append(('gecko '+arch,gecko,sorted(p for p in gecko.rglob('*') if p.suffix.lower() in ('.dll','.exe'))))
for windows in ('system32','syswow64'):
    folder=prefix/'windows'/windows
    roots.append(('mshtml '+windows,folder,[folder/n for n in ('mshtml.dll','ieframe.dll','jscript.dll','shdocvw.dll','urlmon.dll','iexplore.exe')
                                           if (folder/n).is_file()]))
roots.append(('webview',prefix/'orbis',[prefix/'orbis'/n for n in ('webview64.exe','webview32.exe') if (prefix/'orbis'/n).is_file()]))
for extra in args[1:]:
    folder=pathlib.Path(extra)
    roots.append(('program '+folder.name,folder,sorted(p for p in folder.rglob('*') if p.suffix.lower() in ('.dll','.exe'))))
report={'runtime':str(runtime),'staged':{hex(m):str(d) for m,d in staged.items()},'roots':{},'missing':0}
for label,folder,modules in roots:
    own={p.name.lower():p for p in folder.rglob('*') if p.is_file()} if label.startswith(('gecko','program')) else {}
    missing={};delay_missing={};seen=set();pending=[]
    for module in modules:
        info=imports(module)
        if info and info[0] in VIEWS:pending.append((module,info))
    if not pending:report['roots'][label]={'modules':0,'note':'nothing found'};continue
    while pending:
        module,(machine,names,delay)=pending.pop()
        if (str(module),machine) in seen:continue
        seen.add((str(module),machine))
        for name,target in [(n,missing) for n in names]+[(n,delay_missing) for n in delay]:
            if re.match(r'^(api|ext)-ms-',name):continue
            found=own.get(name) or system[machine].get(name)
            if found is None:target.setdefault(name,set()).add(module.name);continue
            if target is missing:
                info=imports(found)
                if info and info[0]==machine:pending.append((found,info))
    report['roots'][label]={'modules':len(seen),'missing':{n:sorted(v) for n,v in sorted(missing.items())},
                            'delay_missing':{n:sorted(v) for n,v in sorted(delay_missing.items())}}
    report['missing']+=len(missing)
print(json.dumps(report,indent=2))
sys.exit(1 if report['missing'] else 0)
