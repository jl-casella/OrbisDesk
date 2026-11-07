#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Attempt a strict full Unix ntdll link, retaining every Wine service table."""
import hashlib,json,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
work=ROOT/'build/wine-boot';sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
report=json.loads((work/'report.json').read_text())
if any(r['exit_code'] for r in report['results']):raise SystemExit('Unix units are not all compiled')
flags=['clang','--target=x86_64-pc-freebsd12-elf','-D__ORBIS__','-fPIC','-O2','-g','-isysroot',str(sdk),'-isystem',str(sdk/'include'),'-I'+str(ROOT/'platform/ps4')]
objects=[work/(r['unit']+'.o') for r in report['results'] if r['unit'] not in ('harness','loader-harness')]
for name in ['pw_wine_platform','pw_vm_ps4_kernel','pw_wine_signals','pw_wine_fs','pw_wine_net','pw_wine_unixlibs','pw_wine_sink_ps4','pw_wine_memory','pw_wine_once','pw_wine_audio']:
    obj=work/(name+'.o');subprocess.run([*flags,'-c',str(ROOT/'platform/ps4'/(name+'.c')),'-o',str(obj)],check=True);objects.append(obj)
wowprospero=json.loads((ROOT/'out/wowprospero-ps4/manifest.json').read_text())
objects+=[ROOT/path for path in wowprospero['unix_objects']]
# W137: the native WoW64 CPU backend (tools/build-wow64native-ps4.py), through pw_wine_unixlibs.c.
wow64native=json.loads((ROOT/'out/wow64native-ps4/manifest.json').read_text())
for path,digest in wow64native['unix_objects'].items():
    if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise SystemExit('wow64native object changed after its build')
    objects.append(ROOT/path)
# win32u's Unix side, linked as one object whose hidden symbols stay local to it, as
# they would in its own win32u.so; ntdll reaches it through pw_wine_unixlibs.c.
win32u=json.loads((ROOT/'build/win32u-ps4/report.json').read_text())
win32u_combined=work/'win32u-combined.o';win32u_object=work/'win32u.o'
subprocess.run(['ld.lld','-r','-o',str(win32u_combined),*[str(ROOT/path) for path in win32u['objects']]],check=True)
subprocess.run(['objcopy','--localize-hidden','--redefine-sym','__wine_unix_lib_init=pw_win32u_unix_lib_init',
                str(win32u_combined),str(win32u_object)],check=True)
objects.append(win32u_object)
# W071: winevulkan's Unix side (tools/build-winevulkan-ps4.py), found by pw_wine_unixlibs.c.
winevulkan=json.loads((ROOT/'build/winevulkan-ps4/report.json').read_text())
if hashlib.sha256((ROOT/winevulkan['object']).read_bytes()).hexdigest()!=winevulkan['object_sha256']:
    raise SystemExit('winevulkan object changed after its build')
objects.append(ROOT/winevulkan['object'])
# W093: ws2_32's Unix side (tools/build-unixlibs-ps4.py), also through pw_wine_unixlibs.c.
unixlibs=json.loads((ROOT/'build/unixlibs-ps4/report.json').read_text())
for lib,entry in sorted(unixlibs['libraries'].items()):
    if hashlib.sha256((ROOT/entry['object']).read_bytes()).hexdigest()!=entry['sha256']:
        raise SystemExit(lib+' object changed after its build')
    objects.append(ROOT/entry['object'])
# W120: Wine's audio driver for the console (tools/build-audio-ps4.py), through pw_wine_unixlibs.c.
audio=json.loads((ROOT/'build/audio-ps4/report.json').read_text())['objects']['driver']
if hashlib.sha256((ROOT/audio['object']).read_bytes()).hexdigest()!=audio['sha256']:
    raise SystemExit('audio driver object changed after its build')
objects.append(ROOT/audio['object'])
# W178 (phase 7): xinput's Unix side, the console's pad (tools/build-xinput-hw.py), through
# pw_wine_unixlibs.c; its pad calls resolve to native/hw_pad.c in the hardware ELF and to
# pw_wine_unixlibs.c's weak "no pad" here.
xinput=json.loads((ROOT/'out/xinput-hw/manifest.json').read_text())['unix_object']
if hashlib.sha256((ROOT/'out/xinput-hw'/xinput['path']).read_bytes()).hexdigest()!=xinput['sha256']:
    raise SystemExit('xinput object changed after its build')
objects.append(ROOT/'out/xinput-hw'/xinput['path'])
# HID stack: winebus's Unix side with the console's pad as an HID gamepad (tools/build-hidstack-hw.py),
# through pw_wine_unixlibs.c; pw_wine_pad_peek is native/hw_pad.c's here too, or the weak "no pad".
hidstack=json.loads((ROOT/'out/hidstack-hw/manifest.json').read_text())['unix_object']
if hashlib.sha256((ROOT/'out/hidstack-hw'/hidstack['path']).read_bytes()).hexdigest()!=hidstack['sha256']:
    raise SystemExit('winebus object changed after its build')
