#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build actual PE dependencies for external prefix preparation, not PS4 code."""
import argparse,hashlib,json,pathlib,re,struct,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILD=ROOT/'.deps/wine/runtime/build'
parser=argparse.ArgumentParser();parser.add_argument('--jobs',type=int,default=12);args=parser.parse_args()
out=ROOT/'reports/increment15/host-build';out.mkdir(parents=True,exist_ok=True)
makefile=(BUILD/'Makefile').read_text()
targets={}
for match in re.finditer(r'^((?:dlls|programs)/[^/ :]+/(i386|x86_64)-windows/([^/ :]+\.(?:dll|exe|sys|drv))):',makefile,re.M):
    targets[(match[2],match[3].lower())]=match[1]
def imports(path):
    data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    if data[:2]!=b'MZ' or data[pe:pe+4]!=b'PE\0\0':raise ValueError('Not PE: '+str(path))
    sections=struct.unpack_from('<H',data,pe+6)[0];optional=pe+24
    size=struct.unpack_from('<H',data,pe+20)[0];magic=struct.unpack_from('<H',data,optional)[0]
    directory=optional+(112 if magic==0x20b else 96)
    imagebase=struct.unpack_from('<Q' if magic==0x20b else '<I',data,optional+(24 if magic==0x20b else 28))[0]
    def offset(rva):
        for index in range(sections):
            header=optional+size+40*index
            virtual,base,raw,pointer=struct.unpack_from('<IIII',data,header+8)
            if base<=rva<base+raw:return pointer+rva-base
        raise ValueError('Unmapped PE RVA: '+str(path))
    def string(rva):
        begin=offset(rva);end=data.index(b'\0',begin,begin+4096)
        return data[begin:end].decode('ascii').lower()
    found=set()
    for index,width,name_at in ((1,20,12),(13,32,4)):
        rva,length=struct.unpack_from('<II',data,directory+index*8)
        if not rva:continue
        start=offset(rva)
        for position in range(start,min(start+length,len(data)),width):
            entry=data[position:position+width]
            if not any(entry):break
            name=struct.unpack_from('<I',entry,name_at)[0]
            if index==13 and not (struct.unpack_from('<I',entry)[0]&1):name-=imagebase
            found.add(string(name))
    return sorted(found)
resources=['mscms.dll','hidclass.sys','mouhid.sys','winebth.sys','winebus.sys','winehid.sys','wineusb.sys','winexinput.sys']
seed=['wineboot.exe','services.exe','rundll32.exe','explorer.exe','rpcss.exe','winedevice.exe','svchost.exe','mountmgr.sys','kernel32.dll','kernelbase.dll','ntdll.dll',*resources]
missing_seeds=[name for name in seed if ('x86_64',name) not in targets]
if missing_seeds:raise SystemExit('Missing required PE64 targets: '+repr(missing_seeds))
pending={(arch,name) for arch in ('i386','x86_64') for name in seed if (arch,name) in targets}
pending|={('x86_64',name) for name in ('wow64.dll','wow64cpu.dll','wow64win.dll')}
done={};commands=[];unknown=[];start=time.monotonic()
while pending:
    current=sorted(pending-set(done));pending=set()
    if not current:break
    missing=[key for key in current if key not in targets]
    if missing:raise SystemExit('No configured PE target: '+str(missing))
    command=['make','-j'+str(args.jobs),*[targets[key] for key in current]];commands.append(command)
    with (out/f'make-{len(commands):02d}.log').open('w') as log:
        subprocess.run(command,cwd=BUILD,stdout=log,stderr=subprocess.STDOUT,check=True)
    for arch,name in current:
        path=BUILD/targets[(arch,name)];dependencies=imports(path)
        directory=path.parent.parent.relative_to(BUILD)
        definition=(ROOT/'.deps/wine/source'/directory/'Makefile.in').read_text().replace('\\\n',' ')
        delayed=re.search(r'^DELAYIMPORTS\s*=\s*(.*)$',definition,re.M)
        source_delayed=sorted({module if '.' in module else module+'.dll' for module in delayed.group(1).split()}) if delayed else []
        if any('$' in module for module in source_delayed):raise SystemExit('Unexpanded delayed import: '+str(directory))
        dependencies=sorted(set(dependencies)|set(source_delayed))
        done[(arch,name)]={'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'imports':dependencies,'source_delayed_imports':source_delayed}
        for dependency in dependencies:
            key=(arch,dependency)
            if key in targets and key not in done:pending.add(key)
            elif key not in targets and not dependency.startswith(('api-ms-','ext-ms-')):
                unknown.append({'arch':arch,'module':name,'import':dependency})
    print('PE modules built:',len(done),'next:',len(pending),flush=True)
report={'scope':'Native Linux Wine PE closure for prefix initialization; not PS4 validation',
        'status':'passed' if not unknown else 'blocked','modules':{arch+'/'+name:value for (arch,name),value in sorted(done.items())},
        'unknown_imports':unknown,'commands':commands,'duration_seconds':round(time.monotonic()-start,3),
        'wine_commit':subprocess.check_output(['git','-C',str(ROOT/'.deps/wine/source'),'rev-parse','HEAD'],text=True).strip(),
        'configure_args':subprocess.check_output([str(BUILD/'config.status'),'--config'],cwd=BUILD,text=True).strip()}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
if unknown:raise SystemExit('Unresolved PE imports: '+str(unknown))
