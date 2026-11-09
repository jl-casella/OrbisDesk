#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W302 (W001 kept in reports/wine-hardware-w001/release-w001): real Wine boot objects, automatic PE32 launch, file logs and packaged host UI."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,tarfile
from wine_prefix import validate_package
from wine_fonts import stage_fonts
from orbis_package import package_app
from orbis_self import set_exec_type
from project_brand import normalize_marker
# W217: the eboot is linked here and made ET_SCE_EXEC, which the kernel loads at its link
# address (B006 stage b, B007), so 0x400000 stays free for fixed-base PE32 images such as
# gta-vc.exe (docs/investigacion-gta-vc-base-0x400000.md).
EBOOT_BASE=0x1100000000
ROOT=pathlib.Path(__file__).resolve().parents[1];sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
parser=argparse.ArgumentParser()
parser.add_argument('--app-version',default='04.01',help='SFO and boot-selector version (NN.NN)')
parser.add_argument('--runtime-outside-package',action='store_true',
                    help='development builds only: a package without the runtime (upload it with upload-hardware.py)')
parser.add_argument('--allow-build-paths',action='store_true',
                    help='development builds only: ship even if binaries still hold the build PC\'s paths (recorded in the manifest)')
parser.add_argument('--mangohud',choices=('enabled','disabled'),default='enabled',
                    help='load the MangoHud layer (default enabled; disabled is a diagnostic control)')
args=parser.parse_args()
if not __import__('re').fullmatch(r'[0-9]{2}\.[0-9]{2}',args.app_version):
    parser.error('app-version must be NN.NN')
