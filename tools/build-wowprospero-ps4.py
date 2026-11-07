#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build prospero-win's translator WoW64 CPU backend (wowprospero) for the PS4 runtime.

Unix side: wowprospero's unix.c and the IA-32 DBT, compiled for Orbis and linked into
the Wine boot ELF (link-wine-boot.py), where ntdll finds it through a static table.
PE side: wowprospero.dll, and a wow64.dll whose CPU selection honours
WINE_PS4_WOW64_CPU (adapted from prospero-win patch 0611), both built against the
pinned host Wine tree. Every adaptation keeps the original and records both hashes.
"""
import hashlib,json,pathlib,shlex,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
UP=ROOT/'upstream/prospero-win';MODULE=UP/'wine/wowprospero'
WINE=ROOT/'.deps/wine/source';HOST=ROOT/'.deps/wine/runtime/build';UNIX=ROOT/'.deps/wine/ps4-unix'
SDK=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
work=ROOT/'build/wowprospero-ps4';out=ROOT/'out/wowprospero-ps4'
for path in (work/'src',work/'unix',work/'pe',out/'x86_64-windows'):path.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def run(command,cwd=ROOT):
    log=work/'build.log'
    with log.open('a') as handle:
        handle.write('$ '+' '.join(map(str,command))+'\n');handle.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,check=True,stdout=handle,stderr=subprocess.STDOUT)
def adapt(original,target,replacements):
    text=original.read_text()
    for old,new in replacements:
        if text.count(old)!=1:raise SystemExit('Unexpected context in '+str(original)+': '+old[:70])
        text=text.replace(old,new)
    target.write_text(text)
    return {'original':str(original.relative_to(ROOT)),'original_sha256':sha(original),
            'adapted':str(target.relative_to(ROOT)),'adapted_sha256':sha(target)}
(work/'build.log').write_text('')
commit=subprocess.check_output(['git','-C',str(WINE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
adaptations=[]

# Unix side. The Orbis signal context has the FreeBSD layout PS5 uses: RIP at 224, RSP at 248.
unix_c=work/'src/unix.c'
adaptations.append(adapt(MODULE/'unix.c',unix_c,[
    ('#if defined(__PROSPERO__)\n    return (uintptr_t *)((char *)context + 248);',
     '#if defined(__PROSPERO__) || defined(__ORBIS__)\n    return (uintptr_t *)((char *)context + 248);'),
    ('#if defined(__PROSPERO__)\n    return (uintptr_t *)((char *)context + 224);',
     '#if defined(__PROSPERO__) || defined(__ORBIS__)\n    return (uintptr_t *)((char *)context + 224);')]))
wine_flags=['-I'+str(WINE/'include'),'-Iinclude','-D__WINESRC__','-D_NTSYSTEM_','-DWINE_UNIX_LIB','-D_REENTRANT',
            '-Wall','-fcf-protection=none','-fvisibility=hidden','-fno-stack-protector','-fno-strict-aliasing',
            '-gdwarf-4','-fasynchronous-unwind-tables','-g','-O2','-D__ORBIS__','-I'+str(ROOT/'platform/ps4'),
            '-ffunction-sections','-fdata-sections','-include',str(ROOT/'platform/ps4/pw_wine_posix.h')]
module_flags=['-I'+str(MODULE),'-I'+str(UP/'src'),'-I'+str(UP/'include'),
              '-D__wine_unix_call_funcs=pw_wowprospero_unix_call_funcs']
unix_objects=[work/'unix/unix.o']
run([UNIX/'orbis-cc','-c','-o',unix_objects[0],unix_c,*wine_flags,*module_flags],cwd=UNIX)
dbt=['pw_x86_engine.c','pw_x86_block.c','pw_x86_cache.c','pw_x86_hostexec.c','pw_x86_reencode.c',
     'pw_x87.c','pw_guest_fp.c','pw_vm.c']
dbt_flags=['--target=x86_64-pc-freebsd12-elf','-fPIC','-funwind-tables','-march=btver2','-O2','-g','-Wall',
           '-isysroot',str(SDK),'-isystem',str(SDK/'include'),'-I'+str(UP/'src'),'-I'+str(UP/'include'),
           '-ffunction-sections','-fdata-sections','-fvisibility=hidden']
for name in dbt:
    obj=work/'unix'/(name[:-2]+'.o');unix_objects.append(obj)
    run(['clang',*dbt_flags,'-c',UP/'src'/name,'-o',obj])

# PE side: wowprospero.dll, as tools/build_wowprospero.sh links it.
pe_flags=['-I'+str(MODULE),'-I'+str(HOST/'include'),'-I'+str(WINE/'include'),'-I'+str(WINE/'include/msvcrt'),
          '-D_MSVCR_VER=0','-D__WINESRC__','-D__WINE_PE_BUILD','-Wall','-fno-strict-aliasing',
          '-mcx16','-mcmodel=small','-O2','-g','-fno-builtin','-fshort-wchar']
run(['x86_64-w64-mingw32-gcc','-c','-o',work/'pe/cpu.o',MODULE/'cpu.c',*pe_flags])
dll=out/'x86_64-windows/wowprospero.dll'
run([HOST/'tools/winegcc/winegcc','-o',dll,'--wine-objdir','.','--cc-cmd=x86_64-w64-mingw32-gcc','-b','x86_64-w64-mingw32',
     '-Wl,--wine-builtin','-shared',MODULE/'wowprospero.spec','-nodefaultlibs',work/'pe/cpu.o',
     'dlls/wow64/x86_64-windows/libwow64.a','dlls/ntdll/x86_64-windows/libntdll.a',
     'libs/winecrt0/x86_64-windows/libwinecrt0.a','dlls/ntdll/x86_64-windows/libntdll.a',
     'libs/compiler-rt/x86_64-windows/libcompiler-rt.a'],cwd=HOST)

# PE side: wow64.dll selecting the backend from WINE_PS4_WOW64_CPU (prospero-win patch 0611).
selection='''/**********************************************************************
 *           load_environment_cpu_dll
 *
 * PS4: WINE_PS4_WOW64_CPU names this process's CPU backend. Only the translator
 * backend the runtime ships is accepted; when it cannot be loaded the prefix's
 * own choice is used. Adapted from prospero-win patch 0611 (WINE_PS5_WOW64_CPU).
 */
static HMODULE load_environment_cpu_dll(void)
{
    static const WCHAR allowed[] = L"wowprospero.dll";
    const WCHAR *dir = get_machine_wow64_dir( IMAGE_FILE_MACHINE_TARGET_HOST );
    WCHAR value[32], path[MAX_PATH];
    UNICODE_STRING name, str;
    HMODULE module;
    NTSTATUS status;

    RtlInitUnicodeString( &name, L"WINE_PS4_WOW64_CPU" );
    str.Buffer = value;
    str.Length = 0;
    str.MaximumLength = sizeof(value) - sizeof(WCHAR);
    if (RtlQueryEnvironmentVariable_U( NULL, &name, &str )) return NULL;
    value[str.Length / sizeof(WCHAR)] = 0;
    if (wcscmp( value, allowed ))
    {
        ERR( "ignoring WINE_PS4_WOW64_CPU: not wowprospero.dll\\n" );
        return NULL;
    }
    swprintf( path, MAX_PATH, L"%s\\\\%s", dir, allowed );
    RtlInitUnicodeString( &str, path );
    if ((status = LdrLoadDll( dir, 0, &str, &module )))
    {
        ERR( "wowprospero.dll not loaded (%lx); using the prefix's CPU\\n", status );
        return NULL;
    }
    MESSAGE( "wow64: CPU wowprospero.dll from WINE_PS4_WOW64_CPU\\n" );
    return module;
}


'''
syscall_c=work/'src/syscall.c'
adaptations.append(adapt(WINE/'dlls/wow64/syscall.c',syscall_c,[
    ('/**********************************************************************\n *           get_cpu_dll_name\n',
     selection+'/**********************************************************************\n *           get_cpu_dll_name\n'),
    ('    module = load_64bit_module( get_cpu_dll_name() );\n',
     '    if (!(module = load_environment_cpu_dll())) module = load_64bit_module( get_cpu_dll_name() );\n')]))
recipe=subprocess.check_output(['make','-n','-W','../../source/dlls/wow64/syscall.c','dlls/wow64/x86_64-windows/wow64.dll'],
                               cwd=HOST,text=True).replace('\\\n',' ').splitlines()
compile_line=next(line for line in recipe if 'dlls/wow64/x86_64-windows/syscall.o' in line and ' -c ' in line)
compile_args=shlex.split(compile_line)
compile_args=[str(work/'pe/syscall.o') if arg=='dlls/wow64/x86_64-windows/syscall.o' else
              str(syscall_c) if arg.endswith('dlls/wow64/syscall.c') else arg for arg in compile_args]
run(compile_args,cwd=HOST)
link_line=next(line for line in recipe if 'winegcc' in line and 'wow64.dll' in line)
link_args=shlex.split(link_line)
wow64=out/'x86_64-windows/wow64.dll'
link_args=[str(wow64) if arg=='dlls/wow64/x86_64-windows/wow64.dll' else
           str(work/'pe/syscall.o') if arg=='dlls/wow64/x86_64-windows/syscall.o' else arg for arg in link_args]
run(link_args,cwd=HOST)

manifest={'schema_version':1,'wine_commit':commit,'prospero_win_revision':
          subprocess.check_output(['git','-C',str(UP),'rev-parse','HEAD'],text=True).strip(),
          'adaptations':adaptations,'derived_from':['upstream/prospero-win/wine/wowprospero (LGPL-2.1-or-later)',
          'upstream/prospero-win/wine/patches/0611-wow64-ps5-take-the-cpu-from-the-environment.patch'],
          'unix_objects':{str(path.relative_to(ROOT)):sha(path) for path in unix_objects},
          'modules':{path.name:{'path':'x86_64-windows/'+path.name,'sha256':sha(path)} for path in (dll,wow64)},
          'selection_environment':'WINE_PS4_WOW64_CPU=wowprospero.dll','Wine_booted':False}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':manifest['modules'],'unix_objects':len(unix_objects)}))
