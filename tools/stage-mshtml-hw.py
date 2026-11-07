#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Phase 9: Wine's MSHTML ("IE" for programs that embed it) and the DLLs the browser needs.

1. Modules, built as PE in the pinned host Wine tree, with their import closure from the same
   tree (as stage-wine-i386.py); modules the sealed prefix or another stager already stages are
   left out. Nothing is patched.
   - 64-bit: mshtml, jscript, msxml3, mshtml.tlb and iexplore; usp10, wsock32, wtsapi32 and
     netapi32, which Pale Moon 35 and Wine Gecko import and the prefix does not have.
   - 32-bit: the same, plus msimg32 and uxtheme (Wine Gecko x86 imports them).
   - W178: bcrypt for both (crypt32 and ncrypt import it, wintrust imports crypt32, and xul.dll of
     Wine Gecko and Pale Moon imports wintrust; W177 failed with "Library bcrypt.dll not found").
     The 64-bit one comes from tools/build-bcrypt-x64.py, since the host tree has none. And the
     modules xul.dll and mozglue.dll delay-load (psapi, winspool.drv, rasapi32, rasdlg, dbghelp):
     a missing one raises an exception at its first call. tools/check-web-closure.py checks the
     whole closure in the built runtime.
2. Their COM registration, as DllRegisterServer would write it, without running Wine: the
   WINE_REGISTRY scripts in each module's resources (read like dlls/atl/registrar.c, with %MODULE%
   in C:\\windows\\system32) and mshtml.inf (RegInstall from mshtml's register_server, with the
   CLSIDs of dlls/mshtml/mshtml_classes.idl). The sealed prefix has ieframe, shdocvw and urlmon
   registered for 64-bit programs only and mshtml/jscript for neither: a 32-bit program finds its
   classes under Classes\\Wow6432Node\\CLSID and Interface (system.reg: the other Classes keys are
   shared or linked), and HKLM\\Software under Software\\Wow6432Node.
   Type libraries (mshtml.tlb, the one in ieframe) are not registered: a program that marshals
   these interfaces across apartments, or a script host that reads the type library, gets
   TYPE_E_LIBNOTREGISTERED from oleaut32 (listed in the manifest).