mangohud_enabled=args.mangohud=='enabled'
work=ROOT/'build/wine-hardware-w302';app=work/'app';out=ROOT/'out/wine-hardware-w302'
HW_BUILD_ID=work.name.rsplit('-',1)[1].upper()  # W302: the build this script makes (its work folder's name)
app.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
base=json.loads((ROOT/'build/wine-boot/link-report.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in base['object_hashes'].items():
    if sha(ROOT/name)!=digest:raise SystemExit('Wine object differs from proven link: '+name)
flags=base['helper_compile_flags']
def run(command):
    with (work/'build.log').open('a') as log:
        subprocess.run(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
renamed=work/'wine_boot_entry.o'
run([*flags,'-Dmain=pw_wine_boot_main','-c',ROOT/'native/wine_boot.c','-o',renamed])
wrapper=work/'wine_hardware.o';run([*flags,'-DPW_MANGOHUD_LAYER_ENABLED='+str(int(mangohud_enabled)),
    '-DHW_VERSION="'+args.app_version+'"',
    '-I'+str(ROOT/'native'),'-c',ROOT/'native/wine_hardware.c','-o',wrapper])
heap=work/'native_heap.o';run([*flags,'-c',ROOT/'native/native_heap.c','-o',heap])
telemetry=work/'telemetry.o';run([*flags,'-I'+str(ROOT/'platform/ps4'),'-c',ROOT/'native/telemetry.c','-o',telemetry])
# W135: the 32-bit compatibility-mode probe (phase 5)
compat32=work/'compat32_probe.o';run([*flags,'-c',ROOT/'native/compat32_probe.c','-o',compat32])
dos_audio=work/'dos_audio.o';run([*flags,'-I'+str(ROOT/'platform/ps4'),'-c',ROOT/'native/dos_audio.c','-o',dos_audio])
fs_override=work/'pw_wine_fs.o'
run([*flags,'-c',ROOT/'platform/ps4/pw_wine_fs.c','-o',fs_override])
# W136: the signal adapter with the raw entry native 32-bit code needs (phase 5A)
signals_override=work/'pw_wine_signals.o'
run([*flags,'-c',ROOT/'platform/ps4/pw_wine_signals.c','-o',signals_override])
delete_server=json.loads((ROOT/'build/delete-server-ps4/report.json').read_text())
if sha(ROOT/delete_server['object'])!=delete_server['object_sha256']:
    raise SystemExit('Delete-server audit object differs from its build report')
directory_build=json.loads((ROOT/'build/directory-ps4/report.json').read_text())
if sha(ROOT/directory_build['object'])!=directory_build['object_sha256']:
    raise SystemExit('Directory file object differs from its build report')
telemetry_build=json.loads((ROOT/'build/telemetry-ps4/report.json').read_text())
if sha(ROOT/telemetry_build['object'])!=telemetry_build['object_sha256']:
    raise SystemExit('Telemetry system object differs from its build report')
for key in ('gpu_source','gpu_library'):
    if sha(pathlib.Path(telemetry_build[key]))!=telemetry_build[key+'_sha256']:
        raise SystemExit('Telemetry GPU input changed: '+key)
sink=work/'sink.c';sink.write_text((ROOT/'platform/ps4/pw_wine_sink_ps4.c').read_text().replace('"/data/frames','"/data/orbisdesk/w302/frames'))
# W027: at most 8 BMP dumps (explorer builds its desktop over several frames); process time in the frame markers.
sink_obj=work/'sink.o';run([*flags,'-I'+str(ROOT/'native'),'-DPW_SINK_MAX_DUMPS=8','-DPW_SINK_TIMING=1','-DPW_SINK_EXTERNAL_INPUT','-DPW_SINK_ASYNC','-DPW_SINK_GPU','-c',sink,'-o',sink_obj])
# W028: controller input and the pointer position the sink draws.
pad=work/'hw_pad.o';run([*flags,'-c',ROOT/'native/hw_pad.c','-o',pad])
# W236: the control overlay (L3+R3), driven by the pad thread and drawn by the sink
overlay_obj=work/'hw_overlay.o';run([*flags,'-I'+str(ROOT/'native'),'-c',ROOT/'native/hw_overlay.c','-o',overlay_obj])
# W070 (H1): Mesa's RADV on GNM in Wine's ELF (tools/vk-h0, VARIANT=wine build in ~/vk-h0) and
# the G001 Vulkan probe in its in-Wine form (native/vk_probe/main.c, PW_VK_IN_WINE), which the
# launcher runs before Wine starts. libc++/libc++abi call pw_vk_pthread_once like Mesa does.
vk=pathlib.Path.home()/'vk-h0';mesa=vk/'build/mesa-wine'
vk_flags=['clang-19','--target=x86_64-pc-freebsd12-elf','-D__ORBIS__','-D__PS4__','-fPIC','-O2','-march=btver2',
          '-isysroot',str(sdk),'-isystem',str(sdk/'include'),'-I'+str(vk/'src/mesa/include')]
vk_probe=work/'vk_probe.o';run([*vk_flags,'-DPW_VK_IN_WINE','-Wno-format','-c',ROOT/'native/vk_probe/main.c','-o',vk_probe])
vk_runtime=work/'wine_vk_runtime.o';run([*flags,'-c',ROOT/'native/wine_vk_runtime.c','-o',vk_runtime])
# W158: dlopen/dlsym/dlerror/dlclose without musl's per-thread error state (platform/ps4/pw_wine_dl.c)
dl_override=work/'pw_wine_dl.o';run([*flags,'-c',ROOT/'platform/ps4/pw_wine_dl.c','-o',dl_override])
# W142 (phase 6): the sink's output through RADV (native/hw_sink_gpu); its SPIR-V comes from the
# GLSL next to it, compiled here by the glslang of ~/vk-h0/host-tools.
sink_gpu_dir=ROOT/'native/hw_sink_gpu';shader_dir=work/'sink-gpu-shaders';shader_dir.mkdir(exist_ok=True)
for stage in ('vert','frag'):
    run([vk/'host-tools/bin/glslang','-V','--target-env','vulkan1.1','--vn','screen_'+stage,
         '-o',shader_dir/('screen_'+stage+'.h'),sink_gpu_dir/('screen.'+stage)])
# W153: and the fragment shader without image layers, used when the compiled one would read them
# with FLAT instructions (hw_sink_gpu.c pipeline_init)
run([vk/'host-tools/bin/glslang','-V','--target-env','vulkan1.1','-DPOOL_ONLY','--vn','screen_frag_pool',
     '-o',shader_dir/'screen_frag_pool.h',sink_gpu_dir/'screen.frag'])
sink_gpu=work/'hw_sink_gpu.o';run([*vk_flags,'-I'+str(shader_dir),'-c',sink_gpu_dir/'hw_sink_gpu.c','-o',sink_gpu])
cxx_libs=[]
for name in ('libc++.a','libc++abi.a'):
    renamed_lib=work/name.replace('.a','-vk.a')
    run(['objcopy','--redefine-sym','pthread_once=pw_vk_pthread_once',vk/'sysroot/lib'/name,renamed_lib]);cxx_libs.append(renamed_lib)
mesa_libs=[mesa/p for p in ('src/amd/vulkan/libvulkan_radeon.a','src/amd/common/libamd_common.a','src/amd/compiler/libaco.a',
    'src/amd/addrlib/libaddrlib.a','src/vulkan/util/libvulkan_util.a','src/compiler/spirv/libvtn.a','src/compiler/nir/libnir.a',
    'src/compiler/libcompiler.a','src/util/libxmlconfig.a','src/util/libmesa_util.a','src/util/libmesa_util_simd.a',
    'src/util/libmesa_util_clflush.a','src/util/libmesa_util_clflushopt.a','src/util/libparson.a','src/util/blake3/libblake3.a',
    'src/c11/impl/libmesa_util_c11.a')]
# Mesa is built with -fdata-sections and libc++ has prioritized constructors: the SDK link
# script leaves .data.* and .init_array.* as orphans (zero on the console, constructors not
# run; DolphinPS4 toolchain/ps4-love-style.cmake), so the link uses a copy that collects them.
link_script=work/'link.x';text=(sdk/'link.x').read_text()
for old,new in (('*(.init_array);','KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*))); KEEP(*(.init_array));'),
                ('*(.data)','*(.data .data.*)'),('*(.tdata)','*(.tdata .tdata.*)'),('*(.tbss)','*(.tbss .tbss.*)')):
    if old not in text:raise SystemExit('unexpected SDK link.x: no '+old)
    text=text.replace(old,new)
# W217: the image starts at EBOOT_BASE. lld puts __dso_handle at the ELF header, which is not
# loaded and stays at 0 once the image moves, out of R_X86_64_PC32 range of Mesa's C++
# objects; it only has to be an address of this image (__cxa_atexit).
if not text.startswith('SECTIONS\n{'):raise SystemExit('unexpected SDK link.x start')
text='SECTIONS\n{\n\t. = 0x%x;\n\tHIDDEN(__dso_handle = .);\n'%EBOOT_BASE+text[len('SECTIONS\n{'):]
link_script.write_text(text)
command=base['bootstrap_command'].copy();command[command.index('-o')+1]=str(work/'wine.elf')
system_original=str(ROOT/'build/wine-boot/system.o')
if command.count(system_original)!=1:raise SystemExit('Expected one proven Wine system object in link')
command=[str(ROOT/telemetry_build['object']) if arg==system_original else arg for arg in command]
command[1:1]=[str(telemetry),str(dos_audio),str(compat32)]
# W120: ntdll's virtual.c that loads the audio driver by name from the static table
# (tools/build-audio-ps4.py); the driver object itself comes through link-wine-boot.py.
audio_build=json.loads((ROOT/'build/audio-ps4/report.json').read_text())
if audio_build['builder_sha256']!=sha(ROOT/'tools/build-audio-ps4.py'):raise SystemExit('audio objects differ from their builder')
for part in ('virtual','driver'):
    if sha(ROOT/audio_build['objects'][part]['object'])!=audio_build['objects'][part]['sha256']:
        raise SystemExit('audio object changed after its build: '+part)
# W130: ntdll's env.c whose initial directory takes PW_PROGRAM_DIR (tools/build-env-ps4.py)
env_build=json.loads((ROOT/'build/env-ps4/report.json').read_text())
if env_build['builder_sha256']!=sha(ROOT/'tools/build-env-ps4.py') or sha(ROOT/env_build['object'])!=env_build['object_sha256']:
    raise SystemExit('env object differs from its build')
env_original=str(ROOT/'build/wine-boot/env.o')
if command.count(env_original)!=1:raise SystemExit('Expected one proven Wine env object in link')
command=[str(ROOT/env_build['object']) if arg==env_original else arg for arg in command]
# W136: ntdll's signal_x86_64.c with the host FS slot and raw registration (tools/build-signal-ps4.py)
signal_build=json.loads((ROOT/'build/signal-ps4/report.json').read_text())
if signal_build['builder_sha256']!=sha(ROOT/'tools/build-signal-ps4.py') or sha(ROOT/signal_build['object'])!=signal_build['object_sha256']:
    raise SystemExit('signal object differs from its build')
signal_original=str(ROOT/'build/wine-boot/signal_x86_64.o')
if command.count(signal_original)!=1:raise SystemExit('Expected one proven Wine signal object in link')
command=[str(ROOT/signal_build['object']) if arg==signal_original else arg for arg in command]
signals_original=str(ROOT/'build/wine-boot/pw_wine_signals.o')
if command.count(signals_original)!=1:raise SystemExit('Expected one signal adapter in link')
command=[str(signals_override) if arg==signals_original else arg for arg in command]
virtual_original=str(ROOT/'build/wine-boot/virtual.o')
if command.count(virtual_original)!=1:raise SystemExit('Expected one proven Wine virtual object in link')
command=[str(ROOT/audio_build['objects']['virtual']['object']) if arg==virtual_original else arg for arg in command]
heap_entries=('malloc','calloc','realloc','free','memalign','__memalign','aligned_alloc','posix_memalign')
command[1:1]=[str(heap),*('--wrap='+name for name in heap_entries)]
# W188: socket options through platform/ps4/pw_wine_sockopt.c (this link only), which turns the SDK's Linux numbers
# for the TCP, IP and IPv6 levels into the kernel's FreeBSD ones (TCP_KEEPIDLE was TCP_NOPUSH).
sockopt=work/'pw_wine_sockopt.o';run([*flags,'-c',ROOT/'platform/ps4/pw_wine_sockopt.c','-o',sockopt])
command[1:1]=['--wrap=setsockopt','--wrap=getsockopt',str(sockopt)]
# W195: the server's SIGUSR1 reaches one thread (platform/ps4/pw_wine_threads.c: kernel id to pthread_t,
# filled from pthread_create, this link only; tools/build-wine-delete-server.py revises server/ptrace.c).
threads=work/'pw_wine_threads.o';run([*flags,'-c',ROOT/'platform/ps4/pw_wine_threads.c','-o',threads])
command[1:1]=['--wrap=pthread_create',str(threads)]
command[command.index('--script')+1]=str(link_script)
first_lib=next(i for i,arg in enumerate(command) if arg.startswith('-L'))
command[first_lib:first_lib]=[str(dl_override),str(vk_probe),str(vk_runtime),str(sink_gpu),'--whole-archive',*map(str,mesa_libs),'--no-whole-archive',
                              str(vk/'sysroot/lib/libz.a'),*map(str,cxx_libs)]
if command.count(str(ROOT/'build/wine-boot/pw_wine_fs.o'))!=1:
    raise SystemExit('Expected exactly one filesystem adapter in the saved link')
command=[str(fs_override) if arg==str(ROOT/'build/wine-boot/pw_wine_fs.o') else arg for arg in command]
if command.count(str(ROOT/'build/wine-server/inprocess.o'))!=1:
    raise SystemExit('Expected exactly one combined server object in the saved link')
command=[str(ROOT/delete_server['object']) if arg==str(ROOT/'build/wine-server/inprocess.o') else arg for arg in command]
if command.count(str(ROOT/'build/wine-boot/file.o'))!=1:
    raise SystemExit('Expected exactly one Wine file object in the saved link')
command=[str(ROOT/directory_build['object']) if arg==str(ROOT/'build/wine-boot/file.o') else arg for arg in command]
command=[str(renamed) if arg==str(ROOT/'build/wine-boot/wine_boot.o') else
         str(sink_obj) if arg==str(ROOT/'build/wine-boot/pw_wine_sink_ps4.o') else arg for arg in command]
# B1 (pe32-en-explorer-plan.md P1): ntdll's Unix units with WoW64 per thread and the late 32-bit world
# (tools/build-wow64-world-ps4.py) in place of the objects above. Its inputs are the sources those were
# built from: a changed input means that builder has to run again.
world_build=json.loads((ROOT/'build/wow64-world-ps4/report.json').read_text())
if world_build['builder_sha256']!=sha(ROOT/'tools/build-wow64-world-ps4.py'):raise SystemExit('wow64 world objects differ from their builder')
for source,digest in world_build['inputs'].items():
    if sha(ROOT/source)!=digest:raise SystemExit('wow64 world input changed; run tools/build-wow64-world-ps4.py: '+source)
for replaced,entry in world_build['replaces'].items():
    if sha(ROOT/entry['object'])!=entry['sha256']:raise SystemExit('wow64 world object changed after its build: '+entry['object'])
    if command.count(str(ROOT/replaced))!=1:raise SystemExit('Expected one '+replaced+' in the link')
    command=[str(ROOT/entry['object']) if arg==str(ROOT/replaced) else arg for arg in command]
# Keep the proven library search order: build/wine-boot/lib/libc.a must win over the SDK
# libc.a, whose readlink/lstat are raw FreeBSD syscalls (ENOSYS for W001 on hardware).
# The Steam client inside the title (tools/build-steam-hosted.py): one object whose only globals are
# pw_hw_steam_open/draw/pad/active (native/hw_pad.c, the sink), and its files for C:\orbis (below)
steam_build=json.loads((ROOT/'build/steam-hosted/manifest.json').read_text())
steam_object=ROOT/steam_build['object']
if sha(steam_object)!=steam_build['object_sha256']:raise SystemExit('Steam object differs from its build')
command[1:1]=[str(steam_object)]
command[1:1]=['--wrap=exit','--wrap=_exit','--wrap=sceKernelDebugOutText','--wrap=write','--wrap=vfprintf','--wrap=fprintf','--wrap=fputs','--wrap=fwrite',str(wrapper),str(pad),str(overlay_obj)];command+=['-lSceSysmodule','-lSceSystemService','-lScePad','-lSceUserService','-lSceRtc','-lSceAudioOut']
run(command)
def symbols(elf,flag):
    listing=subprocess.run(['llvm-nm-14',flag,str(elf)],capture_output=True,text=True,check=True).stdout
    return {line.split()[-1] for line in listing.splitlines() if line.strip()}
captured=sorted(symbols(ROOT/'build/wine-boot/bootstrap.elf','--undefined-only')&symbols(work/'wine.elf','--defined-only'))
if captured:raise SystemExit('kernel imports of the proven ELF became static definitions: '+', '.join(captured))
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
with (work/'build.log').open('a') as log:subprocess.run([str(sdk/'bin/linux/create-fself'),'-in='+str(work/'wine.elf'),
    '-out='+str(work/'wine.oelf'),'--eboot',str(app/'eboot.bin'),'--paid','0x3800000000000011'],
    env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
(work/'wine.exec.oelf').write_bytes(set_exec_type(work/'wine.oelf',app/'eboot.bin'))
# Stage the same sealed prefix without DOS links: PS4 applications cannot use symbolic
# links, so pw_wine_fs serves c: and z: from a fixed mount table.
data=work/'runtime';data.mkdir(exist_ok=True)
prefix=data/'wine-prefix';prefix.mkdir(exist_ok=True)
package=ROOT/'reports/increment15/prefix-package'
wine_commit=json.loads((ROOT/'build/wine-boot/report.json').read_text())['wine_commit']
verified=validate_package(package,wine_commit)
with tarfile.open(package/'prefix.tar.gz') as archive:
    for member in archive:
        relative=pathlib.PurePosixPath(member.name).relative_to('prefix')
        dest=prefix.joinpath(*relative.parts)
        if member.isdir():dest.mkdir(parents=True,exist_ok=True)
        elif member.isfile():
            dest.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(member) as src,dest.open('wb') as target:shutil.copyfileobj(src,target)
        elif not member.issym():raise SystemExit('Unexpected prefix entry')
for folder in ('wine-home','wine/lib/wine/i386-windows','wine/lib/wine/x86_64-windows','wine/lib/wine/x86_64-unix','wine/share/wine/nls'):
    (data/folder).mkdir(parents=True,exist_ok=True)
# alpha-1: the prefix was made on the build PC as its user (W048); Wine runs as "orbis" (native/wine_boot.c).
# The registry's profile paths are rewritten to C:\users\orbis below (system.reg, user.reg, userdef.reg)
# and the host profile's folder is not shipped (W048's mirror makes the same tree for orbis).
host_profiles=[p for p in (prefix/'drive_c/users').iterdir() if p.is_dir() and p.name not in ('Public','orbis')]
if len(host_profiles)!=1:raise SystemExit('prefix: expected one host user profile, found '+str([p.name for p in host_profiles]))
HOST_PROFILE_REG='C:\\\\users\\\\'+host_profiles[0].name   # as written in a .reg file (C:\\users\\<name>)
def orbis_profile(text,name):
    """The host profile's registry paths as C:\\users\\orbis; the name must be there (a prefix change shows)."""
    if HOST_PROFILE_REG not in text:raise SystemExit(name+': expected '+HOST_PROFILE_REG)
    text=text.replace(HOST_PROFILE_REG+'\\\\','C:\\\\users\\\\orbis\\\\').replace(HOST_PROFILE_REG+'"','C:\\\\users\\\\orbis"')
    if HOST_PROFILE_REG.lower() in text.lower():raise SystemExit(name+': host profile path left after rewrite')
    return text
userdef_reg=prefix/'userdef.reg';userdef_reg.write_text(orbis_profile(userdef_reg.read_text(),'userdef.reg'))
shutil.copyfile(ROOT/'out/console32-bare.exe',data/'console32.exe')
runtime=json.loads((ROOT/'out/wine/wine-runtime-manifest.json').read_text())
def copy_verified(source,target,digest):
    if sha(source)!=digest:raise SystemExit('Runtime input hash mismatch: '+str(source))
    shutil.copyfile(source,target)
for e in runtime['modules']:copy_verified(ROOT/'out/wine'/e['path'],data/'wine/lib/wine/i386-windows'/e['name'],e['sha256'])
for e in runtime['data']:
    source=ROOT/'out/wine'/e['path'];copy_verified(source,data/'wine/share/wine/nls'/source.name,e['sha256'])
pe64=json.loads((ROOT/'out/wine-pe64/manifest.json').read_text())
for e in pe64['modules'].values():
    source=ROOT/'out/wine-pe64'/e['path'];copy_verified(source,data/'wine/lib/wine/x86_64-windows'/source.name,e['sha256'])
cpu=json.loads((ROOT/'out/wowprospero-ps4/manifest.json').read_text())
for e in cpu['modules'].values():
    source=ROOT/'out/wowprospero-ps4'/e['path'];copy_verified(source,data/'wine/lib/wine/x86_64-windows'/source.name,e['sha256'])
shutil.copyfile(ROOT/'out/wowprospero-ps4/x86_64-windows/wowprospero.dll',prefix/'drive_c/windows/system32/wowprospero.dll')
# W137: wow64native.dll (32-bit code in compatibility mode) and the wow64.dll that chooses it, with
# wowprospero.dll as fallback (tools/build-wow64native-ps4.py); this wow64.dll replaces the one above.
native_cpu=json.loads((ROOT/'out/wow64native-ps4/manifest.json').read_text())
if native_cpu['builder_sha256']!=sha(ROOT/'tools/build-wow64native-ps4.py'):raise SystemExit('wow64native differs from its builder')
for e in native_cpu['modules'].values():
    source=ROOT/'out/wow64native-ps4'/e['path'];copy_verified(source,data/'wine/lib/wine/x86_64-windows'/source.name,e['sha256'])
shutil.copyfile(ROOT/'out/wow64native-ps4/x86_64-windows/wow64native.dll',prefix/'drive_c/windows/system32/wow64native.dll')
# W119: i386 DLLs for 32-bit games (tools/stage-wine-i386.py: DirectDraw/D3D, DirectInput,
# DirectPlay, DirectSound, Winsock 1, Vulkan), in syswow64 and the i386 builtin folder.
wow32=json.loads((ROOT/'out/wine-i386/manifest.json').read_text())
if wow32['builder_sha256']!=sha(ROOT/'tools/stage-wine-i386.py'):raise SystemExit('i386 DLLs differ from their stager')
for name,e in wow32['modules'].items():
    source=ROOT/'out/wine-i386'/e['path']
    for target in (data/'wine/lib/wine/i386-windows'/name,prefix/'drive_c/windows/syswow64'/name):
        copy_verified(source,target,e['sha256'])
# W138: DirectMusic's software synthesizer for 32-bit programs (tools/build-dmsynth-i386.py);
# W139: also its dmband.dll with GUID_Download, and W140 its dmime.dll with General MIDI drums;
# both replace the ones staged above.
dmsynth=json.loads((ROOT/'out/dmsynth-i386/manifest.json').read_text())
if dmsynth['builder_sha256']!=sha(ROOT/'tools/build-dmsynth-i386.py'):raise SystemExit('dmsynth differs from its builder')
for name,e in dmsynth['modules'].items():
    for target in (data/'wine/lib/wine/i386-windows'/name,prefix/'drive_c/windows/syswow64'/name):
        copy_verified(ROOT/'out/dmsynth-i386'/e['path'],target,e['sha256'])
# W124: DXVK (tools/stage-dxvk.py) as the native d3d8/d3d9/d3d10core/d3d11 of both views,
# chosen by user.reg DllOverrides below. Its 64-bit dxgi.dll is not staged: Wine's builtin dxgi
# stays the one the Khronos loader and MangoHud use (W087), and 64-bit programs share that
# process as guests (W052).
# W172 (phase 7): its 32-bit dxgi.dll goes to syswow64. A 32-bit program runs in its own process
# (W116) with Wine's builtin vulkan-1 and no Khronos loader, and DXVK's d3d10core/d3d11 need
# DXVK's dxgi. With "dxgi"="native,builtin" a 32-bit program finds DXVK's file there; in 64 bits
# system32\dxgi.dll is Wine's, which carries the builtin signature and so still loads as builtin.
# W190: DXVK's 64-bit dxgi.dll goes to system32 too. In W189 a 64-bit D3D11 program got past
# DXVK's device and memory, then Wine's dxgi refused DXVK's device for the swap chain ("This is
# not the device we're looking for"). Wine's builtin dxgi stays in lib/wine/x86_64-windows, and
# explorer.exe (every 64-bit guest shares its process and its AppDefaults) loads it by
# DllOverrides "dxgi"="builtin" (user.reg below). A 64-bit title that runs alone gets DXVK's.
dxvk=json.loads((ROOT/'out/dxvk/manifest.json').read_text())
if dxvk['builder_sha256']!=sha(ROOT/'tools/stage-dxvk.py'):raise SystemExit('DXVK differs from its stager')
for key,e in dxvk['files'].items():
    arch,name=key.split('/')
    folder=prefix/'drive_c/windows'/('system32' if arch=='x64' else 'syswow64')
    copy_verified(ROOT/'out/dxvk'/e['path'],folder/name,e['sha256'])
    # W192: and as dxvk_dxgi.dll, which Wine's dxgi (tools/build-dxgi-hw.py) loads beside itself
    # to create swap chains for DXVK devices in explorer's process
    if key=='x64/dxgi.dll':copy_verified(ROOT/'out/dxvk'/e['path'],folder/'dxvk_dxgi.dll',e['sha256'])
# W128: the hardware 32-bit ddraw (tools/build-ddraw-hw.py): with wined3d's Vulkan renderer a
# windowed primary is presented through the back buffer (the Vulkan front buffer has no drawable).
ddraw_hw=json.loads((ROOT/'out/ddraw-hw/manifest.json').read_text())
if ddraw_hw['builder_sha256']!=sha(ROOT/'tools/build-ddraw-hw.py'):raise SystemExit('ddraw differs from its builder')
for target in (data/'wine/lib/wine/i386-windows/ddraw.dll',prefix/'drive_c/windows/syswow64/ddraw.dll'):
    copy_verified(ROOT/'out/ddraw-hw'/ddraw_hw['ddraw']['path'],target,ddraw_hw['ddraw']['sha256'])
# W166: the 32-bit winevulkan.dll with prospero-win's Vulkan call batching (tools/build-winevulkan-batch.py),
# over the staged one; its Unix side is in the ELF from the same tree (tools/build-winevulkan-ps4.py).
vk_batch=json.loads((ROOT/'out/winevulkan-batch/manifest.json').read_text())
if vk_batch['builder_sha256']!=sha(ROOT/'tools/build-winevulkan-batch.py'):raise SystemExit('winevulkan batch differs from its builder')
for target in (data/'wine/lib/wine/i386-windows/winevulkan.dll',prefix/'drive_c/windows/syswow64/winevulkan.dll'):
    copy_verified(ROOT/'out/winevulkan-batch'/vk_batch['winevulkan']['path'],target,vk_batch['winevulkan']['sha256'])
# W160: the 32-bit wined3d with command stream timing (tools/build-wined3d-hw.py), over the staged one.
wined3d_hw=json.loads((ROOT/'out/wined3d-hw/manifest.json').read_text())
if wined3d_hw['builder_sha256']!=sha(ROOT/'tools/build-wined3d-hw.py'):raise SystemExit('wined3d differs from its builder')
for target in (data/'wine/lib/wine/i386-windows/wined3d.dll',prefix/'drive_c/windows/syswow64/wined3d.dll'):
    copy_verified(ROOT/'out/wined3d-hw'/wined3d_hw['wined3d']['path'],target,wined3d_hw['wined3d']['sha256'])
# W287 (the overlay's GRAFICOS): Wine's own i386 d3d8 and d3d9 (on wined3d) in syswow64\pw-wined3d, which the guests'
# ntdll loads for a 32-bit guest whose AppDefaults\<exe>\DllOverrides asks for builtin (tools/build-guest-hw.py);
# syswow64's d3d8 and d3d9 stay DXVK's.
(prefix/'drive_c/windows/syswow64/pw-wined3d').mkdir(exist_ok=True)
for name in ('d3d8.dll','d3d9.dll'):
    e=wow32['modules'][name]
    copy_verified(ROOT/'out/wine-i386'/e['path'],prefix/'drive_c/windows/syswow64/pw-wined3d'/name,e['sha256'])
# W120: the 64-bit Windows audio DLLs (mmdevapi, dsound, msacm32) from the same stager.
for name,e in wow32['modules_x64'].items():
    source=ROOT/'out/wine-i386'/e['path']
    for target in (data/'wine/lib/wine/x86_64-windows'/name,prefix/'drive_c/windows/system32'/name):
        copy_verified(source,target,e['sha256'])
# W261 (W259/W260: games found Wine DLLs missing one at a time): the rest of the tree's modules a program could import,
# in syswow64 (i386) or system32 (x86_64) only: none has a Unix side, and Wine loads a builtin found there (as the
# sealed prefix's own modules); their registration is appended to system.reg below.
for arch,windows in (('i386-windows','syswow64'),('x86_64-windows','system32')):
    for name,e in wow32['w261'][arch].items():
        copy_verified(ROOT/'out/wine-i386'/e['path'],prefix/'drive_c/windows'/windows/name,e['sha256'])
# W280 (W278: GTA San Andreas ends on wmvcore's delay-load of winegstreamer.dll, absent here): wmvcore.dll whose
# readers fail with ERR "PWWMV" and HRESULT_FROM_WIN32 when winegstreamer.dll does not load (tools/build-wmvcore-hw.py);
# it replaces the W261 copies above and goes to the builtin folders too.
wmvcore_hw=json.loads((ROOT/'out/wmvcore-hw/manifest.json').read_text())
if wmvcore_hw['builder_sha256']!=sha(ROOT/'tools/build-wmvcore-hw.py'):raise SystemExit('wmvcore differs from its builder')
for arch,windows in (('i386-windows','syswow64'),('x86_64-windows','system32')):
    e=wmvcore_hw['modules'][arch]
    for target in (data/'wine/lib/wine'/arch/'wmvcore.dll',prefix/'drive_c/windows'/windows/'wmvcore.dll'):
        copy_verified(ROOT/'out/wmvcore-hw'/e['path'],target,e['sha256'])
# W015: the PE64 GUI closure, fixtures and fonts, staged as run-linux-wine.py --wine-gui does.
gui=json.loads((ROOT/'out/wine-gui/manifest.json').read_text())
for e in gui['modules'].values():
    source=ROOT/'out/wine-gui'/e['path'];copy_verified(source,data/'wine/lib/wine/x86_64-windows'/source.name,e['sha256'])
for name in ('gui-window64.exe','gui-text64.exe'):
    copy_verified(ROOT/gui['targets'][name]['path'],prefix/'drive_c/orbis'/name,gui['targets'][name]['sha256'])
stage_fonts(ROOT,ROOT/'out/wine-gui',gui['fonts'],prefix)
# W116: the same window fixture as a PE32 (i386), the first 32-bit GUI program under WoW64
# (wowprospero) on hardware; opened from the desktop it relaunches the title (kernelbase).
gui32=work/'gui-window32.exe'
subprocess.run(['i686-w64-mingw32-gcc','-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/gui_window.c'),
                '-o',str(gui32)],check=True)
shutil.copyfile(gui32,prefix/'drive_c/orbis/gui-window32.exe')
# W120: a two-second tone through winmm, 64-bit (a guest) and 32-bit (relaunch), for phase 3.
for compiler,name in (('x86_64-w64-mingw32-gcc','sound64.exe'),('i686-w64-mingw32-gcc','sound32.exe')):
    subprocess.run([compiler,'-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/sound_test.c'),
                    '-o',str(work/name),'-lwinmm'],check=True)
    shutil.copyfile(work/name,prefix/'drive_c/orbis'/name)
# W127: DirectDraw 7 / Direct3D 7 as Blitz3D uses them (fixtures/win32/ddraw7test.c), 32-bit,
# through ddraw and wined3d's Vulkan renderer (the launcher sets renderer=vulkan for PE32 runs).
subprocess.run(['i686-w64-mingw32-gcc','-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/ddraw7test.c'),
                '-o',str(work/'ddraw7test32.exe'),'-lddraw','-ldxguid'],check=True)
shutil.copyfile(work/'ddraw7test32.exe',prefix/'drive_c/orbis/ddraw7test32.exe')
# W133: how a 32-bit program reads a data file (fixtures/win32/fileio_test.c): SuperMarioKart.exe
# opened its first PNG twice without one read (W132).
subprocess.run(['i686-w64-mingw32-gcc','-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/fileio_test.c'),
                '-o',str(work/'fileio32.exe')],check=True)
