#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W138: Wine's DirectMusic software synthesizer (dmsynth) for 32-bit programs.

SuperMarioKart.exe (Blitz3D) plays its MIDI music through DirectMusic; dmime sends the notes
to dmsynth, which renders them with the FluidSynth copy Wine bundles (libs/fluidsynth,
LGPL-2.1) and plays them through dsound. The pinned host Wine tree was configured without
a C++ cross compiler for i386, so configure disabled libs/fluidsynth and dlls/dmsynth (and
Wine's libc++). FluidSynth has one C++ file, which uses no C++ runtime: it is compiled here
with clang++ for i686-w64-mingw32 without exceptions, RTTI or C++ headers, and dmsynth is
linked without the C++ libraries. The C sources, the widl registration resource and the
link use the recipes of Wine's own Makefile (taken from the dmime rules of the same tree).
Output: out/dmsynth-i386/i386-windows/dmsynth.dll and manifest.json.
"""
import hashlib,json,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP=['-ffile-prefix-map=%s=.'%ROOT,'-ffile-prefix-map=%s=vk-h0'%(pathlib.Path.home()/'vk-h0')]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
work=ROOT/'build/dmsynth-i386';out=ROOT/'out/dmsynth-i386'
for path in (work,out/'i386-windows'):path.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def run(command):
    with (work/'build.log').open('a') as log:
        log.write('$ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=BUILD,check=True,stdout=log,stderr=subprocess.STDOUT)
(work/'build.log').write_text('')
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('dmsynth requires the pinned Wine revision')
src='../../source'
wine_inc=['-Iinclude','-I'+src+'/include','-I'+src+'/include/msvcrt','-D_UCRT','-D__WINE_PE_BUILD']
i386_flags=['-fno-strict-aliasing','-ffunction-sections','-fno-omit-frame-pointer','-msse2','-gdwarf-4','-g','-O2',*PREFIX_MAP]

# FluidSynth (libs/fluidsynth/Makefile.in: its SOURCES, EXTRADEFS and EXTRAINCL)
makefile=(SOURCE/'libs/fluidsynth/Makefile.in').read_text()
sources=re.findall(r'^\s+(\S+\.(?:c|cpp))\s*\\?$',makefile,re.M)
if len(sources)<20 or sum(s.endswith('.cpp') for s in sources)!=1:raise SystemExit('unexpected fluidsynth sources')
fs=src+'/libs/fluidsynth'
fs_inc=['-I'+fs]+['-I'+fs+'/src'+sub for sub in ('','/bindings','/drivers','/midi','/rvoice','/sfloader','/synth','/utils')]+['-I'+fs+'/include']
fs_defs=['-DNDEBUG','-DWITH_PROFILING']
objects=[]
for name in sources:
    obj=work/(name.replace('/','_').rsplit('.',1)[0]+'.o');objects.append(obj)
    if name.endswith('.cpp'):
        run(['clang++','--target=i686-w64-mingw32','-nostdinc++','-fno-exceptions','-fno-rtti','-std=c++17',
             '-c','-o',obj,fs+'/'+name,*fs_inc,*wine_inc,*fs_defs,*i386_flags])
    else:
        run(['i686-w64-mingw32-gcc','-c','-o',obj,fs+'/'+name,*fs_inc,*wine_inc,*fs_defs,*i386_flags,
             '-mpreferred-stack-boundary=2','-mlong-double-64'])
library=work/'libfluidsynth.a'
if library.exists():library.unlink()
run(['i686-w64-mingw32-ar','rcs',library,*objects])
undefined=subprocess.check_output(['i686-w64-mingw32-nm','-u',str(objects[[s.endswith('.cpp') for s in sources].index(True)])],text=True)
if re.search(r'\b(_Z|__cxa|__gxx)',undefined):raise SystemExit('the C++ file needs a C++ runtime: '+undefined)

# dmsynth (dlls/dmsynth/Makefile.in: dmsynth.idl, dmsynth_main.c, synth.c, synthsink.c; PARENTSRC dmusic)
dm=src+'/dlls/dmsynth'
dm_inc=['-I'+dm,'-I'+src+'/dlls/dmusic','-I'+fs+'/include']
dm_objects=[]
for name in ('dmsynth_main.c','synth.c','synthsink.c'):
    obj=work/name.replace('.c','.o');dm_objects.append(obj)
    run(['i686-w64-mingw32-gcc','-c','-o',obj,dm+'/'+name,*dm_inc,*wine_inc,'-D__WINESRC__','-Wall',*i386_flags,
         '-mpreferred-stack-boundary=2','-mlong-double-64'])
registration=work/'dmsynth_r.res'
run(['tools/widl/widl','-o',registration,'-b','i686-w64-mingw32','--nostdinc','-Ldlls/*','-I'+dm,'-I'+src+'/dlls/dmusic',
     '-Iinclude','-I'+src+'/include','-I'+src+'/include/msvcrt','-D_UCRT','-D__WINESRC__',dm+'/dmsynth.idl'])
version=work/'version.res'
run(['tools/wrc/wrc','-u','-o',version,'--nostdinc','-I'+dm,'-Iinclude','-I'+src+'/include',
     '-DVER_FILEDESCRIPTION_STR="Wine DirectMusic Software Synthesizer"','-DVER_INTERNALNAME_STR="dmsynth.dll"',
     '-DVER_PRODUCTVERSION=5,3,0,900',src+'/include/common.ver'])
dll=out/'i386-windows/dmsynth.dll'
libs=[BUILD/p for p in ('libs/dxguid/i386-windows/libdxguid.a','libs/uuid/i386-windows/libuuid.a',
      'dlls/ole32/i386-windows/libole32.a','dlls/advapi32/i386-windows/libadvapi32.a','dlls/user32/i386-windows/libuser32.a',
      'libs/winecrt0/i386-windows/libwinecrt0.a','libs/compiler-rt/i386-windows/libcompiler-rt.a',
      'dlls/ucrtbase/i386-windows/libucrtbase.a','dlls/kernel32/i386-windows/libkernel32.a','dlls/ntdll/i386-windows/libntdll.a')]
for lib in libs:
    if not lib.is_file():raise SystemExit('missing import library: '+str(lib))
run(['tools/winegcc/winegcc','-o',dll,'--wine-objdir','.','--cc-cmd=i686-w64-mingw32-gcc','-b','i686-w64-mingw32',
     '-Wl,--wine-builtin','-shared',dm+'/dmsynth.spec',*dm_objects,registration,version,library,*libs,
     '-Wl,--disable-stdcall-fixup','-Wl,--build-id'])
# W139: dmband with GUID_Download. A DirectX 7 program (Blitz3D) loads a segment's instruments
# into the synthesizer with IDirectMusicSegment::SetParam(GUID_Download, performance); the
# pinned bandtrack.c only prints a FIXME for it, so no instrument reaches dmsynth and every note
# is "Could not find instrument". GUID_Download takes the same parameter as DirectX 8's
# GUID_DownloadToAudioPath (a performance or an audio path), so it uses that branch. The other
# dmband objects and resources are the host tree's own.
band_source=(SOURCE/'dlls/dmband/bandtrack.c').read_text()
old='''    else if (IsEqualGUID(type, &GUID_Download))
        FIXME("GUID_Download not handled yet\\n");
    else if (IsEqualGUID(type, &GUID_DownloadToAudioPath))
'''
if band_source.count(old)!=1:raise SystemExit('bandtrack.c GUID_Download branch not found once')
band_overlay=work/'bandtrack.c'
band_overlay.write_text(band_source.replace(old,'''    else if (IsEqualGUID(type, &GUID_Download) || IsEqualGUID(type, &GUID_DownloadToAudioPath))
'''))
band_dir=BUILD/'dlls/dmband/i386-windows'
band_objects=[band_dir/name for name in ('band.o','dmband_main.o','dmobject.o','dmband_r.res')]+[BUILD/'dlls/dmband/version.res']
for path in band_objects:
    if not path.is_file():raise SystemExit('missing dmband input: '+str(path))
band_obj=work/'bandtrack.o'
run(['i686-w64-mingw32-gcc','-c','-o',band_obj,band_overlay,'-I'+src+'/dlls/dmband','-I'+src+'/dlls/dmusic',*wine_inc,
     '-D__WINESRC__','-Wall',*i386_flags,'-mpreferred-stack-boundary=2','-mlong-double-64'])
band_dll=out/'i386-windows/dmband.dll'
run(['tools/winegcc/winegcc','-o',band_dll,'--wine-objdir','.','--cc-cmd=i686-w64-mingw32-gcc','-b','i686-w64-mingw32',
     '-Wl,--wine-builtin','-shared',src+'/dlls/dmband/dmband.spec',band_obj,*band_objects,
     *[lib for lib in libs if 'user32' not in str(lib)],'-Wl,--disable-stdcall-fixup','-Wl,--build-id'])
# W140: dmime with General MIDI drums for MIDI files. dmime's MIDI parser turns each program
# change into a band instrument with the bare program number, also on channel 10, so the drum
# channel downloads a melodic instrument; and a drum channel without a program change downloads
# nothing. dmsynth plays channel 10 as drums (patch | F_INSTRUMENT_DRUMS, falling back to the
# standard kit), finds no drum instrument and drops every drum note. Here channel 10's program
# changes carry F_INSTRUMENT_DRUMS, and the band track gets General MIDI's default for channel
# 10, the standard kit, at time 0 (a program change from the file, inserted after it, wins).
# The other dmime objects and resources are the host tree's own.
midi_source=(SOURCE/'dlls/dmime/midi.c').read_text()
midi_pairs=[('''    instrument.dwPatch = event->data[0];
''','''    instrument.dwPatch = event->data[0];
    if (instrument.dwPChannel == 9) instrument.dwPatch |= F_INSTRUMENT_DRUMS;
'''),('''        WARN("Failed to load default collection from loader, hr %#lx\\n", hr);

''','''        WARN("Failed to load default collection from loader, hr %#lx\\n", hr);

    {
        struct midi_event drums = {.status = MIDI_PROGRAM_CHANGE | 9};
        if (FAILED(hr = midi_parser_handle_program_change(parser, &drums))) return hr;
    }

''')]
for old,new in midi_pairs:
    if midi_source.count(old)!=1:raise SystemExit('midi.c context not found once: '+old[:50])
    midi_source=midi_source.replace(old,new)
midi_overlay=work/'midi.c';midi_overlay.write_text(midi_source)
dmime_dir=BUILD/'dlls/dmime/i386-windows'
dmime_units=('audiopath','band','dmime_main','dmobject','graph','lyricstrack','markertrack','paramcontroltrack',
             'performance','segment','segmentstate','segtriggertrack','seqtrack','sysextrack','tempotrack',
             'timesigtrack','wave','wavetrack')
dmime_inputs=[dmime_dir/(unit+'.o') for unit in dmime_units]+[dmime_dir/'dmime_r.res',BUILD/'dlls/dmime/version.res']
for path in dmime_inputs:
    if not path.is_file():raise SystemExit('missing dmime input: '+str(path))
midi_obj=work/'midi.o'
run(['i686-w64-mingw32-gcc','-c','-o',midi_obj,midi_overlay,'-I'+src+'/dlls/dmime','-I'+src+'/dlls/dmusic',*wine_inc,
     '-D__WINESRC__','-Wall',*i386_flags,'-mpreferred-stack-boundary=2','-mlong-double-64'])
dsound_lib=BUILD/'dlls/dsound/i386-windows/libdsound.a'
if not dsound_lib.is_file():raise SystemExit('missing import library: '+str(dsound_lib))
dmime_dll=out/'i386-windows/dmime.dll'
run(['tools/winegcc/winegcc','-o',dmime_dll,'--wine-objdir','.','--cc-cmd=i686-w64-mingw32-gcc','-b','i686-w64-mingw32',
     '-Wl,--wine-builtin','-shared',src+'/dlls/dmime/dmime.spec',midi_obj,*dmime_inputs,dsound_lib,*libs,
     '-Wl,--disable-stdcall-fixup','-Wl,--build-id'])
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(pathlib.Path(__file__)),
          'modules':{'dmsynth.dll':{'path':'i386-windows/dmsynth.dll','sha256':sha(dll)},
                     'dmband.dll':{'path':'i386-windows/dmband.dll','sha256':sha(band_dll),
                                   'source_change':'bandtrack.c: GUID_Download handled as GUID_DownloadToAudioPath'},
                     'dmime.dll':{'path':'i386-windows/dmime.dll','sha256':sha(dmime_dll),
                                  'source_change':'midi.c: channel 10 program changes are drum kits; standard kit at time 0'}},
          'fluidsynth':{'library':str(library.relative_to(ROOT)),'sha256':sha(library),'sources':len(sources),
                        'license':'LGPL-2.1-or-later (Wine libs/fluidsynth)'}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest['modules']))
