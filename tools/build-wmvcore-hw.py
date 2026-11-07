#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W280: wmvcore.dll (i386 and x86_64) that fails with an error when winegstreamer is missing.

GTA San Andreas (PE32, a guest of explorer's WoW64 world) calls WMCreateSyncReader at start.
wmvcore delay-loads winegstreamer.dll for every reader (WMCreateSyncReader/Priv and, through
async_reader_create, WMCreateReader/Priv), and the PS4 runtime has no GStreamer and no
winegstreamer.dll: the delay-load hook raises EXCEPTION_WINE_STUB (0x80000100) and the game ends
(W278, "DelayLoadFailureHook failed to delay load winegstreamer.dll"). Here each of those calls
first loads winegstreamer.dll by name; when it does not load, the call prints an ERR ("PWWMV ...")
and returns HRESULT_FROM_WIN32 of the loader's error with a NULL reader, as Windows does when
the Windows Media runtime cannot create a reader. Nothing is reported as created. When the
DLL loads, the call is the original delay-loaded one.
The overlays come from the pinned sources (checked by sha256); writer.o, version.res and the
link come from the host tree with the recipes of its Makefile (make -n dlls/wmvcore/all).
Output: out/wmvcore-hw/{i386-windows,x86_64-windows}/wmvcore.dll and manifest.json.
"""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
work=ROOT/'build/wmvcore-hw';out=ROOT/'out/wmvcore-hw'
ARCHES={'i386-windows':'i686-w64-mingw32','x86_64-windows':'x86_64-w64-mingw32'}
for path in (work,*[work/a for a in ARCHES],*[out/a for a in ARCHES]):path.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def run(command):
    with (work/'build.log').open('a') as log:
        log.write('$ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=BUILD,check=True,stdout=log,stderr=subprocess.STDOUT)
(work/'build.log').write_text('')
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('wmvcore requires the pinned Wine revision')
PINNED={'dlls/wmvcore/wmvcore_main.c':'0e20a7a81b2301e59e1785f45f2f6cb629f56bf6202425dde389cfb9795b9d1a',
        'dlls/wmvcore/async_reader.c':'3509fc92f4b2d34fc0d46067105fd6a7caafe31cf17cc822efebca323d606677',
        'dlls/wmvcore/wmvcore.spec':'d19871a9ee1d9229aa6c1a4e202aeb123b74d643cb058d0b0d71bc2c9aec6fb0'}
for name,digest in PINNED.items():
    if sha(SOURCE/name)!=digest:raise SystemExit('unexpected source: '+name)

def overlay(name,pairs):
    text=(SOURCE/'dlls/wmvcore'/name).read_text()
    for old,new,count in pairs:
        if text.count(old)!=count:raise SystemExit(name+': context found %d times, expected %d: %s'%(text.count(old),count,old[:60]))
        text=text.replace(old,new)
    path=work/name;path.write_text(text);return path

CALL='winegstreamer_create_wm_sync_reader(NULL, (void **)reader);'
main_c=overlay('wmvcore_main.c',[
    ('''WINE_DEFAULT_DEBUG_CHANNEL(wmvcore);
''','''WINE_DEFAULT_DEBUG_CHANNEL(wmvcore);

/* W280: the PS4 runtime has no winegstreamer.dll; its delay-load would raise EXCEPTION_WINE_STUB. */
HRESULT pwwmv_create_wm_sync_reader(const char *caller, IUnknown *outer, void **out)
{
    static HMODULE gstreamer;
    DWORD error;

    if (!gstreamer && !(gstreamer = LoadLibraryW(L"winegstreamer.dll")))
    {
        error = GetLastError();
        ERR("PWWMV %s: winegstreamer.dll did not load (error %lu); no reader is created.\\n", caller, error);
        if (out) *out = NULL;
        return HRESULT_FROM_WIN32(error ? error : ERROR_MOD_NOT_FOUND);
    }
    return winegstreamer_create_wm_sync_reader(outer, out);
}
''',1),
    ('    return '+CALL+'\n}\n\nHRESULT WINAPI WMCreateSyncReaderPriv',
     '    return pwwmv_create_wm_sync_reader("WMCreateSyncReader", NULL, (void **)reader);\n}\n\nHRESULT WINAPI WMCreateSyncReaderPriv',1),
    ('    return '+CALL+'\n}\n\nHRESULT WINAPI WMCheckURLExtension',
     '    return pwwmv_create_wm_sync_reader("WMCreateSyncReaderPriv", NULL, (void **)reader);\n}\n\nHRESULT WINAPI WMCheckURLExtension',1)])
async_c=overlay('async_reader.c',[
    ('''WINE_DEFAULT_DEBUG_CHANNEL(wmvcore);
''','''WINE_DEFAULT_DEBUG_CHANNEL(wmvcore);

HRESULT pwwmv_create_wm_sync_reader(const char *caller, IUnknown *outer, void **out);
''',1),
    ('''    if (FAILED(hr = winegstreamer_create_wm_sync_reader((IUnknown *)&object->IWMReader_iface,''',
     '''    if (FAILED(hr = pwwmv_create_wm_sync_reader("WMCreateReader", (IUnknown *)&object->IWMReader_iface,''',1)])
for path in (main_c,async_c):
    if 'winegstreamer_create_wm_sync_reader(' in path.read_text().replace('return winegstreamer_create_wm_sync_reader(outer, out);',''):
        raise SystemExit(path.name+' still calls winegstreamer directly')

src='../../source'
common=['-Idlls/wmvcore','-I'+src+'/dlls/wmvcore','-Iinclude','-I'+src+'/include','-I'+src+'/include/msvcrt','-D_UCRT',
        '-D__WINESRC__','-D__WINE_PE_BUILD','-Wall','-fno-strict-aliasing','-Wempty-body','-Wignored-qualifiers',
        '-Winit-self','-Wno-packed-not-aligned','-Wshift-overflow=2','-Wtype-limits','-Wunused-but-set-parameter',
        '-Wvla','-Wwrite-strings','-Wpointer-arith','-Wlogical-op','-ffunction-sections']
arch_flags={'i386-windows':['-fno-omit-frame-pointer','-mpreferred-stack-boundary=2','-mlong-double-64','-msse2'],
            'x86_64-windows':['-Wformat-overflow','-Wnonnull','-mlong-double-64','-mcx16','-mcmodel=small']}
tail=['-gdwarf-4','-Wdeclaration-after-statement','-Wstrict-prototypes','-Wabsolute-value','-g','-O2']
version=BUILD/'dlls/wmvcore/version.res'
modules={}
for arch,triple in ARCHES.items():
    objects=[]
    for path in (async_c,main_c):
        obj=work/arch/path.name.replace('.c','.o');objects.append(obj)
        run([triple+'-gcc','-c','-o',obj,path,*common,*arch_flags[arch],*tail])
    writer=BUILD/'dlls/wmvcore'/arch/'writer.o'
    libs=[BUILD/p.format(arch) for p in ('dlls/kernel32/{}/libkernel32.a','dlls/combase/{}/libcombase.a',
          'dlls/winegstreamer/{}/libwinegstreamer.delay.a','libs/winecrt0/{}/libwinecrt0.a',
          'libs/compiler-rt/{}/libcompiler-rt.a','dlls/ucrtbase/{}/libucrtbase.a',
          'dlls/kernel32/{}/libkernel32.a','dlls/ntdll/{}/libntdll.a')]
    for path in (writer,version,*libs):
        if not path.is_file():raise SystemExit('missing input: '+str(path))
    dll=out/arch/'wmvcore.dll'
    run(['tools/winegcc/winegcc','-o',dll,'--wine-objdir','.','--cc-cmd='+triple+'-gcc','-b',triple,
         '-Wl,--wine-builtin','-shared',src+'/dlls/wmvcore/wmvcore.spec',*objects,writer,version,*libs,
         '-Wl,--disable-stdcall-fixup','-Wl,--build-id'])
    modules[arch]={'path':arch+'/wmvcore.dll','sha256':sha(dll),'writer_o_sha256':sha(writer),
                   'host_original_sha256':sha(BUILD/'dlls/wmvcore'/arch/'wmvcore.dll')}
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(pathlib.Path(__file__)),
          'sources':PINNED,'overlays':{p.name:sha(p) for p in (main_c,async_c)},
          'source_change':'WMCreateSyncReader/Priv and WMCreateReader/Priv load winegstreamer.dll first; '
                          'if it does not load: ERR "PWWMV" and HRESULT_FROM_WIN32(error), NULL reader',
          'modules':modules}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(modules,indent=2))