shutil.copyfile(work/'fileio32.exe',prefix/'drive_c/orbis/fileio32.exe')
# B0 of the plan for 32-bit guests of explorer (pe32-en-explorer-plan.md): fixtures/win32/wow64probe.c,
# a 64-bit guest that writes C:\orbis\wow64probe-result.txt (low address space, raw signals,
# wow64native initialized in explorer); explorer gets the raw signals while C:\orbis\wow64probe.txt
# exists (native/wine_hardware.c).
subprocess.run(['x86_64-w64-mingw32-gcc','-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/wow64probe.c'),
                '-o',str(work/'wow64probe64.exe')],check=True)
shutil.copyfile(work/'wow64probe64.exe',prefix/'drive_c/orbis/wow64probe64.exe')
# B1 (pe32-en-explorer-plan.md P5): C:\windows\syswow64\orbis32host.exe, the image of the 32-bit
# world's PEB (fixtures/win32/orbis32host.c: ps4_guest32_start runs a 32-bit program on a WoW64 thread
# of explorer), and C:\orbis\wow64world64.exe, the 64-bit guest that creates the world and runs
# C:\orbis\console32.exe in it twice (fixtures/win32/wow64world.c, C:\orbis\wow64world-result.txt).
subprocess.run(['i686-w64-mingw32-gcc','-O2','-Wall','-ffreestanding','-fno-stack-protector','-fno-asynchronous-unwind-tables',
                '-nostdlib','-Wl,--entry,_host_entry,--image-base,0x30000000,--kill-at,--no-insert-timestamp',
                str(ROOT/'fixtures/win32/orbis32host.c'),'-lkernel32','-o',str(work/'orbis32host.exe')],check=True)
shutil.copyfile(work/'orbis32host.exe',prefix/'drive_c/windows/syswow64/orbis32host.exe')
subprocess.run(['x86_64-w64-mingw32-gcc','-O2','-Wall','-mwindows','-Wl,--no-insert-timestamp',
                str(ROOT/'fixtures/win32/wow64world.c'),'-o',str(work/'wow64world64.exe')],check=True)
shutil.copyfile(work/'wow64world64.exe',prefix/'drive_c/orbis/wow64world64.exe')
# W124: the first Direct3D 9 program (fixtures/win32/d3d9test.c), 64-bit (guest) and 32-bit.
for compiler,name in (('x86_64-w64-mingw32-gcc','d3d9test64.exe'),('i686-w64-mingw32-gcc','d3d9test32.exe')):
    subprocess.run([compiler,'-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/d3d9test.c'),
                    '-o',str(work/name),'-ld3d9'],check=True)
    shutil.copyfile(work/name,prefix/'drive_c/orbis'/name)
# W172 (phase 7): the first Direct3D 11 program (fixtures/win32/d3d11test.c). The 32-bit one is the
# test (DXVK's dxgi); the 64-bit one runs as a guest with Wine's dxgi and is expected to fail there.
for compiler,name in (('x86_64-w64-mingw32-gcc','d3d11test64.exe'),('i686-w64-mingw32-gcc','d3d11test32.exe')):
    subprocess.run([compiler,'-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/d3d11test.c'),
                    '-o',str(work/name),'-ld3d11','-ldxgi','-luuid'],check=True)
    shutil.copyfile(work/name,prefix/'drive_c/orbis'/name)
# W181: pad key profiles for keyboard-only games (native/hw_pad.c reads C:\orbis\padmaps\<exe>.ini when
# the launcher runs that program); SuperMarioKart.exe's maps the pad to its arrows, space and Enter.
(prefix/'drive_c/orbis/padmaps').mkdir(exist_ok=True)
for profile in sorted((ROOT/'fixtures/padmaps').glob('*.ini')):
    shutil.copyfile(profile,prefix/'drive_c/orbis/padmaps'/profile.name)
# W174 (phase 8): networking as a Windows program sees it (fixtures/win32/nettest.c), 64-bit (guest)
# and 32-bit; each run appends its steps to C:\orbis\net-result.txt.
for compiler,name in (('x86_64-w64-mingw32-gcc','nettest64.exe'),('i686-w64-mingw32-gcc','nettest32.exe')):
    subprocess.run([compiler,'-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/nettest.c'),
                    '-o',str(work/name),'-lws2_32','-liphlpapi'],check=True)
    shutil.copyfile(work/name,prefix/'drive_c/orbis'/name)
# W177 (phase 9): the IE control embedded in a program (fixtures/win32/webview.c), 64-bit (guest)
# and 32-bit; each run appends its steps to C:\orbis\webview-result.txt. Local page: C:\orbis\webtest.
for compiler,name in (('x86_64-w64-mingw32-gcc','webview64.exe'),('i686-w64-mingw32-gcc','webview32.exe')):
    subprocess.run([compiler,'-O2','-mwindows','-Wl,--no-insert-timestamp',str(ROOT/'fixtures/win32/webview.c'),
                    '-o',str(work/name),'-lole32','-loleaut32','-luuid'],check=True)
    shutil.copyfile(work/name,prefix/'drive_c/orbis'/name)
(prefix/'drive_c/orbis/webtest').mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'fixtures/web/index.html',prefix/'drive_c/orbis/webtest/index.html')
# W179: "Wine Configuration" in the Start menu's Control Panel, which lists the Control Panel
# applets in system32: a 64-bit applet (fixtures/win32/winecfgcpl.c) with winecfg's icon that
# starts winecfg.exe.
subprocess.run(['x86_64-w64-mingw32-windres','-I',str(ROOT/'.deps/wine/source/programs/winecfg'),str(ROOT/'fixtures/win32/winecfgcpl.rc'),
                '-O','coff','-o',str(work/'winecfgcpl-res.o')],check=True)
subprocess.run(['x86_64-w64-mingw32-gcc','-O2','-shared','-municode','-Wl,--no-insert-timestamp','-Wl,--kill-at',
                str(ROOT/'fixtures/win32/winecfgcpl.c'),str(work/'winecfgcpl-res.o'),'-o',str(work/'winecfg.cpl')],check=True)
shutil.copyfile(work/'winecfg.cpl',prefix/'drive_c/windows/system32/winecfg.cpl')
# W043: Wine's own programs (tools/stage-wine-programs.py), also in system32, where Run
# and the Start menu find them by name.
# W173: their import closure too. winecfg (W172) brought uxtheme.dll and msimg32.dll, which the
# sealed prefix does not have in system32; only in the builtin folder, the loader did not find
# them ("Library uxtheme.dll (which is needed by winecfg.exe) not found", c0000135).
programs=json.loads((ROOT/'out/wine-programs/manifest.json').read_text())
for name,e in programs['modules'].items():
    source=ROOT/'out/wine-programs'/e['path'];copy_verified(source,data/'wine/lib/wine/x86_64-windows'/source.name,e['sha256'])
    copy_verified(source,prefix/'drive_c/windows/system32'/name,e['sha256'])
# W229: joy.cpl without the Windows.Gaming.Input page (tools/build-joycpl-hw.py) replaces the pinned one
# that the block above copied, in the builtin folder and system32.
joycpl=json.loads((ROOT/'out/joycpl-hw/manifest.json').read_text())
if joycpl['builder_sha256']!=sha(ROOT/'tools/build-joycpl-hw.py'):raise SystemExit('joy.cpl differs from its builder')
for target in (data/'wine/lib/wine/x86_64-windows/joy.cpl',prefix/'drive_c/windows/system32/joy.cpl'):
    copy_verified(ROOT/'out/joycpl-hw'/joycpl['joy.cpl']['path'],target,joycpl['joy.cpl']['sha256'])
# W178 (phase 7): xinput with the console's pad as controller 0 (tools/build-xinput-hw.py) for both
# views, in the builtin folders and system32/syswow64, with the 64-bit hid.dll it imports. Its Unix
# side is in the boot ELF (tools/link-wine-boot.py); the pad is native/hw_pad.c's.
xinput=json.loads((ROOT/'out/xinput-hw/manifest.json').read_text())
if xinput['builder_sha256']!=sha(ROOT/'tools/build-xinput-hw.py'):raise SystemExit('xinput differs from its builder')
for key,e in xinput['modules'].items():
    arch,name=key.split('/')
    for target in (data/'wine/lib/wine'/(arch+'-windows')/name,prefix/'drive_c/windows'/('system32' if arch=='x86_64' else 'syswow64')/name):
        copy_verified(ROOT/'out/xinput-hw'/e['path'],target,e['sha256'])