Values the sealed system.reg already holds with the same data are left out; one with other data
is replaced (listed in the manifest), except where the INF line says FLG_ADDREG_NOCLOBBER.
Output: out/mshtml-hw/{x86_64-windows,i386-windows}/, system.reg.add and manifest.json;
tools/build-wine-hardware.py copies the modules and appends system.reg.add to system.reg.
"""
import hashlib,json,pathlib,re,struct,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';out=ROOT/'out/mshtml-hw'
CRYPTO_AND_DELAYED=('bcrypt.dll','psapi.dll','winspool.drv','rasapi32.dll','rasdlg.dll','dbghelp.dll')  # W178
TARGETS={'x86_64-windows':('mshtml.dll','jscript.dll','msxml3.dll','mshtml.tlb','iexplore.exe',
                           'usp10.dll','wsock32.dll','wtsapi32.dll','netapi32.dll')+CRYPTO_AND_DELAYED,
         'i386-windows':('mshtml.dll','jscript.dll','msxml3.dll','mshtml.tlb','iexplore.exe',
                         'usp10.dll','wsock32.dll','wtsapi32.dll','netapi32.dll','msimg32.dll','uxtheme.dll',
                         # W252: the i386 crypt32 in its builtin folder, so its Unix side (W180's static table)
                         # is found; the syswow64 copy alone had none and xul.dll failed (W251: webview32)
                         'crypt32.dll')+CRYPTO_AND_DELAYED}
# W252: modules staged although the sealed prefix has them: its syswow64 crypt32.dll is not in the builtin folder,
# so ntdll Unix gives it no Unix library
BUILTIN_FOLDER={('i386-windows','crypt32.dll')}
# modules whose WINE_REGISTRY scripts are applied, per view, in order: shdocvw and ieframe both
# register the WebBrowser class, and wineboot leaves it in ieframe (the sealed 64-bit view)
REGISTER={'x86_64-windows':('mshtml.dll','jscript.dll','msxml3.dll'),
          'i386-windows':('urlmon.dll','shdocvw.dll','ieframe.dll','mshtml.dll','jscript.dll','msxml3.dll')}
LABEL={'x86_64-windows':'x64','i386-windows':'i386'}
STAMP='1793390636';TIME='#time=1dd68a9cb52bf36'
wine_commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if wine_commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('MSHTML requires the pinned Wine revision')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
# W178: the 64-bit bcrypt.dll the host tree could not link (tools/build-bcrypt-x64.py)
bcrypt64=json.loads((ROOT/'out/bcrypt-x64/manifest.json').read_text())
if bcrypt64['builder_sha256']!=sha(ROOT/'tools/build-bcrypt-x64.py'):raise SystemExit('bcrypt differs from its builder')
if sha(ROOT/'out/bcrypt-x64'/bcrypt64['bcrypt']['path'])!=bcrypt64['bcrypt']['sha256']:raise SystemExit('bcrypt differs from its manifest')
def locate(name,arch):
    if (name,arch)==('bcrypt.dll','x86_64-windows'):return ROOT/'out/bcrypt-x64'/bcrypt64['bcrypt']['path']
    stem=name.rsplit('.',1)[0]
    for candidate in (BUILD/'dlls'/name/arch/name,BUILD/'dlls'/stem/arch/name,BUILD/'programs'/stem/arch/name):
        if candidate.is_file():return candidate
    return None
def pe(path):
    data=path.read_bytes();at=struct.unpack_from('<I',data,0x3c)[0]
    machine=struct.unpack_from('<H',data,at+4)[0]
    if machine not in (0x14c,0x8664):raise SystemExit('Not a PE for i386 or x86-64: '+str(path))
    count=struct.unpack_from('<H',data,at+6)[0];optional=at+24;size=struct.unpack_from('<H',data,at+20)[0]
    sections=[struct.unpack_from('<IIII',data,optional+size+40*i+8) for i in range(count)]
    def offset(rva):
        for vsize,address,raw_size,raw in sections:
            if address<=rva<address+max(vsize,raw_size):return raw+rva-address
        return None
    def directory(index):
        return struct.unpack_from('<II',data,optional+(96 if machine==0x14c else 112)+8*index)
    return data,offset,directory
def imports(path):
    """Import and delay-import names (directories 1 and 13)."""
    data,offset,directory=pe(path);names=set()
    for index,entry_size,name_field in ((1,20,12),(13,32,4)):
        rva=directory(index)[0];at=offset(rva) if rva else None
        while at is not None:
            entry=data[at:at+entry_size]
            if entry==bytes(entry_size):break
            name_at=offset(struct.unpack_from('<I',entry,name_field)[0])
            if name_at is not None:names.add(data[name_at:data.index(b'\0',name_at)].decode().lower())
            at+=entry_size
    return sorted(names)
def resources(path,wanted):
    """(name or id, bytes) of each resource of the named type (all names and languages)."""
    data,offset,directory=pe(path);rva=directory(2)[0]
    if not rva:return []
    base=offset(rva)
    def entries(at):
        named,ids=struct.unpack_from('<HH',data,at+12)
        return [struct.unpack_from('<II',data,at+16+8*i) for i in range(named+ids)]
    def name(value):
        if not value&0x80000000:return value
        at=base+(value&0x7fffffff);length=struct.unpack_from('<H',data,at)[0]
        return data[at+2:at+2+2*length].decode('utf-16-le')
    found=[]
    for type_name,type_at in entries(base):
        if name(type_name)!=wanted:continue
        for resource_name,name_at in entries(base+(type_at&0x7fffffff)):
            for _,leaf in entries(base+(name_at&0x7fffffff)):
                data_rva,length=struct.unpack_from('<II',data,base+leaf)
                found.append((name(resource_name),data[offset(data_rva):offset(data_rva)+length]))
    return found
def registry_scripts(path):
    """Text of each WINE_REGISTRY resource."""
    return [blob.decode('utf-8').rstrip('\0') for _,blob in resources(path,'WINE_REGISTRY')]
def msft_typelib(blob):
    """What RegisterTypeLib reads from an MSFT type library (dlls/oleaut32/typelib.c, typelib.h):
    library GUID, version, lcid, syskind, flags, name and doc string, and each type's kind, flags,
    GUID and name."""
    def i32(at):return struct.unpack_from('<i',blob,at)[0]
    if blob[:4]!=b'MSFT':raise SystemExit('Not an MSFT type library')
    varflags,count=i32(0x14),i32(0x20)
    segdir=0x54+4*count+(4 if varflags&0x100 else 0)   # HELPDLLFLAG adds one INT
    def segment(index):return i32(segdir+16*index)
    typeinfo_tab,guid_tab,name_tab,string_tab=segment(0),segment(5),segment(7),segment(8)
    def guid(offset):
        d1,d2,d3=struct.unpack_from('<IHH',blob,guid_tab+offset);tail=blob[guid_tab+offset+8:guid_tab+offset+16]
        return '{%08X-%04X-%04X-%s-%s}'%(d1,d2,d3,tail[:2].hex().upper(),tail[2:].hex().upper())
    def name(offset):   # MSFT_NameIntro (12 bytes), namelen & 0xff ANSI characters
        at=name_tab+offset;length=i32(at+8)&0xff
        return blob[at+12:at+12+length].decode('latin-1')
    def string(offset):   # INT16 length, then the characters
        if offset<0:return None
        at=string_tab+offset;length=struct.unpack_from('<h',blob,at)[0]
        return blob[at+2:at+2+length].decode('latin-1')
    version=i32(0x18)
    library={'guid':guid(i32(0x08)),'major':version&0xffff,'minor':(version>>16)&0xffff,
             'lcid':i32(0x10)&0xffffffff,   # lcid2: what GetLibAttr reports
             'syskind':varflags&0xf,'flags':i32(0x1c)&0xffff,
             'name':name(i32(0x38)),'doc':string(i32(0x24)),'types':[]}
    for index in range(count):
        at=typeinfo_tab+index*0x64
        library['types'].append({'kind':i32(at)&0xf,'flags':i32(at+0x30)&0xffff,'guid':guid(i32(at+0x2c)),'name':name(i32(at+0x34))})
    return library

# ---- registry model: {key path relative to HKLM: {value name or None: (kind, data)}} ----
class Registrar:
    """dlls/atl/registrar.c for registration: words, quoted '' strings, nested keys, val, s/d/b."""
    def __init__(self,text,replacements):
        def replace(match):
            word=match.group(1)
            if word=='':return '%'
            for key,value in replacements.items():
                if key.lower()==word.lower():return value
            raise SystemExit('No replacement for %'+word+'%')
        self.text=re.sub(r'%([^%]*)%',replace,text);self.at=0
    def word(self):
        t=self.text;i=self.at
        while i<len(t) and t[i].isspace():i+=1
        if i>=len(t):self.at=i;return ''
        if t[i] in '}=':word=t[i];i+=1
        elif t[i]=="'":
            parts=[];i+=1
            while True:
                end=t.index("'",i)
                if end+1<len(t) and t[end+1]=="'":parts.append(t[i:end+1]);i=end+2;continue
                parts.append(t[i:end]);i=end+1;break
            word=''.join(parts)
        else:
            j=i
            while j<len(t) and not t[j].isspace():j+=1
            word=t[i:j];i=j
        while i<len(t) and t[i].isspace():i+=1
        self.at=i;return word
    def peek(self):return self.text[self.at:self.at+2]
    def run(self,emit):
        roots={'HKCR':'HKCR','HKEY_CLASSES_ROOT':'HKCR','HKLM':'HKLM','HKEY_LOCAL_MACHINE':'HKLM',
               'HKCU':'HKCU','HKEY_CURRENT_USER':'HKCU'}
        word=self.word()
        while word:
            if word.upper() not in roots:raise SystemExit('Unsupported root key: '+word)
            if self.word()!='{':raise SystemExit('Expected {')
            self.keys([roots[word.upper()]],emit)
            word=self.word()
    def keys(self,path,emit):
        word=self.word()
        while word!='}':
            kind='key'
            if word.lower() in ('noremove','forceremove','val','delete'):
                kind={'val':'val','delete':'delete'}.get(word.lower(),'key');word=self.word()
            if kind=='delete':raise SystemExit('Delete in a registration script: '+word)
            if kind=='key':emit(path+[word],None,None)
            if self.peek()[:1]=='=':
                self.at+=1;typ=self.word();value=self.word()
                if typ=='s':data=('sz',value)
                elif typ=='d':data=('dword',int(value,10))
                elif typ=='b':data=('binary',bytes.fromhex(value))
                else:raise SystemExit('Unsupported value type: '+typ)
                if kind=='val':emit(path,word,data)
                else:emit(path+[word],'',data)
            elif kind=='val':raise SystemExit('val without a value: '+word)
            if kind=='key' and self.peek()[:1]=='{' and self.peek()[1:2].isspace():
                self.word();self.keys(path+[word],emit)
            word=self.word()

hkcu_skipped=set()
def view_path(path,arch):
    """HKCR/HKLM path list -> key relative to HKLM in the view of a program of that arch."""
    root,rest=path[0],path[1:]
    if root=='HKCR':
        if arch=='i386-windows' and rest and rest[0].lower() in ('clsid','interface'):
            return ['Software','Classes','Wow6432Node']+rest
        return ['Software','Classes']+rest
    if rest and rest[0].lower()=='software' and arch=='i386-windows':
        return ['Software','Wow6432Node']+rest[1:]
    return rest
def parse_reg(text):
    """Keys and values of a Wine .reg file (names unescaped only as far as comparison needs)."""
    keys={};current=None
    for line in text.splitlines():
        match=re.match(r'^\[(.*)\](?: \d+)?$',line)
        if match:current=keys.setdefault(match.group(1).lower(),{});continue
        if current is None:continue
        match=re.match(r'^(@|"(?:[^"\\]|\\.)*")=(.*)$',line)
        if match:current[match.group(1).lower()]=match.group(2)
    return keys
def escape(text):
    return ''.join('\\\\' if c=='\\' else '\\"' if c=='"' else c if 32<=ord(c)<127 else '\\x%04x'%ord(c) for c in text)
def reg_key(path):return '\\\\'.join(escape(part) for part in path)
def reg_name(name):return '@' if name in ('',None) else '"'+escape(name)+'"'
def reg_data(data):
    kind,value=data
    if kind=='sz':return '"'+escape(value)+'"'
    if kind=='expand':return 'str(2):"'+escape(value)+'"'
    if kind=='dword':return 'dword:%08x'%value
    if kind=='binary':return 'hex:'+','.join('%02x'%b for b in value)
    raise SystemExit('kind '+kind)

with tarfile.open(ROOT/'reports/increment15/prefix-package/prefix.tar.gz') as archive:
    present={'x86_64-windows':set(),'i386-windows':set()};sealed_reg=None
    for member in archive:
        if not member.isfile():continue
        name=pathlib.PurePosixPath(member.name)
        if '/system32/' in member.name:present['x86_64-windows'].add(name.name.lower())
        if '/syswow64/' in member.name:present['i386-windows'].add(name.name.lower())
        if name.name=='system.reg':
            if sealed_reg is not None:raise SystemExit('two system.reg in the prefix package')
            sealed_reg=archive.extractfile(member).read().decode('utf-8','replace')
if sealed_reg is None:raise SystemExit('no system.reg in the prefix package')
sealed=parse_reg(sealed_reg)
# W174/W175: out/wine-extras lists its modules as "<x86_64|i386>/<name>"
for key in json.loads((ROOT/'out/wine-extras/manifest.json').read_text())['modules']:
    arch,name=key.split('/')
    present[arch+'-windows'].add(name.lower())
for path in ('out/wine-pe64/manifest.json','out/wine-gui/manifest.json','out/wine-programs/manifest.json'):
    present['x86_64-windows']|={n.lower() for n in json.loads((ROOT/path).read_text())['modules']}
i386=json.loads((ROOT/'out/wine-i386/manifest.json').read_text())
present['x86_64-windows']|={n.lower() for n in i386['modules_x64']}
present['i386-windows']|={n.lower() for n in i386['modules']}
present['i386-windows']|={n.lower() for n in json.loads((ROOT/'out/dmsynth-i386/manifest.json').read_text())['modules']}

modules={};edges={};unresolved=set()
for arch,targets in TARGETS.items():
    (out/arch).mkdir(parents=True,exist_ok=True)
    found={}
    for name in targets:
        path=locate(name,arch)
        if not path:raise SystemExit('Not built: %s (%s)'%(name,arch))
        found[name]=path
    closure={};pending=list(found.values())
    while pending:
        module=pending.pop()
        for name in imports(module):
            edges.setdefault(LABEL[arch]+':'+module.name,[]).append(name)
            if name in present[arch] or name in closure or name in found or re.match(r'^(api|ext)-ms-',name):continue
            path=locate(name,arch)
            if not path:unresolved.add(LABEL[arch]+':'+name);continue
            closure[name]=path;pending.append(path)
    staged={}
    for name,path in sorted({**closure,**found}.items()):
        if name in present[arch] and name in found and (arch,name) not in BUILTIN_FOLDER:continue   # already staged elsewhere: register only
        target=out/arch/name;target.write_bytes(path.read_bytes())
        staged[name]={'path':arch+'/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT))}
    modules[arch]=staged

# ---- registration ----
writes={}   # (key tuple, name) -> data ; key-only entries use name None
order=[]
def emit(key,name,data,noclobber=False):
    key=tuple(key)
    if (key,None) not in writes:writes[(key,None)]=None;order.append((key,None))
    if name is None:return
    item=(key,name)
    # W182: compared as parse_reg stores them (escaped key, quoted value name, lower case); before,
    # a value of the sealed prefix never matched
    if noclobber and (item in writes or reg_name(name).lower() in sealed.get(reg_key(key).lower(),{})):return
    if item not in writes:order.append(item)
    writes[item]=data
scripts_applied={}
for arch,names in REGISTER.items():
    for name in names:
        path=locate(name,arch)
        scripts=registry_scripts(path)
        if not scripts:raise SystemExit('No WINE_REGISTRY resource in '+str(path))
        scripts_applied[LABEL[arch]+':'+name]=len(scripts)
        replacements={'MODULE':'C:\\windows\\system32\\'+name,'SystemRoot':'C:\\windows'}
        for text in scripts:
            # HKCU (urlmon's Internet Settings): user.reg, not split by view; the sealed prefix
            # has it from the 64-bit registration. Left out and listed.
            Registrar(text,replacements).run(lambda key,value_name,data,arch=arch,name=name:
                hkcu_skipped.add(LABEL[arch]+':'+name) if key[0]=='HKCU' else emit(view_path(key,arch),value_name,data))
# mshtml.inf, [RegisterDll] AddReg sections, with the CLSID strings of register_server
classes={}
for idl in ('include/mshtml.idl','dlls/mshtml/mshtml_classes.idl'):
    classes.update((m.group(2).lower(),'{'+m.group(1).upper()+'}') for m in re.finditer(
        r'uuid\(([0-9a-fA-F-]{36})\)\s*\]\s*coclass\s+(\w+)',(SOURCE/idl).read_text()))
# the rest are DEFINE_GUIDs in mshtml_private.h and main.c
for m in re.finditer(r'DEFINE_GUID\(CLSID_(\w+),\s*0x(\w+),\s*0x(\w+),\s*0x(\w+),((?:\s*0x\w+,?){8})\);',
                     (SOURCE/'dlls/mshtml/mshtml_private.h').read_text()+(SOURCE/'dlls/mshtml/main.c').read_text()):
    tail=[int(b,16) for b in re.findall(r'0x(\w+)',m.group(5))]
    classes[m.group(1).lower()]='{%08X-%04X-%04X-%02X%02X-%s}'%(int(m.group(2),16),int(m.group(3),16),int(m.group(4),16),
                                                             tail[0],tail[1],''.join('%02X'%b for b in tail[2:]))
main=(SOURCE/'dlls/mshtml/main.c').read_text()
strings={}
for clsid in re.findall(r'^\s+INF_SET_CLSID\((\w+)\);',main,re.M):
    if clsid.lower() not in classes:raise SystemExit('No uuid for CLSID_'+clsid+' in mshtml_classes.idl')
    strings['clsid_'+clsid.lower()]=classes[clsid.lower()]
inf=(SOURCE/'dlls/mshtml/mshtml.inf').read_text().splitlines()
def section(name):
    start=inf.index('['+name+']')+1;lines=[]
    for line in inf[start:]:
        if line.startswith('['):break
        if line.strip() and not line.lstrip().startswith(';'):lines.append(line)
    return lines
addreg=[s.strip() for line in section('RegisterDll') if line.startswith('AddReg=') for s in line[7:].split(',')]
def inf_fields(line):
    fields=[];field='';quoted=False;i=0
    while i<len(line):
        c=line[i]
        if c=='"':
            if quoted and line[i+1:i+2]=='"':field+='"';i+=2;continue
            quoted=not quoted
        elif c==',' and not quoted:fields.append(field.strip());field=''
        else:field+=c
        i+=1
    fields.append(field.strip());return fields
def inf_text(text,program_files):
    def replace(match):
        word=match.group(1)
        if word=='':return '%'
        if word=='16422':return program_files
        if word.lower() in strings:return strings[word.lower()]
        raise SystemExit('No INF string %'+word+'%')
    return re.sub(r'%([^%]*)%',replace,text)
inf_lines=0
for name in addreg:
    for line in section(name):
        fields=inf_fields(line)+['']*5
        root,subkey,value_name,flags=fields[0],fields[1],fields[2],int(fields[3] or '0',0)
        data_fields=[f for f in fields[4:] if f!='']
        for arch,program_files in (('x86_64-windows','C:\\Program Files'),('i386-windows','C:\\Program Files (x86)')):
            key=view_path([root]+inf_text(subkey,program_files).split('\\'),arch)
            if arch=='i386-windows' and key==view_path([root]+inf_text(subkey,program_files).split('\\'),'x86_64-windows'):
                continue   # a shared key: written once, from the 64-bit view
            if flags&0x10:emit(key,None,None);continue                     # FLG_ADDREG_KEYONLY
            if flags&0x10001==0x10001:data=('dword',int(data_fields[0],0))
            elif flags&1:data=('binary',bytes(int(b,16) for b in data_fields))  # FLG_ADDREG_BINVALUETYPE
            elif flags&0x20000:data=('expand',inf_text(data_fields[0],program_files))
            else:data=('sz',inf_text(data_fields[0] if data_fields else '',program_files))
            emit(key,inf_text(value_name,program_files),data,noclobber=bool(flags&2))   # FLG_ADDREG_NOCLOBBER
        inf_lines+=1
# W182: type libraries, as RegisterTypeLib writes them (dlls/oleaut32/typelib.c). W180: mshtml's
# LoadRegTypeLib(LIBID_MSHTML 4.0) failed (TYPE_E_LIBNOTREGISTERED, the sealed prefix registers no
# type library at all), its dispatch data stayed empty and the next call faulted. ieframe
# (LIBID_SHDocVw), jscript (stdole 2.0) and msxml3 (LIBID_MSXML2) load theirs the same way.
# The sealed prefix registers some (stdole 2.0 for 64-bit, SHDocVw's interfaces) but not MSHTML's or MSXML2's.
# TypeLib\{libid}\<major.minor> is shared by the two views, with a win64 path (system32) and a
# win32 one (syswow64, where a 32-bit registration finds the module); every dispinterface and
# oleautomation interface also gets Interface\{iid} in both views (Wine registers the opposite
# view too). A value the sealed prefix already has (oleaut32's own proxies, such as IDispatch's)
# is kept.
TYPELIBS=('stdole2.tlb','mshtml.tlb','ieframe.dll','msxml3.dll')
TKIND_INTERFACE,TKIND_DISPATCH=3,4
TYPEFLAG_FDUAL,TYPEFLAG_FOLEAUTOMATION=0x40,0x100
typelibs_registered={}
for arch,folder in (('x86_64-windows','system32'),('i386-windows','syswow64')):
    for module in TYPELIBS:
        found=[(resource,blob) for resource,blob in resources(locate(module,arch),'TYPELIB') if resource==1]
        if len(found)!=1:raise SystemExit('No TYPELIB resource 1 in %s (%s)'%(module,arch))
        library=msft_typelib(found[0][1])
        if library['syskind']!=(3 if arch=='x86_64-windows' else 1):raise SystemExit('Unexpected syskind in '+module)
        full_path='C:\\windows\\'+folder+'\\'+module
        key=['HKCR','TypeLib',library['guid'],'%x.%x'%(library['major'],library['minor'])]
        emit(view_path(key,arch),'',('sz',library['doc'] or library['name']))
        emit(view_path(key+['%x'%library['lcid'],'win64' if library['syskind']==3 else 'win32'],arch),'',('sz',full_path))
        # FLAGS and no HELPDIR, as the sealed prefix's own registrations (stdole 2.0, Accessibility) have them
        emit(view_path(key+['FLAGS'],arch),'',('sz','%u'%library['flags']))
        interfaces=0
        for info in library['types']:
            if not ((info['kind']==TKIND_INTERFACE and info['flags']&TYPEFLAG_FOLEAUTOMATION) or info['kind']==TKIND_DISPATCH):continue
            proxy=('{00020424-0000-0000-C000-000000000046}' if info['kind']==TKIND_INTERFACE or info['flags']&TYPEFLAG_FDUAL
                   else '{00020420-0000-0000-C000-000000000046}')
            for view in ('x86_64-windows','i386-windows'):
                interface=['HKCR','Interface',info['guid']]
                emit(view_path(interface,view),'',('sz',info['name']),noclobber=True)
                emit(view_path(interface+['ProxyStubClsid'],view),'',('sz',proxy),noclobber=True)
                emit(view_path(interface+['ProxyStubClsid32'],view),'',('sz',proxy),noclobber=True)
                emit(view_path(interface+['TypeLib'],view),'',('sz',library['guid']),noclobber=True)
                emit(view_path(interface+['TypeLib'],view),'Version',('sz','%x.%x'%(library['major'],library['minor'])),noclobber=True)
            interfaces+=1
        typelibs_registered[LABEL[arch]+':'+module]={'libid':library['guid'],'version':'%x.%x'%(library['major'],library['minor']),
                                                     'name':library['name'],'path':full_path,'interfaces':interfaces}

# ---- write only what the sealed system.reg does not already hold ----
blocks={};replaced=[];kept=0
for key,name in order:
    path=reg_key(key);sealed_values=sealed.get(path.lower())
    blocks.setdefault(path,[])
    if name is None:continue
    rendered=reg_data(writes[(key,name)]);current=(sealed_values or {}).get(reg_name(name).lower())
    if current==rendered:kept+=1;continue
    if current is not None:replaced.append({'key':path,'value':reg_name(name),'sealed':current,'new':rendered})
    blocks[path].append(reg_name(name)+'='+rendered)
text=''
for path,lines in blocks.items():
    if not lines and path.lower() in sealed:continue
    text+='\n['+path+'] '+STAMP+'\n'+TIME+'\n'+''.join(line+'\n' for line in lines)
(out/'system.reg.add').write_text(text)
manifest={'schema_version':1,'wine_commit':wine_commit,'modules':modules,'import_edges':edges,
          'unresolved_imports':sorted(unresolved),
          'excluded':'modules in the sealed prefix, out/wine-pe64, wine-gui, wine-programs, wine-extras, wine-i386 and dmsynth-i386; api-set names',
          'registry':{'path':'system.reg.add','sha256':sha(out/'system.reg.add'),'keys':text.count('\n['),
                      'scripts':scripts_applied,'hkcu_left_out':sorted(hkcu_skipped),'inf_lines':inf_lines,'values_already_sealed':kept,'values_replaced':replaced},
          'typelibs':typelibs_registered,
          'source_patches':False,'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'x86_64':sorted(modules['x86_64-windows']),'i386':sorted(modules['i386-windows']),
                  'unresolved':sorted(unresolved),'registry_keys':manifest['registry']['keys'],'values_replaced':len(replaced)}))
