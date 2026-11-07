#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W225: DirectShow for 32-bit programs, and an MPEG-1 decoder for it.

GTA Vice City plays movies/Logo.mpg and GTAtitles.mpg (MPEG-1 system streams: MPEG-1 video
640x480 at 25 fps, MPEG-1 layer II audio at 48 kHz) through CLSID_FilterGraph, which was not
registered: the sealed syswow64 has no quartz (W221 run-0002.log, "class {e436ebb3-...} not
registered"). docs/investigacion-gta-vc-base-0x400000.md.

1. Modules, unpatched PE32 from the pinned host Wine tree, with their import closure from the
   same tree (as stage-wine-i386.py); modules already in the sealed syswow64 or staged by another
   stager are left out: quartz, devenum, msdmo, avicap32 (its v4l Unix side is absent; DllMain
   ignores that, as on a host without a camera), msvfw32.
2. pwmpeg1.ax (native/pwmpeg1): the MPEG-1 system stream filter. In the pinned Wine the MPEG-1
   splitter and decoders exist only in winegstreamer, which needs GStreamer; the PS4 has none.
   pwmpeg1 decodes with pl_mpeg (MIT, .deps/downloads/pl_mpeg-c871f2be) into RGB32 and PCM.
   Built here like build-dmsynth-i386.py builds dmsynth (i686-w64-mingw32-gcc, winegcc, the
   host tree's import libraries and libstrmbase.a), as a native DLL.
3. Their registration for the 32-bit view, as DllRegisterServer would write it, without
   running Wine:
   - the WINE_REGISTRY scripts of quartz and devenum (classes, and quartz.rgs: the Media Type
     check-bytes and extensions); HKCR\\CLSID and Interface go to Classes\\Wow6432Node, Media
     Type to both Classes\\Media Type and Classes\\Wow6432Node\\Media Type (the sealed prefix has
     the latter key, so a 32-bit program may be redirected there);
   - devenum's categories (IFilterMapper2::CreateCategory, dlls/devenum/devenum_main.c) and
     quartz's filters (IFilterMapper2::RegisterFilter, dlls/quartz/main.c) under
     CLSID\\{category}\\Instance, FilterData serialized as dlls/quartz/filtermapper.c
     FM2_WriteFilterData does. quartz's registrations of winegstreamer filters (AVI and MPEG-1
     splitters, WAVE parser, MPEG audio and video decoders) are left out: nothing here creates
     those classes, and listing them would offer filters that are not there;
   - pwmpeg1's class and filter, input MEDIATYPE_Stream/MPEG1System, outputs RGB32 and PCM.
   The audio renderers are registered by devenum at run time (DirectSound devices), as on Wine.
Output: out/dshow-i386/i386-windows/, system.reg.add and manifest.json; tools/build-wine-hardware.py
copies the Wine modules to wine/lib/wine/i386-windows and syswow64, pwmpeg1.ax to syswow64, and
appends system.reg.add to system.reg.
"""
import hashlib,json,pathlib,re,struct,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';out=ROOT/'out/dshow-i386';work=ROOT/'build/dshow-i386'
PLMPEG=ROOT/'.deps/downloads/pl_mpeg-c871f2be';PLMPEG_SHA='3a8cb30c83c2a1147719c30fe0c8b93da2987aa43140077c575b39aaa75fc2c9'
ARCH='i386-windows'
TARGETS=('quartz.dll','devenum.dll','msdmo.dll','avicap32.dll','msvfw32.dll')
REGISTER=('quartz.dll','devenum.dll')
STAMP='1793390636';TIME='#time=1dd68a9cb52bf36'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('DirectShow requires the pinned Wine revision')
if sha(PLMPEG/'pl_mpeg.h')!=PLMPEG_SHA:raise SystemExit('pl_mpeg.h differs from the pinned copy')
for path in (work,out/ARCH):path.mkdir(parents=True,exist_ok=True)
for old in (out/ARCH).iterdir():old.unlink()
(work/'build.log').write_text('')
def run(command):
    with (work/'build.log').open('a') as log:
        log.write('$ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=BUILD,check=True,stdout=log,stderr=subprocess.STDOUT)

# ---- PE helpers (as tools/stage-mshtml-hw.py) ----
def locate(name):
    stem=name.rsplit('.',1)[0]
    for candidate in (BUILD/'dlls'/name/ARCH/name,BUILD/'dlls'/stem/ARCH/name):
        if candidate.is_file():return candidate
    return None
def pe(path):
    data=path.read_bytes();at=struct.unpack_from('<I',data,0x3c)[0]
    if struct.unpack_from('<H',data,at+4)[0]!=0x14c:raise SystemExit('Not a PE32 for i386: '+str(path))
    count=struct.unpack_from('<H',data,at+6)[0];optional=at+24;size=struct.unpack_from('<H',data,at+20)[0]
    sections=[struct.unpack_from('<IIII',data,optional+size+40*i+8) for i in range(count)]
    def offset(rva):
        for vsize,address,raw_size,raw in sections:
            if address<=rva<address+max(vsize,raw_size):return raw+rva-address
        return None
    def directory(index):return struct.unpack_from('<II',data,optional+96+8*index)
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
def registry_scripts(path):
    """Text of each WINE_REGISTRY resource."""
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
        if name(type_name)!='WINE_REGISTRY':continue
        for _,name_at in entries(base+(type_at&0x7fffffff)):
            for _,leaf in entries(base+(name_at&0x7fffffff)):
                data_rva,length=struct.unpack_from('<II',data,base+leaf)
                found.append(data[offset(data_rva):offset(data_rva)+length].decode('utf-8').rstrip('\0'))
    return found
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
        roots={'HKCR':'HKCR','HKEY_CLASSES_ROOT':'HKCR','HKLM':'HKLM','HKEY_LOCAL_MACHINE':'HKLM'}
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
def views(path):
    """HKCR/HKLM path list -> the keys relative to HKLM a 32-bit program reads."""
    root,rest=path[0],path[1:]
    if root=='HKCR':
        if rest and rest[0].lower() in ('clsid','interface'):return [['Software','Classes','Wow6432Node']+rest]
        if rest and rest[0].lower()=='media type':return [['Software','Classes']+rest,['Software','Classes','Wow6432Node']+rest]
        return [['Software','Classes']+rest]
    if rest and rest[0].lower()=='software':return [['Software','Wow6432Node']+rest[1:]]
    return [rest]
def escape(text):
    return ''.join('\\\\' if c=='\\' else '\\"' if c=='"' else c if 32<=ord(c)<127 else '\\x%04x'%ord(c) for c in text)
def reg_key(path):return '\\\\'.join(escape(part) for part in path)
def reg_name(name):return '@' if name in ('',None) else '"'+escape(name)+'"'
def reg_data(data):
    kind,value=data
    if kind=='sz':return '"'+escape(value)+'"'
    if kind=='dword':return 'dword:%08x'%value
    if kind=='binary':return 'hex:'+','.join('%02x'%b for b in value)
    raise SystemExit('kind '+kind)

# ---- what the 32-bit view already has ----
present=set();sealed_keys=set()
with tarfile.open(ROOT/'reports/increment15/prefix-package/prefix.tar.gz') as archive:
    for member in archive:
        if not member.isfile():continue
        if '/syswow64/' in member.name:present.add(pathlib.PurePosixPath(member.name).name.lower())
        if pathlib.PurePosixPath(member.name).name=='system.reg':
            sealed=archive.extractfile(member).read().decode('utf-8','replace')
            sealed_keys={m.group(1).lower() for m in re.finditer(r'^\[(.*)\](?: \d+)?$',sealed,re.M)}
for key in json.loads((ROOT/'out/wine-extras/manifest.json').read_text())['modules']:
    if key.startswith('i386/'):present.add(key.split('/',1)[1].lower())
present|={n.lower() for n in json.loads((ROOT/'out/wine-i386/manifest.json').read_text())['modules']}
present|={n.lower() for n in json.loads((ROOT/'out/dmsynth-i386/manifest.json').read_text())['modules']}
present|={n.lower() for n in json.loads((ROOT/'out/mshtml-hw/manifest.json').read_text())['modules'][ARCH]}

# ---- 1. Wine modules and their closure ----
found={}
for name in TARGETS:
    path=locate(name)
    if not path:raise SystemExit('Not built: %s (make dlls/%s/%s/%s)'%(name,name[:-4],ARCH,name))
    if name in present:raise SystemExit(name+' is already staged elsewhere')
    found[name]=path
closure={};pending=list(found.values());edges={};unresolved=set()
while pending:
    module=pending.pop()
    for name in imports(module):
        edges.setdefault(module.name,[]).append(name)
        if name in present or name in closure or name in found or re.match(r'^(api|ext)-ms-',name):continue
        path=locate(name)
        if not path:unresolved.add(name);continue
        closure[name]=path;pending.append(path)
if unresolved:raise SystemExit('unresolved imports: '+', '.join(sorted(unresolved)))
modules={}
for name,path in sorted({**closure,**found}.items()):
    target=out/ARCH/name;target.write_bytes(path.read_bytes())
    modules[name]={'path':ARCH+'/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT)),'builtin':True}

# ---- 2. pwmpeg1.ax ----
src='../../source'
wine_inc=['-Iinclude','-I'+src+'/include','-I'+src+'/include/msvcrt','-D_UCRT','-D__WINE_PE_BUILD','-D__WINESRC__']
i386_flags=['-fno-strict-aliasing','-ffunction-sections','-fno-omit-frame-pointer','-msse2','-gdwarf-4','-g','-O2',
            '-mpreferred-stack-boundary=2','-mlong-double-64']
filter_source=ROOT/'native/pwmpeg1/pwmpeg1.c';spec=ROOT/'native/pwmpeg1/pwmpeg1.spec'
obj=work/'pwmpeg1.o'
run(['i686-w64-mingw32-gcc','-c','-o',obj,filter_source,'-I'+str(PLMPEG),*wine_inc,'-Wall',*i386_flags])
libs=[BUILD/p for p in ('libs/strmbase/i386-windows/libstrmbase.a','libs/strmiids/i386-windows/libstrmiids.a',
      'libs/uuid/i386-windows/libuuid.a','libs/dxguid/i386-windows/libdxguid.a','dlls/ole32/i386-windows/libole32.a',
      'dlls/user32/i386-windows/libuser32.a','libs/winecrt0/i386-windows/libwinecrt0.a',
      'libs/compiler-rt/i386-windows/libcompiler-rt.a','dlls/ucrtbase/i386-windows/libucrtbase.a',
      'dlls/kernel32/i386-windows/libkernel32.a','dlls/ntdll/i386-windows/libntdll.a')]
for lib in libs:
    if not lib.is_file():raise SystemExit('missing library: '+str(lib))
ax=out/ARCH/'pwmpeg1.ax'
run(['tools/winegcc/winegcc','-o',ax,'--wine-objdir','.','--cc-cmd=i686-w64-mingw32-gcc','-b','i686-w64-mingw32',
     '-shared',spec,obj,*libs,'-Wl,--disable-stdcall-fixup','-Wl,--build-id'])
for name in imports(ax):
    if name not in present and name not in modules:raise SystemExit('pwmpeg1.ax imports '+name+', which is not staged')
modules['pwmpeg1.ax']={'path':ARCH+'/pwmpeg1.ax','sha256':sha(ax),'source':str(filter_source.relative_to(ROOT)),
                       'source_sha256':sha(filter_source),'builtin':False,'imports':imports(ax)}

# ---- 3. registration ----
writes={};order=[]
def emit(key,name,data):
    key=tuple(key)
    if (key,None) not in writes:writes[(key,None)]=None;order.append((key,None))
    if name is None:return
    if (key,name) not in writes:order.append((key,name))
    writes[(key,name)]=data
def emit_views(path,name,data):
    for key in views(path):emit(key,name,data)
scripts={}
for name in REGISTER:
    texts=registry_scripts(found[name])
    if not texts:raise SystemExit('No WINE_REGISTRY resource in '+name)
    scripts[name]=len(texts)
    for text in texts:
        Registrar(text,{'MODULE':'C:\\windows\\system32\\'+name,'SystemRoot':'C:\\windows'}).run(emit_views)
# GUIDs as include/uuids.h defines them
uuids={}
for m in re.finditer(r'OUR_GUID_ENTRY\((\w+),\s*0x(\w+),\s*0x(\w+),\s*0x(\w+),((?:\s*0x\w+,?){8})\)',(SOURCE/'include/uuids.h').read_text()):
    tail=[int(b,16) for b in re.findall(r'0x(\w+)',m.group(5))]
    uuids[m.group(1)]=struct.pack('<IHH',int(m.group(2),16),int(m.group(3),16),int(m.group(4),16))+bytes(tail)
def guid_text(raw):
    d1,d2,d3=struct.unpack_from('<IHH',raw);return '{%08X-%04X-%04X-%s-%s}'%(d1,d2,d3,raw[8:10].hex().upper(),raw[10:].hex().upper())
GUID_NULL=bytes(16)
PWMPEG1=struct.pack('<IHH',0xd1abd1fb,0x1295,0x47e2)+bytes([0xa8,0xfc,0x65,0x86,0x8f,0x9c,0x0c,0x90])
if b'0xd1abd1fb, 0x1295, 0x47e2, {0xa8, 0xfc, 0x65, 0x86, 0x8f, 0x9c, 0x0c, 0x90}' not in filter_source.read_bytes():
    raise SystemExit('pwmpeg1.c CLSID differs from the stager')
MERIT_PREFERRED,MERIT_NORMAL,MERIT_UNLIKELY,MERIT_DO_NOT_USE=0x800000,0x600000,0x400000,0x200000
REG_PINFLAG_B_ZERO,REG_PINFLAG_B_RENDERER,REG_PINFLAG_B_OUTPUT=1,2,8
def filter_data(merit,pins):
    """dlls/quartz/filtermapper.c FM2_WriteFilterData: REG_RF, then per pin REG_RFP and REG_TYPEs,
    then the GUID store, offsets counted from the start of the data (no pin categories or mediums)."""
    size=16+sum(24+16*len(types) for _,types in pins)
    store=bytearray()
    def find(raw):
        at=bytes(store).find(raw)   # filtermapper's find_data: first match at any byte offset
        if at<0:at=len(store);store.extend(raw)
        return at+size
    main=bytearray(struct.pack('<IIII',2,merit,len(pins),0))
    for i,(flags,types) in enumerate(pins):
        main+=struct.pack('<4sIIIII',bytes([0x30+i])+b'pi3',flags,0,len(types),0,0)
        for j,(major,minor) in enumerate(types):
            main+=struct.pack('<4sIII',bytes([0x30+j])+b'ty3',0,find(major),find(minor))
    if len(main)!=size:raise SystemExit('FilterData layout')
    return bytes(main+store)
def instance(category,clsid,name,merit,pins):
    key=['Software','Classes','Wow6432Node','CLSID',guid_text(uuids[category]),'Instance',guid_text(clsid)]
    emit(key,'FriendlyName',('sz',name));emit(key,'CLSID',('sz',guid_text(clsid)))
    emit(key,'FilterData',('binary',filter_data(merit,pins)))
# devenum's categories (dlls/devenum/devenum_main.c DllRegisterServer)
CATEGORIES=(('CLSID_AudioCompressorCategory',MERIT_DO_NOT_USE,'Audio Compressors'),
            ('CLSID_AudioInputDeviceCategory',MERIT_DO_NOT_USE,'Audio Capture Sources'),
            ('CLSID_AudioRendererCategory',MERIT_NORMAL,'Audio Renderers'),
            ('CLSID_DeviceControlCategory',MERIT_DO_NOT_USE,'Device Control Filters'),
            ('CLSID_LegacyAmFilterCategory',MERIT_NORMAL,'DirectShow Filters'),
            ('CLSID_MidiRendererCategory',MERIT_NORMAL,'Midi Renderers'),
            ('CLSID_TransmitCategory',MERIT_DO_NOT_USE,'External Renderers'),
            ('CLSID_VideoInputDeviceCategory',MERIT_DO_NOT_USE,'Video Capture Sources'),
            ('CLSID_VideoCompressorCategory',MERIT_DO_NOT_USE,'Video Compressors'))
devenum_source=(SOURCE/'dlls/devenum/devenum_main.c').read_text()
for category,merit,name in CATEGORIES:
    if 'CreateCategory(pMapper, &%s, %s, L"%s")'%(category,{MERIT_DO_NOT_USE:'MERIT_DO_NOT_USE',MERIT_NORMAL:'MERIT_NORMAL'}[merit],name) not in devenum_source:
        raise SystemExit('devenum_main.c differs for '+category)
    key=['Software','Classes','Wow6432Node','CLSID',guid_text(uuids['CLSID_ActiveMovieCategories']),'Instance',guid_text(uuids[category])]
    emit(key,'FriendlyName',('sz',name));emit(key,'CLSID',('sz',guid_text(uuids[category])));emit(key,'Merit',('dword',merit))
# quartz's own filters (dlls/quartz/main.c DllRegisterServer), all in the legacy category
V,A,S=uuids['MEDIATYPE_Video'],uuids['MEDIATYPE_Audio'],uuids['MEDIATYPE_Stream']
QUARTZ=(('CLSID_VideoRenderer','Video Renderer',MERIT_PREFERRED,[(REG_PINFLAG_B_RENDERER,[(V,GUID_NULL)])]),
        ('CLSID_VideoRendererDefault','Video Renderer',MERIT_PREFERRED+1,[(REG_PINFLAG_B_RENDERER,[(V,GUID_NULL)])]),
        ('CLSID_VideoMixingRenderer9','Video Mixing Renderer 9',MERIT_DO_NOT_USE,[(REG_PINFLAG_B_RENDERER,[(V,GUID_NULL)])]),
        ('CLSID_AVIDec','AVI Decompressor',MERIT_NORMAL-16,[(0,[(V,GUID_NULL)]),(REG_PINFLAG_B_OUTPUT,[(V,GUID_NULL)])]),
        ('CLSID_AsyncReader','File Source (Async.)',MERIT_UNLIKELY,[(REG_PINFLAG_B_OUTPUT,[(S,GUID_NULL)])]),
        ('CLSID_ACMWrapper','ACM Wrapper',MERIT_NORMAL-16,[(0,[(A,GUID_NULL)]),(REG_PINFLAG_B_OUTPUT,[(A,GUID_NULL)])]))
quartz_source=(SOURCE/'dlls/quartz/main.c').read_text()
for clsid,name,merit,pins in QUARTZ:
    if 'RegisterFilter(mapper, &%s, L"%s"'%(clsid,name) not in quartz_source:raise SystemExit('quartz main.c differs for '+clsid)
    instance('CLSID_LegacyAmFilterCategory',uuids[clsid],name,merit,pins)
# pwmpeg1: its class and its filter
key=['Software','Classes','Wow6432Node','CLSID',guid_text(PWMPEG1)]
emit(key,'',('sz','PW MPEG-1 Decoder'))
emit(key+['InprocServer32'],'',('sz','C:\\windows\\system32\\pwmpeg1.ax'))
emit(key+['InprocServer32'],'ThreadingModel',('sz','Both'))
instance('CLSID_LegacyAmFilterCategory',PWMPEG1,'PW MPEG-1 Decoder',MERIT_NORMAL,
         [(0,[(S,uuids['MEDIASUBTYPE_MPEG1System'])]),
          (REG_PINFLAG_B_OUTPUT|REG_PINFLAG_B_ZERO,[(V,uuids['MEDIASUBTYPE_RGB32'])]),
          (REG_PINFLAG_B_OUTPUT|REG_PINFLAG_B_ZERO,[(A,uuids['MEDIASUBTYPE_PCM'])])])
text='';count=0
for key,name in order:
    if name is not None:continue
    lines=[reg_name(n)+'='+reg_data(writes[(k,n)]) for k,n in order if k==key and n is not None]
    path=reg_key(key)
    if not lines and path.lower() in sealed_keys:continue
    text+='\n['+path+'] '+STAMP+'\n'+TIME+'\n'+''.join(line+'\n' for line in lines);count+=1
(out/'system.reg.add').write_text(text)
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(__file__),'modules':modules,
          'import_edges':edges,'registration_scripts':scripts,
          'registry':{'path':'system.reg.add','sha256':sha(out/'system.reg.add'),'keys':count},
          'pl_mpeg':{'path':str(PLMPEG.relative_to(ROOT)),'commit':'c871f2be022ece7ef4f64230b4fb8e1fb9eb6023',
                     'sha256':PLMPEG_SHA,'license':'MIT'},
          'not_registered':['CLSID_AviSplitter','CLSID_MPEG1Splitter','CLSID_WAVEParser','CLSID_CMpegAudioCodec',
                            'CLSID_CMpegVideoCodec'],
          'source_patches':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':sorted(modules),'registry_keys':count}))