# W179 (phase 7): dinput/dinput8 with the console's pad as a DirectInput gamepad (tools/build-dinput-hw.py:
# joystick_pad.c over XInput controller 0), for both views, in the builtin folders and system32/syswow64.
dinput=json.loads((ROOT/'out/dinput-hw/manifest.json').read_text())
if dinput['builder_sha256']!=sha(ROOT/'tools/build-dinput-hw.py'):raise SystemExit('dinput differs from its builder')
for key,e in dinput['modules'].items():
    arch,name=key.split('/')
    for target in (data/'wine/lib/wine'/(arch+'-windows')/name,prefix/'drive_c/windows'/('system32' if arch=='x86_64' else 'syswow64')/name):
        copy_verified(ROOT/'out/dinput-hw'/e['path'],target,e['sha256'])
# HID stack (tools/build-hidstack-hw.py): ntoskrnl.exe (overlay) and the HID drivers in the builtin
# folder and the prefix (drivers in system32\drivers, as their service keys name them), and
# pwhidhost.dll, which explorer loads to run them. winebus's Unix side is in the boot ELF.
hidstack=json.loads((ROOT/'out/hidstack-hw/manifest.json').read_text())
if hidstack['builder_sha256']!=sha(ROOT/'tools/build-hidstack-hw.py'):raise SystemExit('HID stack differs from its builder')
if hidstack['bus_source_sha256']!=sha(ROOT/'native/winebus_orbis.c') or hidstack['host']['source_sha256']!=sha(ROOT/'native/pwhidhost.c'):
    raise SystemExit('HID stack differs from its sources')
for name,e in hidstack['modules'].items():
    folder='system32/drivers' if e['driver'] else 'system32'
    for target in (data/'wine/lib/wine/x86_64-windows'/name,prefix/'drive_c/windows'/folder/name):
        copy_verified(ROOT/'out/hidstack-hw'/e['path'],target,e['sha256'])
# W200: pwhidhost.dll staged again. W198's freeze (faults at C023E040/C0221B30) was ntoskrnl relocating
# already-relocated guest executables a second time, and winebus's 0xc0000001 a bogus service-manager
# handle; build-hidstack-hw.py's overlay now relocates drivers only and loads them from their service key.
copy_verified(ROOT/'out/hidstack-hw'/hidstack['host']['path'],prefix/'drive_c/windows/system32/pwhidhost.dll',hidstack['host']['sha256'])
# W174 (phase 7): common controls v6 and audio codecs (tools/stage-wine-extras.py) for both views:
# each in its builtin folder and, except comctl32_v6 (loaded by that name only from the builtin
# folder), in system32/syswow64; and the common-controls 6.0 assembly in winsxs, as Wine's
# setupapi installs it. winecfg's About page needs SysLink (v6 only), its test sound IMA ADPCM.
extras=json.loads((ROOT/'out/wine-extras/manifest.json').read_text())
if extras['builder_sha256']!=sha(ROOT/'tools/stage-wine-extras.py'):raise SystemExit('Wine extras differ from their stager')
for key,e in extras['modules'].items():
    arch,name=key.split('/')
    targets=[data/'wine/lib/wine'/(arch+'-windows')/name]
    if name!='comctl32_v6.dll':targets.append(prefix/'drive_c/windows'/('system32' if arch=='x86_64' else 'syswow64')/name)
    for target in targets:copy_verified(ROOT/'out/wine-extras'/e['path'],target,e['sha256'])
for assembly in extras['winsxs'].values():
    for e in (assembly['dll'],assembly['manifest']):
        target=prefix/'drive_c/windows'/e['path'];target.parent.mkdir(parents=True,exist_ok=True)
        copy_verified(ROOT/'out/wine-extras'/e['path'],target,e['sha256'])
# W175: Aero, Wine's only visual style, where wine.inf puts it; winecfg lists the visual styles of
# resources\themes. Not applied: ThemeManager in user.reg stays as it is until the user picks it.
for name,e in extras['themes'].items():
    target=prefix/'drive_c/windows/resources/themes'/name;target.parent.mkdir(parents=True,exist_ok=True)
    copy_verified(ROOT/'out/wine-extras'/e['path'],target,e['sha256'])
# W177: Luna (Windows XP look) and Noir (Royale Noir look), visual styles built from Wine's aero
# (tools/build-msstyles-hw.py), each in its own folder of resources\themes, where winecfg lists them.
msstyles=json.loads((ROOT/'out/msstyles-hw/manifest.json').read_text())
if msstyles['builder_sha256']!=sha(ROOT/'tools/build-msstyles-hw.py'):raise SystemExit('visual styles differ from their builder')
for key,e in msstyles['styles'].items():
    target=prefix/'drive_c/windows/resources/themes'/e['path'];target.parent.mkdir(parents=True,exist_ok=True)
    copy_verified(ROOT/'out/msstyles-hw'/e['path'],target,e['sha256'])
# W177 (phase 9): MSHTML, its import closure and the DLLs Pale Moon and Wine Gecko import
# (tools/stage-mshtml-hw.py): 64-bit in system32, 32-bit in syswow64, each also in its builtin
# folder; iexplore.exe also where wineboot would put it.
mshtml=json.loads((ROOT/'out/mshtml-hw/manifest.json').read_text())
if mshtml['builder_sha256']!=sha(ROOT/'tools/stage-mshtml-hw.py'):raise SystemExit('MSHTML differs from its stager')
for arch,windows,program_files in (('x86_64-windows','system32','Program Files'),('i386-windows','syswow64','Program Files (x86)')):
    for name,e in mshtml['modules'][arch].items():
        source=ROOT/'out/mshtml-hw'/e['path']
        for target in (data/'wine/lib/wine'/arch/name,prefix/'drive_c/windows'/windows/name):
            copy_verified(source,target,e['sha256'])
        if name=='iexplore.exe':
            target=prefix/'drive_c'/program_files/'Internet Explorer/iexplore.exe';target.parent.mkdir(parents=True,exist_ok=True)
            copy_verified(source,target,e['sha256'])
# W225: DirectShow for 32-bit programs and its MPEG-1 filter (tools/stage-dshow-i386.py): the Wine
# modules in syswow64 and their builtin folder, pwmpeg1.ax (native) in syswow64 only; the registration
# is appended to system.reg below. GTA Vice City's intro videos (MPEG-1) found no FilterGraph (W221).
dshow=json.loads((ROOT/'out/dshow-i386/manifest.json').read_text())
if dshow['builder_sha256']!=sha(ROOT/'tools/stage-dshow-i386.py'):raise SystemExit('DirectShow differs from its stager')
for name,e in dshow['modules'].items():
    source=ROOT/'out/dshow-i386'/e['path']
    targets=[prefix/'drive_c/windows/syswow64'/name]+([data/'wine/lib/wine/i386-windows'/name] if e['builtin'] else [])
    for target in targets:copy_verified(source,target,e['sha256'])
# W177 (phase 9): Wine Gecko 2.47.4 (tools/stage-wine-gecko.py) where its .msi would put it; GeckoPath
# below. About 108 MB (x86_64) and 109 MB (x86).
gecko=json.loads((ROOT/'out/wine-gecko/manifest.json').read_text())
if gecko['builder_sha256']!=sha(ROOT/'tools/stage-wine-gecko.py'):raise SystemExit('Wine Gecko differs from its stager')
for arch,windows in (('x86_64','system32'),('x86','syswow64')):
    for relative,digest in gecko['trees'][arch]['files'].items():
        target=prefix/'drive_c/windows'/windows/'gecko'/gecko['version']/relative;target.parent.mkdir(parents=True,exist_ok=True)
        copy_verified(ROOT/'out/wine-gecko'/arch/relative,target,digest)
# DVD (dvd-plan.md): VLC 3.0.24 x64 (tools/stage-vlc.py) in C:\Program Files\VLC, about 56 MiB (W243); its
# shortcuts are make-start-menu.py's Programs/Multimedia. Not stripped (the loop below does not
# look in Program Files). plugins.dat is made on the console ("VLC plugin cache") and survives uploads.
vlc=json.loads((ROOT/'out/vlc/manifest.json').read_text())
if vlc['builder_sha256']!=sha(ROOT/'tools/stage-vlc.py'):raise SystemExit('VLC differs from its stager')
for relative,digest in vlc['files'].items():
    target=prefix/'drive_c/Program Files/VLC'/relative;target.parent.mkdir(parents=True,exist_ok=True)
    copy_verified(ROOT/'out/vlc/VLC'/relative,target,digest)
# W112: the hardware taskmgr (tools/build-taskmgr-hw.py: dead rows removed after End task,
# traced query failures) replaces the pinned one in both places.
taskmgr=json.loads((ROOT/'out/taskmgr-hw/manifest.json').read_text())
if taskmgr['builder_sha256']!=sha(ROOT/'tools/build-taskmgr-hw.py'):raise SystemExit('taskmgr differs from its builder')
for target in (data/'wine/lib/wine/x86_64-windows/taskmgr.exe',prefix/'drive_c/windows/system32/taskmgr.exe'):
    copy_verified(ROOT/'out/taskmgr-hw'/taskmgr['taskmgr']['path'],target,taskmgr['taskmgr']['sha256'])
# W182 (diagnosis): winecfg with timing markers on Apply (tools/build-winecfg-hw.py) replaces the
# pinned one in both places; W180's winecfg froze applying a theme.
winecfg=json.loads((ROOT/'out/winecfg-hw/manifest.json').read_text())
if winecfg['builder_sha256']!=sha(ROOT/'tools/build-winecfg-hw.py'):raise SystemExit('winecfg differs from its builder')
for target in (data/'wine/lib/wine/x86_64-windows/winecfg.exe',prefix/'drive_c/windows/system32/winecfg.exe'):
    copy_verified(ROOT/'out/winecfg-hw'/winecfg['winecfg']['path'],target,winecfg['winecfg']['sha256'])
# W174 (phase 8): the hardware nsi.dll (tools/build-nsi-hw.py): the network tables from libSceNetCtl
# when nsiproxy.sys cannot be opened. After the programs, whose import closure stages the pinned one.
nsi_hw=json.loads((ROOT/'out/nsi-hw/manifest.json').read_text())
if nsi_hw['builder_sha256']!=sha(ROOT/'tools/build-nsi-hw.py'):raise SystemExit('nsi differs from its builder')
for arch,windows in (('x86_64-windows','system32'),('i386-windows','syswow64')):
    for target in (data/'wine/lib/wine'/arch/'nsi.dll',prefix/'drive_c/windows'/windows/'nsi.dll'):
        copy_verified(ROOT/'out/nsi-hw'/nsi_hw['nsi'][arch]['path'],target,nsi_hw['nsi'][arch]['sha256'])
shutil.copyfile(prefix/'drive_c/windows/Fonts/tahoma.ttf',prefix/'drive_c/orbis/tahoma.ttf')
# W044: the hardware explorer (tools/build-explorer-hw.py: Start glyph, Run/Exit glyphs,
# clock) replaces the pinned one in every place Wine may load it from.
explorer=json.loads((ROOT/'out/explorer-hw/manifest.json').read_text())['explorer']
protocol_sha=sha(ROOT/'platform/ps4/pw_shell_open.h')
for proof in ('out/explorer-hw/manifest.json','out/wfm/manifest.json'):
    if json.loads((ROOT/proof).read_text()).get('open_protocol_sha256')!=protocol_sha:
        raise SystemExit('WFM/Explorer open protocol differs from compiled proof: '+proof)
for target in (data/'wine/lib/wine/x86_64-windows/explorer.exe',prefix/'drive_c/windows/explorer.exe',
               prefix/'drive_c/windows/system32/explorer.exe'):
    copy_verified(ROOT/'out/explorer-hw'/explorer['path'],target,explorer['sha256'])
# W058: WFM, the Winlator File Manager (tools/build-wfm.py), in system32 (alpha-1: without libcdio.dll).
wfm_files=json.loads((ROOT/'out/wfm/manifest.json').read_text())['files']
if 'libcdio.dll' in wfm_files:raise SystemExit('out/wfm still has libcdio.dll: rerun tools/build-wfm.py (alpha-1 licences)')
for name,e in wfm_files.items():
    if name.endswith(('.exe','.dll')):copy_verified(ROOT/'out/wfm'/e['path'],prefix/'drive_c/windows/system32'/name,e['sha256'])
# W112: DOSBox Pure PE64 guest; sources/license travel with the runtime, no game included.
dos=json.loads((ROOT/'out/wine-dos/manifest.json').read_text())
if dos['host_source_sha256']!=sha(ROOT/'native/doshost_win32.c') or dos['audio_abi_sha256']!=sha(ROOT/'platform/ps4/pw_dos_audio.h'):
    raise SystemExit('DOS runtime differs from its compiled source')
if json.loads((ROOT/'out/explorer-hw/manifest.json').read_text()).get('dos_classifier_sha256')!=sha(ROOT/'tools/explorer-dos.h'):
    raise SystemExit('Explorer DOS routing not compiled')
for name,e in dos['files'].items():
    copy_verified(ROOT/'out/wine-dos'/e['path'],prefix/'drive_c/windows/system32'/name,e['sha256'])
# W114: Start menu games (tools/build-games.py), programs and license notices in system32; no game data.
games=json.loads((ROOT/'out/games/manifest.json').read_text())
if games['builder_sha256']!=sha(ROOT/'tools/build-games.py'):raise SystemExit('games differ from their builder')
for name in games['system32']+games['notices']:
    copy_verified(ROOT/'out/games'/games['files'][name]['path'],prefix/'drive_c/windows/system32'/name,games['files'][name]['sha256'])
# W052: ntdll and kernelbase that run 64-bit GUI programs as guests of this process
# (tools/build-guest-hw.py), in the library directory and wherever the prefix has a copy.
for name,e in json.loads((ROOT/'out/guest-hw/manifest.json').read_text())['modules'].items():
    for target in (data/'wine/lib/wine/x86_64-windows'/name,prefix/'drive_c/windows/system32'/name):
        if target.parent.is_dir() and (target.exists() or target.parent.name=='x86_64-windows'):
            copy_verified(ROOT/'out/guest-hw'/e['path'],target,e['sha256'])