objects.append(ROOT/'out/hidstack-hw'/hidstack['path'])
freetype=win32u['freetype']
freetype_library=ROOT/freetype['library']
if hashlib.sha256(freetype_library.read_bytes()).hexdigest()!=freetype['sha256']:
    raise SystemExit('FreeType archive changed after win32u compilation')
# Include the archive after the referencing objects in both final links.
objects.append(freetype_library)
server=ROOT/'build/wine-server'
server_report=json.loads((server/'report.json').read_text())
if any(r['exit_code'] for r in server_report['results']):raise SystemExit('Server units are not all compiled')
combined=server/'combined.o'
subprocess.run(['ld.lld','-r','-o',str(combined),*[str(server/(r['unit']+'.o')) for r in server_report['results']]],check=True)
symbols=subprocess.check_output(['nm','-g','--defined-only',str(combined)],text=True)
mapping=server/'namespace.txt'
names=[line.split()[-1] for line in symbols.splitlines() if len(line.split())>=3]
mapping.write_text(''.join(f'{name} pwserver_{name}\n' for name in names if not name.startswith('pw_wine')))
namespaced=server/'inprocess.o'
subprocess.run(['objcopy','--redefine-syms='+str(mapping),str(combined),str(namespaced)],check=True)
objects.append(namespaced)
command=['ld.lld','-shared','-Bsymbolic','--no-undefined','--error-limit=0','--eh-frame-hdr','--script',str(sdk/'link.x'),'-soname','ntdll.so','-o',str(work/'ntdll.so'),
         *map(str,objects),'-L'+str(work/'lib'),'-L'+str(sdk/'lib'),'-lc','-lm','-lunwind','-lkernel','-lkernel_sys','-lSceNet','-lSceVideoOut','-lSceAudioOut']
with (work/'link.log').open('w') as log:r=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
missing=sorted(set(re.findall(r'undefined(?: hidden)? symbol: ([^\n]+)',(work/'link.log').read_text())))
out={'status':'linked-unvalidated' if not r.returncode else 'blocked','exit_code':r.returncode,'command':command,'helper_compile_flags':flags,
     'wine_commit':report['wine_commit'],'undefined_symbols':missing,'Wine_booted':False,'hardware_status':'pending',
     'object_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in objects}}
(work/'link-report.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'status':out['status'],'undefined_symbols':missing}))
if not r.returncode:
    services_obj=work/'wine_boot_services.o'
    subprocess.run([*flags,'-c',str(ROOT/'native/wine_boot_services.c'),'-o',str(services_obj)],check=True)
    probe_objects=[]
    for filename in ('wine_ipc_probe','wine_gs_probe','wine_signal_probe','wine_pipe_probe','wine_fs_probe','wine_metadata_probe','wine_prefix_probe'):
        obj=work/(filename+'.o');subprocess.run([*flags,'-c',str(ROOT/'native'/(filename+'.c')),'-o',str(obj)],check=True)
        probe_objects.append(obj)
    main_obj=work/'wine_boot.o'
    subprocess.run([*flags,'-c',str(ROOT/'native/wine_boot.c'),'-o',str(main_obj)],check=True)
    boot_command=['ld.lld','-pie','--no-undefined','--error-limit=0','--eh-frame-hdr','--script',str(sdk/'link.x'),
                  '-o',str(work/'bootstrap.elf'),str(main_obj),str(services_obj),*map(str,probe_objects),*map(str,objects),str(sdk/'lib/crt1.o'),
                  '-L'+str(work/'lib'),'-L'+str(sdk/'lib'),'-lc','-lm','-lunwind','-lkernel','-lkernel_sys','-lSceNet','-lSceVideoOut','-lSceAudioOut']
    with (work/'bootstrap-link.log').open('w') as log: boot=subprocess.run(boot_command,stdout=log,stderr=subprocess.STDOUT)
    out['bootstrap_command']=boot_command;out['bootstrap_exit_code']=boot.returncode
    if not boot.returncode:
        import os
        subprocess.run([str(sdk/'bin/linux/create-fself'),'-in='+str(work/'bootstrap.elf'),'-out='+str(work/'bootstrap.oelf'),
                        '--eboot',str(work/'eboot.bin'),'--paid','0x3800000000000011'],check=True,
                       env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk)))
        out['bootstrap_sha256']=hashlib.sha256((work/'eboot.bin').read_bytes()).hexdigest()
    (work/'link-report.json').write_text(json.dumps(out,indent=2)+'\n')
    if boot.returncode:raise SystemExit(boot.returncode)
raise SystemExit(r.returncode)