# W235 (pe32-en-explorer-plan.md P6): the i386 ntdll, kernelbase and ucrtbase of the guests of explorer's
# 32-bit world (tools/build-guest-hw.py), in wine/lib/wine/i386-guest only: ntdll Unix looks there first
# in a 64-bit process (tools/build-wow64-world-ps4.py); a relaunched 32-bit program keeps the stock ones.
guest32=json.loads((ROOT/'out/guest-hw-i386/manifest.json').read_text())
if guest32['builder_sha256']!=sha(ROOT/'tools/build-guest-hw.py'):raise SystemExit('i386 guest DLLs differ from their builder')
(data/'wine/lib/wine/i386-guest').mkdir(parents=True,exist_ok=True)
for name,e in guest32['modules'].items():
    copy_verified(ROOT/'out/guest-hw-i386'/e['path'],data/'wine/lib/wine/i386-guest'/name,e['sha256'])
# W071 (H2): Vulkan for Windows programs. winevulkan.dll and vulkan-1.dll are built unpatched
# as PE64 in the pinned host Wine tree (make dlls/<name>/x86_64-windows/<name>.dll); their
# Unix side is in the ELF (tools/build-winevulkan-ps4.py). vkprobe64.exe
# (fixtures/win32/vkprobe64.c) uses them as a Windows program does.
vulkan_files={}
for stem in ('winevulkan','vulkan-1'):
    source=ROOT/'.deps/wine/runtime/build/dlls'/stem/'x86_64-windows'/(stem+'.dll')
    vulkan_files[source.name]=sha(source)
    for target in (data/'wine/lib/wine/x86_64-windows'/source.name,prefix/'drive_c/windows/system32'/source.name):
        copy_verified(source,target,vulkan_files[source.name])
# W193: Unity players import winhttp (The Lost Forest's UnityPlayer.dll did not load without it)
# and load avrt for their audio threads; both are built unpatched in the host Wine tree.
# W194: winhttp imports jsproxy (proxy auto-config).
for stem in ('winhttp','jsproxy','avrt'):
    source=ROOT/'.deps/wine/runtime/build/dlls'/stem/'x86_64-windows'/(stem+'.dll')
    for target in (data/'wine/lib/wine/x86_64-windows'/source.name,prefix/'drive_c/windows/system32'/source.name):
        copy_verified(source,target,sha(source))
# W072 (H3): vkspin64.exe (fixtures/win32/vkspin64.c) draws through a swapchain into its window.
for name in ('vkprobe64.exe','vkspin64.exe','vklayers64.exe'):  # W091: vklayers64.exe (fixtures/win32/vklayers64.c) reports the loader's layers
    vulkan_files[name]=sha(ROOT/'out'/name)
    copy_verified(ROOT/'out'/name,prefix/'drive_c/orbis'/name,vulkan_files[name])
# W076 (H4): OpenGL. Mesa's WGL frontend with Zink (tools/vk-h0/build-mesa-zink.sh) as the
# native opengl32.dll in system32 (the runtime has no builtin opengl32), drawing through
# vulkan-1.dll; glxgears.exe (fixtures/win32/glxgears) to try it.
zink=pathlib.Path.home()/'vk-h0/build/mesa-zink/src/gallium/targets'
for source in (zink/'libgl-gdi/opengl32.dll',zink/'wgl/libgallium_wgl.dll'):
    vulkan_files[source.name]=sha(source)
    copy_verified(source,prefix/'drive_c/windows/system32'/source.name,vulkan_files[source.name])
# W262 (W261: Call of Duty found no pixel format and tried every mode): the same Mesa WGL/Zink for 32-bit programs
# (tools/vk-h0/build-mesa-zink-i386.sh) in syswow64. Wine's builtin opengl32 (W121, for wined3d) has no OpenGL driver
# behind it here (ps5drv implements none), so wglChoosePixelFormat found nothing. "opengl32"="native,builtin" below
# makes 32-bit programs, and wined3d, load this one; the 64-bit view has no builtin opengl32. About 21 MB.
zink32=pathlib.Path.home()/'vk-h0/build/mesa-zink-i386/src/gallium/targets'
for source in (zink32/'libgl-gdi/opengl32.dll',zink32/'wgl/libgallium_wgl.dll'):
    vulkan_files['i386:'+source.name]=sha(source)
    copy_verified(source,prefix/'drive_c/windows/syswow64'/source.name,vulkan_files['i386:'+source.name])
# W084: gltest64.exe (fixtures/win32/gltest64.c) draws one ring six ways, to see which loses geometry.
for name in ('glxgears.exe','gltest64.exe'):
    vulkan_files[name]=sha(ROOT/'out'/name)
    copy_verified(ROOT/'out'/name,prefix/'drive_c/orbis'/name,vulkan_files[name])
# W086: MangoHud for Vulkan and OpenGL (Zink) programs. The Khronos loader
# (tools/vk-h0/build-vulkan-loader.sh) is the native vulkan-1.dll in system32 (user.reg
# DllOverrides below), finds winevulkan through its manifest (as Wine's DllRegisterServer
# writes it, dlls/winevulkan/winevulkan.json) and loads MangoHud-Windows
# (tools/vk-h0/build-mangohud.sh) as an implicit layer, enabled by MANGOHUD=1 (launcher).
# MangoHud imports dxgi, d3dcompiler_47 and dwmapi; with wined3d for dxgi they are built
# unpatched in the host Wine tree like winevulkan. vkcube (Vulkan-Tools, build-vkcube.sh) in C:\orbis.
vk=pathlib.Path.home()/'vk-h0'
system32=prefix/'drive_c/windows/system32'
# W192: dxgi is the hardware variant (tools/build-dxgi-hw.py: DXVK devices get their swap chain
# through dxvk_dxgi.dll)
dxgi_hw=json.loads((ROOT/'out/dxgi-hw/manifest.json').read_text())
if dxgi_hw['builder_sha256']!=sha(ROOT/'tools/build-dxgi-hw.py'):raise SystemExit('dxgi differs from its builder')
for stem in ('dxgi','d3dcompiler_47','dwmapi','wined3d'):
    source=ROOT/'.deps/wine/runtime/build/dlls'/stem/'x86_64-windows'/(stem+'.dll')
    if stem=='dxgi':source=ROOT/'out/dxgi-hw'/dxgi_hw['dxgi']['path']
    vulkan_files[source.name]=sha(source)
    for target in (data/'wine/lib/wine/x86_64-windows'/source.name,system32/source.name):
        if target==system32/'dxgi.dll':continue  # W190: system32 holds DXVK's (see the DXVK block)
        copy_verified(source,target,vulkan_files[source.name])
for source,target in ((vk/'build/vk-loader/loader/vulkan-1.dll',system32/'vulkan-1.dll'),
                      (vk/'build/mangohud/src/libMangoHud.dll',system32/'libMangoHud.dll'),
                      (vk/'build/vk-tools/cube/vkcube.exe',prefix/'drive_c/orbis/vkcube.exe')):
    vulkan_files[target.name]=sha(source)
    copy_verified(source,target,vulkan_files[target.name])
(system32/'winevulkan.json').write_text((ROOT/'.deps/wine/source/dlls/winevulkan/winevulkan.json').read_text())
layer=json.loads((vk/'build/mangohud/src/MangoHud.x86_64.json').read_text())
layer['layer']['library_path']='.\\libMangoHud.dll'
(system32/'MangoHud.x86_64.json').write_text(json.dumps(layer,indent=4)+'\n')
# W245: the same for 32-bit programs (explorer's WoW64 world, relaunched PE32 titles). Wine's builtin vulkan-1
# loads no layers: syswow64 gets the Khronos loader (tools/vk-h0/build-vulkan-loader-i386.sh, v1.4.335 as the
# x64 one; "vulkan-1"="native,builtin" since W124 makes 32-bit programs take it) and MangoHud's i386 layer
# (tools/vk-h0/build-mangohud-i386.sh, W086's patched tree) with its i386 imports; Wow6432Node below.
wow64_dir=prefix/'drive_c/windows/syswow64'
loader32=json.loads((vk/'build/vk-loader-i386/orbis-build.json').read_text())
hud32=json.loads((vk/'build/mangohud-i386/orbis-build.json').read_text())
for name,digest in hud32['sources'].items():
    if sha(vk/'src/mangohud-win-i386'/name)!=digest:raise SystemExit('MangoHud i386 source changed since compilation: '+name)
for source,digest in ((vk/'build/vk-loader-i386/loader/vulkan-1.dll',loader32['dll_sha256']),
                      (vk/'build/mangohud-i386/src/libMangoHud.dll',hud32['dll_sha256'])):
    vulkan_files['i386:'+source.name]=digest
    copy_verified(source,wow64_dir/source.name,digest)
for stem in ('d3dcompiler_47','dwmapi'):
    source=ROOT/'.deps/wine/runtime/build/dlls'/stem/'i386-windows'/(stem+'.dll')
    vulkan_files['i386:'+source.name]=sha(source)
    for target in (data/'wine/lib/wine/i386-windows'/source.name,wow64_dir/source.name):
        copy_verified(source,target,vulkan_files['i386:'+source.name])
(wow64_dir/'winevulkan.json').write_text((ROOT/'.deps/wine/source/dlls/winevulkan/winevulkan.json').read_text())
layer32=json.loads((vk/'build/mangohud-i386/src/MangoHud.x86.json').read_text())
layer32['layer']['library_path']='.\\libMangoHud.dll'
(wow64_dir/'MangoHud.x86.json').write_text(json.dumps(layer32,indent=4)+'\n')
# W248 (W247: Vice City's 32-bit loader never loaded libMangoHud.dll): the 32-bit loader in explorer's world reads
# the 64-bit registry view (redirection to Wow6432Node follows the process being WoW64; explorer's is 64-bit), so
# it looks for system32\MangoHud.x86_64.json, which the system32->syswow64 redirection makes this file; it took its
# ICD the same way (system32\winevulkan.json, its .\winevulkan.dll loaded from syswow64). The Wow6432Node keys stay
# for a 32-bit process (a relaunched title).
(wow64_dir/'MangoHud.x86_64.json').write_text(json.dumps(layer32,indent=4)+'\n')
system_reg=prefix/'system.reg';system_text=system_reg.read_text()
if '[Software\\\\Khronos\\\\Vulkan' in system_text or '[Software\\\\Wow6432Node\\\\Khronos\\\\Vulkan' in system_text:
    raise SystemExit('system.reg already has Khronos keys')
system_text+=('\n[Software\\\\Khronos\\\\Vulkan\\\\Drivers] 1793390636\n#time=1dd68a9cb52bf36\n'
              '"C:\\\\windows\\\\system32\\\\winevulkan.json"=dword:00000000\n'
              '\n[Software\\\\Khronos\\\\Vulkan\\\\ImplicitLayers] 1793390636\n#time=1dd68a9cb52bf36\n'
              '"C:\\\\windows\\\\system32\\\\MangoHud.x86_64.json"=dword:%08x\n' % (0 if mangohud_enabled else 1))
# W245: the i386 loader reads the 32-bit view
system_text+=('\n[Software\\\\Wow6432Node\\\\Khronos\\\\Vulkan\\\\Drivers] 1793390636\n#time=1dd68a9cb52bf36\n'
              '"C:\\\\windows\\\\syswow64\\\\winevulkan.json"=dword:00000000\n'
              '\n[Software\\\\Wow6432Node\\\\Khronos\\\\Vulkan\\\\ImplicitLayers] 1793390636\n#time=1dd68a9cb52bf36\n'
              '"C:\\\\windows\\\\syswow64\\\\MangoHud.x86.json"=dword:%08x\n' % (0 if mangohud_enabled else 1))
# W112: the pinned Wine maps HKCR to Machine\\Software\\Classes, without
# merging the user's Classes key. ShellExecute must see these real associations.
for key,value in [('Software\\Classes\\OrbisDesk.Text\\shell\\open\\command',
                   '"C:\\windows\\system32\\notepad.exe" "%1"')]+[
        ('Software\\Classes\\'+ext,'OrbisDesk.Text')
        for ext in ('.txt','.log','.ini','.cfg','.conf','.json','.md','.csv','.xml')]:
    escaped=key.replace('\\','\\\\')
    if '['+escaped+']' in system_text:
        # Preserve existing Wine associations, e.g. .ini -> inifile -> Notepad.
        if key.rsplit('\\',1)[-1].startswith('.'):continue
        raise SystemExit('text association class already exists: '+key)
    system_text+='\n['+escaped+']\n@='+json.dumps(value)+'\n'
# W121: COM classes of the audio DLLs added in W120, as their DllRegisterServer would write them
# (dlls/mmdevapi/mmdevapi_classes.idl, dlls/dsound/dsound_classes.idl). The sealed prefix was
# made before those DLLs existed: winmm found no MMDeviceEnumerator ("class {bcde0395-...} not
# registered", W120: waveOutGetNumDevs 0, waveOutOpen MMSYSERR_NODRIVER). Both registry views:
# the 64-bit one and Wow6432Node for 32-bit programs (system32 is syswow64 for those).
AUDIO_CLASSES={'{BCDE0395-E52F-467C-8E3D-C4579291692E}':('mmdevapi.dll','MMDeviceEnumerator class'),
               '{47D4D946-62E8-11CF-93BC-444553540000}':('dsound.dll','DirectSound Object'),
               '{3901CC3F-84B5-4FA4-BA35-AA8172B8A09B}':('dsound.dll','DirectSound 8.0 Object'),
               '{B2F586D4-5558-49D1-A07B-3249DBBB33C2}':('dsound.dll','DirectSoundBufferConfig Object'),
               '{B0210780-89CD-11D0-AF08-00A0C925CD16}':('dsound.dll','DirectSoundCapture Object'),
               '{E4BCAC13-7F99-4908-9A8E-74E3BF24B6E1}':('dsound.dll','DirectSoundCapture 8.0 Object'),
               '{FEA4300C-7959-4147-B26A-2377B9E7A91D}':('dsound.dll','DirectSoundFullDuplex Object')}
for view in ('Software\\\\Classes\\\\CLSID','Software\\\\Classes\\\\Wow6432Node\\\\CLSID'):
    for clsid,(dll,description) in AUDIO_CLASSES.items():
        key=view+'\\\\'+clsid
        if '['+key+']' in system_text:raise SystemExit('system.reg already has '+key)
        system_text+=('\n['+key+'] 1793390636\n#time=1dd68a9cb52bf36\n@='+json.dumps(description)+'\n'
                      '\n['+key+'\\\\InprocServer32] 1793390636\n#time=1dd68a9cb52bf36\n'
                      '@="C:\\\\windows\\\\system32\\\\'+dll+'"\n"ThreadingModel"="Both"\n')
# W138: DirectMusic's classes for 32-bit programs (the i386 DLLs staged above), taken from the
# pinned Wine source's .idl files: SuperMarioKart.exe plays its MIDI music through
# CLSID_DirectMusicPerformance, which was not registered (W137).
import re
for dll in ('dmband','dmcompos','dmime','dmloader','dmscript','dmstyle','dmsynth','dmusic','dswave'):
    if dll+'.dll' not in wow32['modules'] and dll+'.dll' not in dmsynth['modules']:raise SystemExit(dll+' is not staged for i386')
    idl=(ROOT/'.deps/wine/source/dlls'/dll/(dll+'.idl')).read_text()
    classes=re.findall(r'uuid\(([0-9a-fA-F-]{36})\)\s*\]\s*coclass\s+(\w+)',idl)
    if not classes:raise SystemExit('no coclass in '+dll+'.idl')
    for uuid,name in classes:
        key='Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{'+uuid.upper()+'}'
        if '['+key+']' in system_text:raise SystemExit('system.reg already has '+key)
        system_text+=('\n['+key+'] 1793390636\n#time=1dd68a9cb52bf36\n@='+json.dumps(name)+'\n'
                      '\n['+key+'\\\\InprocServer32] 1793390636\n#time=1dd68a9cb52bf36\n'
                      '@="C:\\\\windows\\\\system32\\\\'+dll+'.dll"\n"ThreadingModel"="Both"\n')
# W138: the General MIDI bank DirectMusic's default collection loads (dmloader reads
# HKLM\Software\Microsoft\DirectMusic GMFilePath; Wine ships none). GeneralUser GS v2.0.3 by
# S. Christian Collins (its LICENSE.txt allows use and redistribution), pinned to the commit
# 684543d5e5efaef08d02be50dcda8d552478fa60 of github.com/mrbumpy409/GeneralUser-GS.
SOUNDFONT=ROOT/'.deps/downloads/generaluser-gs-2.0.3'
for name,digest in (('GeneralUser-GS.sf2','9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe'),
                    ('LICENSE.txt','7b32efefdf95ce38a043799f0659853ddc00fbaa14d8c50f0aca16b9b8b405be')):
    copy_verified(SOUNDFONT/name,prefix/'drive_c/windows'/('GeneralUser-GS.sf2' if name.endswith('.sf2') else 'GeneralUser-GS-LICENSE.txt'),digest)
# The sealed prefix names C:\windows\system32\drivers\gm.dls, which it does not have.
gm_old='"GMFilePath"="C:\\\\windows\\\\system32\\\\drivers\\\\gm.dls"'
if system_text.count(gm_old)!=2:raise SystemExit('system.reg: expected GMFilePath in both views')
system_text=system_text.replace(gm_old,'"GMFilePath"="C:\\\\windows\\\\GeneralUser-GS.sf2"')
# W177 (phase 9): GeckoPath for 64- and 32-bit programs (a 32-bit program sees syswow64 as system32).
# Without it mshtml starts "control.exe appwiz.cpl install_gecko" in a new process (nsembed.c).
# W262 (W261: Prince of Persia's launcher runs a DirectX version test): HKLM\Software\Microsoft\DirectX as wine.inf's
# [DirectX] section writes it (DirectX 9.0c), in both views; the sealed prefix's registry has neither.
for view in ('Software\\\\Microsoft\\\\DirectX','Software\\\\Wow6432Node\\\\Microsoft\\\\DirectX'):
    # the sealed registry already has both (W262's console check), with these values: keep them
    if '['+view+']' in system_text:continue
    system_text+=('\n['+view+'] 1793390636\n#time=1dd68a9cb52bf36\n'
                  '"InstalledVersion"=hex:00,00,00,09,00,00,00,00\n"Version"="4.09.00.0904"\n')
for view,arch in (('Software\\\\Wine\\\\MSHTML\\\\2.47.4','x86_64'),('Software\\\\Wow6432Node\\\\Wine\\\\MSHTML\\\\2.47.4','x86')):
    if '['+view+']' in system_text:raise SystemExit('system.reg already has '+view)
    system_text+=('\n['+view+'] 1793390636\n#time=1dd68a9cb52bf36\n'
                  '"GeckoPath"="C:\\\\windows\\\\system32\\\\gecko\\\\2.47.4\\\\wine-gecko-2.47.4-'+arch+'"\n')
# W261: the COM registration of the modules above and of avifil32 (W260), both views (tools/stage-wine-i386.py);
# before MSHTML's and DirectShow's, whose sections come later and so keep their values where both register a key
wow32_reg=ROOT/'out/wine-i386'/wow32['registry']['path']
if sha(wow32_reg)!=wow32['registry']['sha256']:raise SystemExit('W261 registry differs from its manifest')
system_text+=wow32_reg.read_text()
# W177 (phase 9): MSHTML's COM registration in both views (tools/stage-mshtml-hw.py, system.reg.add)
mshtml_reg=ROOT/'out/mshtml-hw'/mshtml['registry']['path']
if sha(mshtml_reg)!=mshtml['registry']['sha256']:raise SystemExit('MSHTML registry differs from its manifest')
system_text+=mshtml_reg.read_text()
# W225: DirectShow's registration for 32-bit programs (tools/stage-dshow-i386.py, system.reg.add)
dshow_reg=ROOT/'out/dshow-i386'/dshow['registry']['path']
if sha(dshow_reg)!=dshow['registry']['sha256']:raise SystemExit('DirectShow registry differs from its manifest')
system_text+=dshow_reg.read_text()
# alpha-1: the build PC's name out of the shipped registry (the prefix was made on the host)
for old,new in (('"ComputerName"="JCASELLA"','"ComputerName"="ORBISDESK"'),('"Hostname"="jcasella"','"Hostname"="orbisdesk"')):
    if old not in system_text:raise SystemExit('system.reg: expected '+old)
    system_text=system_text.replace(old,new)
system_text=orbis_profile(system_text,'system.reg')
system_reg.write_text(system_text)
# W226: the same registry as a file Wine never rewrites; the launcher appends the keys the console's
# system.reg lacks before Wine starts (native/wine_hardware.c merge_system_reg). W225's keys were lost
# when a Wine started during the upload saved its old registry over the uploaded system.reg.
(prefix/'system.reg.build').write_text(system_text)
# W044: desktop wallpaper (tools/make-wallpaper.py), read by explorer at start from the
# registry, and full-window dragging, now that the compositor moves windows without a repaint.
# W170: a CC0 photograph instead (out/wallpaper-cc0, source and conversion in its manifest), same
# name and format, so the registry and ps5drv's WINE_PS5_WALLPAPER stay as they are.
wallpaper=json.loads((ROOT/'out/wallpaper-cc0/manifest.json').read_text())['wallpaper']
copy_verified(ROOT/'out/wallpaper-cc0'/wallpaper['path'],prefix/'drive_c/windows/orbis-hills.bmp',wallpaper['sha256'])
# W292: more wallpapers to choose from (the desktop's right-click menu > Wallpaper lists the BMPs in
# C:\windows), drawn by tools/make-wallpaper-set.py; the default stays orbis-hills.bmp.
wallpaper_set=json.loads((ROOT/'out/wallpaper-set/manifest.json').read_text())
for item in wallpaper_set['wallpapers']:
    copy_verified(ROOT/'out/wallpaper-set'/item['path'],prefix/'drive_c/windows'/item['path'],item['sha256'])
user_reg=prefix/'user.reg';text=user_reg.read_text()
for old,new in (('"Wallpaper"=""','"Wallpaper"="C:\\\\windows\\\\orbis-hills.bmp"'),('"DragFullWindows"="0"','"DragFullWindows"="1"')):
    if text.count(old)!=1:raise SystemExit('user.reg: unexpected '+old)
    text=text.replace(old,new)
# W086: the Khronos loader in system32 instead of Wine's builtin vulkan-1 (see above)
overrides=text.index('[Software\\\\Wine\\\\DllOverrides]');overrides=text.index('\n',text.index('#time=',overrides))+1
# W124: native,builtin: 32-bit programs have no native vulkan-1 (the syswow64 one is Wine's builtin,
# which "native" alone would refuse); 64-bit ones still get the Khronos loader in system32.
text=text[:overrides]+'"vulkan-1"="native,builtin"\n'+text[overrides:]
# W124: Direct3D 8-11 through DXVK (staged above), for 32- and 64-bit programs
text=text[:overrides]+''.join('"%s"="native,builtin"\n'%name for name in ('d3d10core','d3d11','d3d8','d3d9'))+text[overrides:]
# W262 set "opengl32"="native,builtin" (Mesa's opengl32 with Zink for 32-bit programs); W263 takes it out:
# every 32-bit program that loaded the i386 Mesa (wined3d imports opengl32) ended the title (CE-34878). The Mesa
# files stay in syswow64; Wine's builtin opengl32 is preferred again, as in W261.
# W172: DXVK's dxgi for 32-bit programs, and since W190 for 64-bit titles that run alone; explorer
# and its guests keep Wine's builtin (explorer.exe block below; see the DXVK block).
# A program can choose otherwise in winecfg (HKCU\Software\Wine\AppDefaults, kept by upload-hardware.py).
text=text[:overrides]+'"dxgi"="native,builtin"\n'+text[overrides:]
# W120: mmdevapi's audio driver is the console's (tools/build-audio-ps4.py, "wineps4.drv");
# its default list (pulse, alsa, oss, coreaudio) has none that exists here.
if '[Software\\\\Wine\\\\Drivers]' in text:raise SystemExit('user.reg: unexpected Drivers key')
text+='\n[Software\\\\Wine\\\\Drivers] 1793390636\n#time=1dd68a9cb52bf36\n"Audio"="ps4"\n'
# W207 (phase 9): no AppDefaults\palemoon.exe. Pale Moon runs as a guest of explorer, without
# restarting the title (the user's choice, W205; W183-W204 relaunched it with OrbisRunsAlone="Y").
# A guest runs under explorer.exe's AppDefaults, so palemoon.exe's DllOverrides (W184) never applied.
# W190: explorer and every 64-bit guest in its process keep Wine's builtin dxgi (the Khronos
# loader, MangoHud, Gecko's adapter query); system32\dxgi.dll is DXVK's (see the DXVK block).
if '[Software\\\\Wine\\\\AppDefaults\\\\explorer.exe\\\\DllOverrides]' in text:raise SystemExit('user.reg: unexpected explorer.exe DllOverrides')
text+='\n[Software\\\\Wine\\\\AppDefaults\\\\explorer.exe\\\\DllOverrides] 1793390636\n#time=1dd68a9cb52bf36\n"dxgi"="builtin"\n'
# W190: the 64-bit Direct3D 11 test needs DXVK's dxgi, which only a title running alone gets.
if '[Software\\\\Wine\\\\AppDefaults\\\\d3d11test64.exe]' in text:raise SystemExit('user.reg: unexpected d3d11test64.exe AppDefaults')
text+='\n[Software\\\\Wine\\\\AppDefaults\\\\d3d11test64.exe] 1793390636\n#time=1dd68a9cb52bf36\n"OrbisRunsAlone"="Y"\n'
# W045: a dark scheme through the system colours (the prefix's Colors key is empty, so Wine
# used its classic grey). Light text on every dark face: buttons and taskbar, menus,
# captions, windows, tooltips; blue selection with white text.
DARK={'ActiveBorder':'45 45 48','ActiveTitle':'0 90 158','AppWorkspace':'30 30 30','Background':'0 0 0',
      'ButtonAlternateFace':'45 45 48','ButtonDkShadow':'10 10 10','ButtonFace':'45 45 48','ButtonHilight':'90 90 95',
      'ButtonLight':'70 70 74','ButtonShadow':'25 25 28','ButtonText':'235 235 235','GradientActiveTitle':'0 120 215',
      'GradientInactiveTitle':'70 70 74','GrayText':'140 140 140','Hilight':'0 120 215','HilightText':'255 255 255',
      'HotTrackingColor':'80 160 255','InactiveBorder':'45 45 48','InactiveTitle':'60 60 64','InactiveTitleText':'190 190 190',
      'InfoText':'235 235 235','InfoWindow':'50 50 54','Menu':'38 38 40','MenuBar':'38 38 40','MenuHilight':'0 120 215',
      'MenuText':'235 235 235','Scrollbar':'55 55 58','TitleText':'255 255 255','Window':'30 30 30',
      'WindowFrame':'10 10 10','WindowText':'235 235 235'}
colours=text.index('[Control Panel\\\\Colors]');colours=text.index('\n',text.index('#time=',colours))+1
if not text[colours:].startswith('\n'):raise SystemExit('user.reg: Colors key is not empty')
text=text[:colours]+''.join('"%s"="%s"\n'%item for item in sorted(DARK.items()))+text[colours:]
# W175: the dark scheme above and a light one (Windows 10's default colours) as .theme files in
# resources\themes; winecfg's Desktop Integration applies one with "Install theme..."
# (programs/winecfg/theme.c, do_parse_theme reads its [Control Panel\Colors]). After the first
# install the console keeps the user's colours (upload-hardware.py); a build that must change them
# lists 'control panel\\colors' in manifest['user_reg_reset'].
LIGHT={'ActiveBorder':'180 180 180','ActiveTitle':'153 180 209','AppWorkspace':'171 171 171','Background':'0 0 0',
       'ButtonAlternateFace':'0 0 0','ButtonDkShadow':'105 105 105','ButtonFace':'240 240 240','ButtonHilight':'255 255 255',
       'ButtonLight':'227 227 227','ButtonShadow':'160 160 160','ButtonText':'0 0 0','GradientActiveTitle':'185 209 234',
       'GradientInactiveTitle':'215 228 242','GrayText':'109 109 109','Hilight':'0 120 215','HilightText':'255 255 255',
       'HotTrackingColor':'0 102 204','InactiveBorder':'244 247 252','InactiveTitle':'191 205 219','InactiveTitleText':'0 0 0',
       'InfoText':'0 0 0','InfoWindow':'255 255 225','Menu':'240 240 240','MenuBar':'240 240 240','MenuHilight':'0 120 215',
       'MenuText':'0 0 0','Scrollbar':'200 200 200','TitleText':'0 0 0','Window':'255 255 255',
       'WindowFrame':'100 100 100','WindowText':'0 0 0'}
if set(LIGHT)!=set(DARK):raise SystemExit('light and dark schemes name different colours')
themes=prefix/'drive_c/windows/resources/themes';themes.mkdir(parents=True,exist_ok=True)
for name,scheme in (('Orbis Oscuro',DARK),('Orbis Claro',LIGHT)):
    (themes/(name+'.theme')).write_bytes(('[Theme]\r\nDisplayName=%s\r\n\r\n[Control Panel\\Colors]\r\n'%name+
        ''.join('%s=%s\r\n'%item for item in sorted(scheme.items()))).encode('ascii'))
# W177: no visual style by default: Aero felt slower on the console (W175). The sealed prefix names
# Aero as active in ThemeManager, which W175's aero.msstyles made effective.
theme=text.index('[Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\ThemeManager]')
end=text.index('\n\n',theme)
if text[theme:end].count('"ThemeActive"="1"')!=1:raise SystemExit('user.reg: ThemeManager is not as expected')
text=text[:theme]+text[theme:end].replace('"ThemeActive"="1"','"ThemeActive"="0"')+text[end:]
for old,new in (('"LOGONSERVER"="\\\\\\\\JCASELLA"','"LOGONSERVER"="\\\\\\\\ORBISDESK"'),('"USERDOMAIN"="JCASELLA"','"USERDOMAIN"="ORBISDESK"')):
    if old not in text:raise SystemExit('user.reg: expected '+old)
    text=text.replace(old,new)
text=orbis_profile(text,'user.reg')
user_reg.write_text(text)
# W048: Wine runs on hardware as user "orbis" (native/wine_boot.c), but the prefix was made
# on the host for another user, so C:\users\orbis (the user's Start menu, AppData) did
# not exist. The host profile is directories only; the same tree is made for orbis.
profiles=host_profiles
for folder in sorted(p for p in profiles[0].rglob('*') if p.is_dir()):
    (prefix/'drive_c/users/orbis'/folder.relative_to(profiles[0])).mkdir(parents=True,exist_ok=True)
# A runtime left by a build before alpha-1 can hold the MangoHud config that went there (now in orbis'
# profile, below); permit only that file; still reject other profile data.
generated_config=profiles[0]/'AppData/Roaming/MangoHud/MangoHud.conf'
if any(p.is_file() and p!=generated_config for p in profiles[0].rglob('*')):
    raise SystemExit('prefix: host profile has files; copy them too')
# alpha-1: the host profile is not shipped (the registry names C:\users\orbis, above)
shutil.rmtree(profiles[0])
# W045: Start menu folders and shortcuts (tools/make-start-menu.py) in the common Start menu.
start_menu=json.loads((ROOT/'out/start-menu/manifest.json').read_text())
for name,e in start_menu['shortcuts'].items():
    copy_target=prefix/'drive_c/ProgramData/Microsoft/Windows/Start Menu'/name;copy_target.parent.mkdir(parents=True,exist_ok=True)
    copy_verified(ROOT/'out/start-menu'/name,copy_target,e['sha256'])
# W168: the Desktop folders were empty, so explorer had no launchers to show; the user wants only
# the File Manager shortcut there. W169: in the user's own Desktop (C:\users\orbis\Desktop,
# FOLDERID_Desktop) rather than the common one: WFM's Desktop opens that folder, and what the
# user puts there shows on the desktop too (explorer reads both).
for name in ('Programs/Accessories/File Manager.lnk',):
    copy_verified(ROOT/'out/start-menu'/name,prefix/'drive_c/users/orbis/Desktop'/pathlib.PurePosixPath(name).name,
                  start_menu['shortcuts'][name]['sha256'])
# The Steam client: C:\orbis\steam (CA bundle, gbe_fork's DLLs with their licence and source note),
# C:\orbis\steam-open.exe (the Start menu item's and Desktop link's request) and the Desktop link
for name,digest in steam_build['prefix_files'].items():
    steam_target=prefix/'drive_c'/name;steam_target.parent.mkdir(parents=True,exist_ok=True)
    copy_verified(ROOT/'build/steam-hosted/prefix'/name,steam_target,digest)
# alpha-1 (docs/RELEASE_LICENSES.md): the licence texts, the copyright notices MIT/BSD/zlib ask
# for (LICENSES/NOTICE.txt), THIRD_PARTY.md and where to get the corresponding source, in C:\orbis\licenses.
SOURCE_REPOSITORY='https://github.com/jl-casella/OrbisDesk'
licenses=prefix/'drive_c/orbis/licenses';licenses.mkdir(parents=True,exist_ok=True)
license_inputs=sorted((ROOT/'LICENSES').glob('*.txt'))+[ROOT/'THIRD_PARTY.md']
if not any(p.name=='NOTICE.txt' for p in license_inputs):raise SystemExit('LICENSES/NOTICE.txt is missing')
for source in license_inputs:shutil.copyfile(source,licenses/source.name)
head=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
dirty=bool(subprocess.run(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],
                          capture_output=True,text=True,check=True).stdout.strip())
(licenses/'SOURCE.txt').write_text(
    'OrbisDesk W302 ('+args.app_version+'): corresponding source\r\n\r\n'
    'OrbisDesk is free software under the GNU GPL version 3 or later (GPL-3.0.txt).\r\n'
    'Source code: '+SOURCE_REPOSITORY+', tag orbisdesk-'+args.app_version+' (commit '+head+(' plus local changes' if dirty else '')+').\r\n'
    'Third-party sources (Wine, Mesa, VLC, Wine Gecko, DOSBox Pure, gbe_fork, curl, Mbed TLS and others)\r\n'
    'are attached to the same release as orbisdesk-'+args.app_version+'-third-party-sources, listed with their SHA-256 in\r\n'
    'THIRD_PARTY.md. For three years from the release date the same sources are also available on request\r\n'
    'through the repository\'s issue tracker.\r\n')
manifest_licenses={p.name:sha(p) for p in sorted(licenses.iterdir())}
# Phase 9: the SeaMonkey profile the Start menu shortcut passes with -profile (fixtures/browser).
# SeaMonkey 2.53 is the browser (the user's choice; W177-W215 staged two Pale Moon profiles, whose
# user.js on the console are obsolete_files below). SeaMonkey itself is the user's own copy, not in
# the package. Only user.js is the build's (each upload replaces it); what SeaMonkey writes in the
# profile (prefs.js, history, bookmarks) is not in the build and survives uploads.
seamonkey_profile=prefix/'drive_c/users/orbis/AppData/Roaming/Mozilla/SeaMonkey/Profiles/orbis'
seamonkey_profile.mkdir(parents=True,exist_ok=True)
(seamonkey_profile/'user.js').write_text((ROOT/'fixtures/browser/seamonkey-user.js').read_text())
# W090: the Graphics Tools shortcuts' icons (tools/make-icons.py) and the MangoHud settings that
# its "MangoHud Config" shortcut opens (%APPDATA%\MangoHud\MangoHud.conf, MangoHud's own path).
icons=json.loads((ROOT/'out/icons/manifest.json').read_text())['icons']
(prefix/'drive_c/orbis/icons').mkdir(exist_ok=True)
for name,digest in icons.items():copy_verified(ROOT/'out/icons'/name,prefix/'drive_c/orbis/icons'/name,digest)
# W092: %APPDATA% follows the registry's shell folders; since alpha-1 they name C:\users\orbis (above),
# as tools/make-start-menu.py's "MangoHud Config" shortcut does
mangohud_conf=prefix/'drive_c/users/orbis/AppData/Roaming/MangoHud/MangoHud.conf'
mangohud_conf.parent.mkdir(parents=True,exist_ok=True)
mangohud_conf.write_text('# MangoHud settings (OrbisDesk). Save and restart OrbisDesk to apply.\n'
                         '# Options: https://github.com/flightlessmango/MangoHud#hud-configuration\n'
                         'fps\nframetime\nframe_timing=1\ncpu_stats\ngpu_stats\nram\nposition=top-left\n')
# W284 (W281: NFS U2's second start had no music: its timer outlived the program and killed winmm's timer thread):
# winmm.dll that removes a timer whose function is gone or faults (tools/build-winmm-hw.py). After every other
# staging, so it replaces the host copies in the builtin folders and the prefix.
winmm_hw=json.loads((ROOT/'out/winmm-hw/manifest.json').read_text())
if winmm_hw['builder_sha256']!=sha(ROOT/'tools/build-winmm-hw.py'):raise SystemExit('winmm differs from its builder')
for arch,windows in (('i386-windows','syswow64'),('x86_64-windows','system32')):
    e=winmm_hw['modules'][arch]
    for target in (data/'wine/lib/wine'/arch/'winmm.dll',prefix/'drive_c/windows'/windows/'winmm.dll'):
        copy_verified(ROOT/'out/winmm-hw'/e['path'],target,e['sha256'])
# W095: debug information out of the 64-bit PE modules. The title cannot map files, so Wine
# reads every image whole into memory, its .debug_* sections included, and all programs share
# explorer's process: in W094 the title ended (no signal, the log cut short) while glxgears
# loaded Mesa's DLLs, after vkcube and vkspin64 with MangoHud. --strip-debug brings the 64-bit
# modules from about 332 MiB to 158 MiB; Wine's builtin marker stays. A module llvm-strip
# refuses (e.g. the guest ntdll and kernelbase: "unexpected associative section index") is
# kept as it is.
stripped={'modules':0,'bytes_before':0,'bytes_after':0,'kept':[]}
# W120: also the i386 modules (W119 added ~100 MiB of PE32 debug information with wined3d).
for folder in (data/'wine/lib/wine/x86_64-windows',prefix/'drive_c/windows/system32',prefix/'drive_c/orbis',
               data/'wine/lib/wine/i386-windows',prefix/'drive_c/windows/syswow64'):
    for module in sorted(folder.iterdir()):
        if module.suffix.lower() not in ('.dll','.exe','.drv','.sys') or not module.is_file():continue
        if module.read_bytes()[:2]!=b'MZ':continue
        before=module.stat().st_size;temporary=module.with_name(module.name+'.stripped')
        result=subprocess.run(['llvm-strip-19','--strip-debug','-o',str(temporary),str(module)],capture_output=True,text=True)
        if result.returncode:
            temporary.unlink(missing_ok=True);stripped['kept'].append(str(module.relative_to(data)));continue
        temporary.replace(module)
        stripped['modules']+=1;stripped['bytes_before']+=before;stripped['bytes_after']+=module.stat().st_size
print(json.dumps({'stripped_modules':stripped['modules'],'mib_before':stripped['bytes_before']>>20,
                  'mib_after':stripped['bytes_after']>>20,'kept':len(stripped['kept'])}))
# W170: the console keeps /data/wine-prefix between builds and the upload only adds files, so a
# file a build stops shipping stays. W168's shortcut in the common Desktop showed File Manager
# twice next to W169's one in the user's Desktop. upload-hardware.py deletes these paths.
obsolete_files=['wine-prefix/drive_c/users/Public/Desktop/File Manager.lnk',
    # W179 (phase 9): iexplore cannot run in one process (it registers a local COM server, which
    # needs rpcss); W177 shipped its Start menu shortcut, which W179 no longer makes.
    'wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Internet/Internet Explorer.lnk',
    # W179: Wine Configuration moved from System Tools to Control Panel (winecfg.cpl)
    'wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/System Tools/Wine Configuration.lnk',
    # Phase 9: Pale Moon is no longer the browser (the user's choice; SeaMonkey replaces it): its
    # shortcuts, their icon and the user.js of the two profiles the build staged (W177-W215). The
    # rest of those profiles and the program folder are the user's (Pale Moon wrote them).
    'wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Internet/Pale Moon.lnk',
    'wine-prefix/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Internet/Pale Moon (no JIT).lnk',
    'wine-prefix/drive_c/orbis/icons/palemoon.ico',
    'wine-prefix/drive_c/users/orbis/AppData/Roaming/Moonchild Productions/Pale Moon/Profiles/orbis/user.js',
    'wine-prefix/drive_c/users/orbis/AppData/Roaming/Moonchild Productions/Pale Moon/Profiles/orbis-nojit/user.js']
# W243: the VLC plugins stage-vlc.py leaves out. W241 shipped 290 and VLC loads whatever is in its
# plugins folder (W241 ran out of descriptors), so the console's copies go too.
obsolete_files+=['wine-prefix/drive_c/Program Files/VLC/'+name for name in vlc['left_out_plugins']]
# alpha-1 licences: libcdio.dll (GPL-3.0, prebuilt, no known source) is no longer shipped; builds since W058
# put it in system32, so the console's copy goes too.
obsolete_files.append('wine-prefix/drive_c/windows/system32/libcdio.dll')
# The runtime's inventory (also the manifest's, below) and what the console must drop
runtime_directories=[p.relative_to(data).as_posix() for p in sorted(data.rglob('*')) if p.is_dir()]
runtime_files={p.relative_to(data).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(data.rglob('*')) if p.is_file()}
for path in obsolete_files:
    if not path.startswith('wine-prefix/') or '..' in path.split('/') or path in runtime_files:
        raise SystemExit('obsolete file must be an unshipped wine-prefix path: '+path)
user_reg_reset=[]   # CONSOLE_OWNED keys this build takes from its own user.reg once (tools/console_state.py)
# alpha-1: the runtime travels inside OrbisDesk.pkg as /app0/runtime, and the launcher installs it into
# /data on the first start of each build (native/hw_install.c), with install.json as its contract:
# the same rules tools/upload-hardware.py applies over FTP. --runtime-outside-package keeps the old
# split (a 35 MB package and an FTP-uploaded runtime) for quick development builds.
from console_state import CONSOLE_OWNED
install={'schema_version':1,'build':HW_BUILD_ID,'app_version':args.app_version,'state_root':'/data/orbisdesk',
    'writable':['wine-prefix','wine-home'],'directories':runtime_directories,
    'files':[[path,e['sha256'],e['bytes']] for path,e in runtime_files.items()],
    'obsolete_files':obsolete_files,'console_owned':list(CONSOLE_OWNED),'user_reg_reset':user_reg_reset,
    'host_profile':host_profiles[0].name,'bytes':sum(e['bytes'] for e in runtime_files.values())}
install_json=work/'install.json'
install_json.write_text(json.dumps(install,indent=1,ensure_ascii=False)+'\n',encoding='utf-8')
# the same list as lines for the launcher (native/hw_install.h hw_install_parse); paths last, they hold spaces
def install_line(kind,value):
    if '\n' in value or '\r' in value:raise SystemExit('install list: line break in '+repr(value))
    return kind+' '+value+'\n'
install_text='ORBISDESK-INSTALL 1\n'+install_line('B',HW_BUILD_ID)+install_line('H',host_profiles[0].name)+install_line('T',str(install['bytes']))
install_text+=''.join(install_line('W',w) for w in install['writable'])
install_text+=''.join(install_line('K',k) for k in CONSOLE_OWNED)+''.join(install_line('R',k) for k in user_reg_reset)
install_text+=''.join(install_line('D',d) for d in runtime_directories)
install_text+=''.join(install_line('F','%s %d %s'%(e['sha256'],e['bytes'],path)) for path,e in runtime_files.items())
install_text+=''.join(install_line('O',o) for o in obsolete_files)
install_txt=work/'install.txt';install_txt.write_bytes(install_text.encode('utf-8'))
embedded={} if args.runtime_outside_package else {
    **{'runtime/'+path:data/path for path in runtime_files},'runtime/install.json':install_json,'runtime/install.txt':install_txt}
# alpha-1: nothing of the build PC in what ships. Its checkout and home paths (compilers' __FILE__ and debug
# strings: -ffile-prefix-map in the builders) and its user's profile, in the runtime and the ELF.
build_identity=sorted({str(ROOT),str(ROOT).replace('/','\\'),str(pathlib.Path.home())}-{'','/','\\'})
build_identity_utf16=[s.encode('utf-16-le') for s in build_identity]
identity_hits=[]
for path in [app/'eboot.bin',*(p for p in data.rglob('*') if p.is_file())]:
    blob=path.read_bytes()
    if any(s.encode() in blob for s in build_identity) or any(s in blob for s in build_identity_utf16):
        identity_hits.append(str(path.relative_to(work)))
if (prefix/'drive_c/users'/host_profiles[0].name).exists():identity_hits.append('host profile folder')
if identity_hits and not args.allow_build_paths:
    raise SystemExit('build PC paths in %d shipped files (first: %s); rebuild them with -ffile-prefix-map, '
                     'or --allow-build-paths for a development build'%(len(identity_hits),', '.join(identity_hits[:5])))
content='IV0000-ORBW00002_00-ORBISWINW0010000'
pkg=package_app(ROOT,app,out,'OrbisDesk','ORBW00002',content,version=args.app_version,filename='OrbisDesk.pkg',extra=embedded)
manifest={'build':'W302','app_version':args.app_version,'title_id':'ORBW00002','package':str(pkg.relative_to(ROOT)),'package_sha256':sha(pkg),
    'package_bytes':pkg.stat().st_size,'eboot_sha256':sha(app/'eboot.bin'),'base_wine_elf_sha256':base['bootstrap_sha256'],
    'wine_commit':wine_commit,'prefix_package':verified,'hardware_status':'pending','Wine_booted':False,
    'runtime_root':str(data.relative_to(ROOT)),
    'directories':runtime_directories,'runtime_files':runtime_files,
    'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'native/wine_hardware.c',ROOT/'native/hw_text.h',ROOT/'platform/ps4/pw_wine_fs.c',ROOT/'platform/ps4/pw_wine_platform.c',
        ROOT/'native/wine_boot.c',ROOT/'native/hw_pad.c',ROOT/'native/hw_overlay.c',ROOT/'platform/ps4/pw_wine_sink_ps4.c',ROOT/'tools/build-wine-hardware.py',ROOT/'tools/orbis_package.py',ROOT/'native/hw_install.h',ROOT/'tools/console_state.py')},
    'link_command':command,'eboot_base':hex(EBOOT_BASE),'drive_mounts':{'dosdevices/c:':'../drive_c','dosdevices/z:':'../..'},
    'expected_result':'reports/increment15/native-prefix-console32/result.txt'}
# Reference directory naming differs in older evidence; the canonical increment11
# fixture output is the same console32-bare contract used by the Linux runner.
manifest['expected_result']='reports/increment25-windows-reference/text-result.txt'
manifest['program']='C:\\windows\\explorer.exe /desktop=shell,1280x720'
manifest['licenses']={'folder':'wine-prefix/drive_c/orbis/licenses','files':manifest_licenses,'source_commit':head,'source_dirty':dirty}
manifest['build_identity']={'files_with_build_paths':len(identity_hits),'allowed':args.allow_build_paths,'sample':identity_hits[:20]}
manifest['runs_until_closed']=True
manifest['obsolete_files']=obsolete_files
manifest['user_reg_reset']=user_reg_reset
manifest['runtime_embedded']={'embedded':not args.runtime_outside_package,'install_json':'runtime/install.json','install_json_sha256':sha(install_json),'files':len(runtime_files),'bytes':install['bytes']}
manifest['result_name']='text-result.txt'
manifest['expected_prefix']='passed=1;family_tahoma=1;'
# W112 retains W103's private system.o override and rebuilds native telemetry.
# The old CPU-telemetry preparer draft is deliberately not run.
overlay_source=vk/'src/mangohud-win/src/vulkan.cpp'
if '// OrbisDesk W096: shared-process overlay lock.' not in normalize_marker(overlay_source.read_text()):
    raise SystemExit('W302 requires the W096 shared-process MangoHud patch')
if '// OrbisDesk W099: join outside the UI lock.' not in normalize_marker(overlay_source.read_text()):
    raise SystemExit('W302 requires the W099 teardown patch')
overlay_proof=json.loads((vk/'build/mangohud/orbis-build.json').read_text())
if overlay_proof['dll_sha256']!=vulkan_files['libMangoHud.dll']:
    raise SystemExit('MangoHud DLL differs from its successful build proof')
for name,digest in overlay_proof['sources'].items():
    if sha(vk/'src/mangohud-win'/name)!=digest:
        raise SystemExit('MangoHud source changed since compilation: '+name)
for name,marker in (('src/overlay.cpp','// OrbisDesk W102: sample on the frame thread'),
                    ('src/fps_metrics.h','// OrbisDesk W102: calculate on the frame thread'),
                    ('src/notify_win32.cpp','// OrbisDesk W102: configuration reloads at instance creation')):
    if name not in overlay_proof['sources'] or marker not in normalize_marker((vk/'src/mangohud-win'/name).read_text()):
        raise SystemExit('W302 requires compiled frame-sampling source: '+name)
for name in ('src/cpu_win32.cpp','src/hud_elements.cpp','src/orbis_metrics.h','src/orbis_telemetry.h'):
    if name not in overlay_proof['sources']:raise SystemExit('W302 native metrics source missing from build proof: '+name)
if overlay_proof['sources']['src/orbis_telemetry.h']!=sha(ROOT/'platform/ps4/pw_telemetry.h'):
    raise SystemExit('MangoHud/native telemetry schemas differ')
manifest['mangohud']={'library_sha256':vulkan_files['libMangoHud.dll'],
    'enabled':mangohud_enabled,'implicit_layer_registry_dword':0 if mangohud_enabled else 1,
    'sampling':'frame','fps_metrics':'frame','config_watcher':False,'config_apply':'restart OrbisDesk',
    'patched_vulkan_source_sha256':sha(overlay_source),
    'fix':'shared UI protected; joins and downstream teardown outside UI lock; service synchronous sent messages while joining',
    'build_proof':overlay_proof,
    'hardware_validation':'pending','cpu_gpu_telemetry_changed':True,'metric_labels':['CPU','GPU']}
for source in (ROOT/'tools/vk-h0/build-mangohud.sh',ROOT/'tools/vk-h0/build-mangohud-i386.sh',ROOT/'tools/vk-h0/build-vulkan-loader-i386.sh',ROOT/'tools/vk-h0/patch-mangohud-shared-process.py',ROOT/'tools/vk-h0/patch-mangohud-teardown.py',ROOT/'tools/vk-h0/patch-mangohud-frame-sampling.py'):
    manifest['source_hashes'][str(source.relative_to(ROOT))]=sha(source)
manifest['shell_diagnostics']={'build':'W302','purpose':'locate Start failure after guest window/thread teardown',
    'observer':'independent Wine thread; GUI clock heartbeat; Start and taskbar cleanup progress',
    'guest_thread_wait_result_logged':True,'fix_validated':False}
manifest['reload_diagnostics']={'wine_debug':'warn+module,trace+seh,trace+loaddll,warn+debugstr',
    'load_unload_boundaries':True,'kernel_memory_before_load':True,
    'qpc_and_shared_tick':True,'fix_validated':False}
manifest['native_heap']={'policy':'serialize SDK allocation family using a libkernel-thread-owned recursive lock',
    'entries':list(heap_entries),'allocator_replaced':False,'physical_validation':'pending'}
manifest['source_hashes']['native/native_heap.c']=sha(ROOT/'native/native_heap.c')
manifest['experiment']={'kind':'DOSBox Pure interpreted PE64 guest with GDI and native AudioOut','baseline':'W111',
    'mangohud_enabled':mangohud_enabled,'expected_runtime_differences':['explorer.exe','doshost.exe','dosbox_pure_libretro.dll','DOS license and source archive'],
    'not_a_validated_fix':True}
for source in (ROOT/'tools/build-explorer-hw.py',ROOT/'tools/build-guest-hw.py'):
    manifest['source_hashes'][str(source.relative_to(ROOT))]=sha(source)
manifest['native_telemetry']={'abi_version':1,'query_class':'0x50573454','cpu':'getrusage SELF user + kernel / wall / initial affinity capacity',
    'gpu':'union of title GFX submission timestamps in Crema queue order','build':telemetry_build,
    'physical_validation':'pending','standard_windows_cpu_classes_modified':['SystemProcessorPerformanceInformation','SystemPerformanceInformation.IdleTime']}
manifest['task_manager']={'build':taskmgr,'runtime_differences':['taskmgr.exe','ntdll unix system.o'],
    'cpu':'title process busy/(capacity*wall), same source as the HUD; not system-wide',
    'processes':'Wine processes only; guests share the explorer process','physical_validation':'pending'}
manifest['source_hashes']['tools/build-taskmgr-hw.py']=sha(ROOT/'tools/build-taskmgr-hw.py')
manifest['source_hashes']['tools/build-winecfg-hw.py']=sha(ROOT/'tools/build-winecfg-hw.py')  # W182
manifest['source_hashes']['tools/build-dxgi-hw.py']=sha(ROOT/'tools/build-dxgi-hw.py')  # W192
manifest['source_hashes']['platform/ps4/pw_wine_threads.c']=sha(ROOT/'platform/ps4/pw_wine_threads.c')  # W195
manifest['source_hashes']['tools/build-nsi-hw.py']=sha(ROOT/'tools/build-nsi-hw.py')  # W174 (phase 8)
for source in ('tools/stage-wine-gecko.py','tools/stage-mshtml-hw.py','fixtures/win32/webview.c','fixtures/web/index.html',
               'fixtures/browser/seamonkey-user.js'):  # W177 (phase 9); SeaMonkey replaced Pale Moon
    manifest['source_hashes'][source]=sha(ROOT/source)
manifest['source_hashes']['tools/build-bcrypt-x64.py']=sha(ROOT/'tools/build-bcrypt-x64.py')  # W179 (phase 9)
for source in ('fixtures/win32/winecfgcpl.c','fixtures/win32/winecfgcpl.rc'):  # W179
    manifest['source_hashes'][source]=sha(ROOT/source)
for source in (ROOT/'native/telemetry.c',ROOT/'platform/ps4/pw_telemetry.h',ROOT/'tools/build-telemetry-ps4.py',
               ROOT/'tools/vk-h0/patch-crema-telemetry.py',ROOT/'tools/vk-h0/patch-mangohud-orbis-metrics.py'):
    manifest['source_hashes'][str(source.relative_to(ROOT))]=sha(source)
manifest['file_manager']={'drive_discovery':'real GetFileAttributesW roots in PS4 guest mode',
    'enumeration':'validated find handle; no archive-bit requirement; PWFM errors and counts',
    'wfm_build':json.loads((ROOT/'out/wfm/manifest.json').read_text()),
    'guest_build':json.loads((ROOT/'out/guest-hw/manifest.json').read_text()),
    'open_dispatch':'copied WM_COPYDATA request queued on Explorer desktop thread; ShellExecuteEx NOASYNC',
    'text_associations':['.txt','.log','.ini','.cfg','.conf','.json','.md','.csv','.xml'],
    'association_hive':'HKLM Software Classes (HKCR in pinned Wine)',
    'directory_rename':'real syscall and cached directory/cwd repair; native fs object overridden explicitly',
    'filesystem_object_sha256':sha(fs_override),
    'delete_server_audit':delete_server,
    'directory_filter':directory_build,
    'bsd_unused_dirents':'skip inode=0 and BSD whiteouts with validated record length; preserve active records and real read errors',
    'pending_delete_retry':'at most 10 x 50ms; actual RemoveDirectory only; cancellation and true failure preserved',
    'recursive_delete':'close enumeration before recursion; no reparse traversal; stop/report real errors',
    'reject_invalid_title_replacement':True,
    'explorer_build':json.loads((ROOT/'out/explorer-hw/manifest.json').read_text()),
    'physical_validation':'pending'}
for source in (ROOT/'platform/ps4/pw_dirent_record.h',ROOT/'native/wine_dirent_record_check.c',ROOT/'tools/build-wfm.py',ROOT/'tools/patch-wfm-files.py',ROOT/'tools/wfm-operations.h',ROOT/'tools/wfm-debug.h',ROOT/'tools/build-wine-delete-server.py',ROOT/'tools/build-wine-directory-ps4.py',ROOT/'tools/build-explorer-hw.py',
               ROOT/'tools/patch-explorer-open.py',ROOT/'platform/ps4/pw_shell_open.h',
               ROOT/'native/hw_sink_gpu/hw_sink_gpu.c',ROOT/'native/hw_sink_gpu/screen.vert',ROOT/'native/hw_sink_gpu/screen.frag'):
    manifest['source_hashes'][str(source.relative_to(ROOT))]=sha(source)
manifest['dos_runtime']=dos
for source in ('native/dos_audio.c','native/doshost_win32.c','platform/ps4/pw_dos_audio.h','tools/explorer-dos.h','tools/build-dos-runtime.py','dos.lock.json'):
    manifest['source_hashes'][source]=sha(ROOT/source)
manifest['product']={'name':'OrbisDesk','slug':'orbisdesk','state_root':'/data/orbisdesk',
    'upgrade_identity_preserved':True,'legacy_evidence_unchanged':True}
for source in ('platform/ps4/pw_brand.h','tools/project_brand.py','tools/orbis_package.py'):
    manifest['source_hashes'][source]=sha(ROOT/source)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'package':manifest['package'],'runtime_files':len(manifest['runtime_files']),
    'runtime_bytes':sum(e['bytes'] for e in manifest['runtime_files'].values()),'elf':manifest['eboot_sha256']}))
