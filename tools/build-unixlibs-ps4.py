#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W093: the Unix side of ws2_32 (dlls/ws2_32/unixlib.c) for Orbis, unpatched, each with its recipe from the OrbisDesk Makefile, as
build-winevulkan-ps4.py does for winevulkan. Each library's object becomes one whose hidden
symbols stay local, with its call tables renamed pw_<lib>_unix_call_funcs and
pw_<lib>_unix_call_wow64_funcs for platform/ps4/pw_wine_unixlibs.c.

W092 on hardware: ws2_32.dll's initialisation failed ("failed to load .../ws2_32.so: Dynamic
loading not supported"), so every module importing it failed to load with
ERROR_DLL_INIT_FAILED: iphlpapi, and through it MangoHud's layer."""
import hashlib,json,pathlib,shlex,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP='-ffile-prefix-map=%s=. -ffile-prefix-map=%s=vk-h0'%(ROOT,pathlib.Path.home()/'vk-h0')
SOURCE=ROOT/'.deps/wine/source';UNIX=ROOT/'.deps/wine/ps4-unix';work=ROOT/'build/unixlibs-ps4'
# A unit is a Wine source compiled with its own recipe, or (recipe, platform source): a file of
# platform/ps4 compiled with that Wine recipe's flags and include paths.
LIBS={# Phase 8: ws2_32 with getaddrinfo and the other resolver calls answered by
      # platform/ps4/pw_ws2_32_libc.c (the console's resolver) instead of musl's, which has no
      # name server here; configure had found no getaddrinfo, so every lookup failed.
      'ws2_32':['dlls/ws2_32/unixlib',('dlls/ws2_32/unixlib','platform/ps4/pw_ws2_32_libc.c')],
      # W121: opengl32's Unix side (its WoW64 thunks to win32u's WGL); without it the 32-bit
      # opengl32.dll failed to initialise, and with it ddraw/wined3d (W120, SuperMarioKart.exe).
      'opengl32':['dlls/opengl32/unix_thunks','dlls/opengl32/unix_wgl'],
      # Phase 8: dnsapi has no Unix side without libresolv (all of libresolv.c is under
      # HAVE_RESOLV). platform/ps4/pw_wine_netctl.c is one from libSceNetCtl and UDP (dnsapi.so),
      # with the settings call of the hardware nsi.dll (nsi.so); its tables are named
      # pw_dnsapi_* and pw_nsi_* in the source.
      'netctl':[('dlls/dnsapi/libresolv','platform/ps4/pw_wine_netctl.c')],
      # W180 (phase 9): crypt32's Unix side, without GnuTLS (PFX and key-store calls answer
      # STATUS_DLL_NOT_FOUND) and without a CA bundle on the console. W179: crypt32.dll could not
      # initialise, so neither Wine Gecko's nor Pale Moon's xul.dll loaded (both import it through
      # wintrust). platform/ps4/pw_crypt32_unix.c holds the tables, with PWCRYPT traces.
      'crypt32':['dlls/crypt32/unixlib',('dlls/crypt32/unixlib','platform/ps4/pw_crypt32_unix.c')]}
DEFINES={'ws2_32':['-DHAVE_GETADDRINFO=1','-Dgetaddrinfo=pw_ws2_getaddrinfo','-Dfreeaddrinfo=pw_ws2_freeaddrinfo',
                   '-Dgetnameinfo=pw_ws2_getnameinfo','-Dgethostbyname=pw_ws2_gethostbyname',
                   '-Dgethostbyaddr=pw_ws2_gethostbyaddr','-Dgethostname=pw_ws2_gethostname',
                   '-D__h_errno_location=pw_ws2_h_errno_location'],
         # Wine's tables keep a name of their own; pw_crypt32_unix.c defines the registered ones
         'crypt32':['-D__wine_unix_call_funcs=pw_crypt32_wine_unix_call_funcs',
                    '-D__wine_unix_call_wow64_funcs=pw_crypt32_wine_unix_call_wow64_funcs']}
work.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
makefile=(UNIX/'Makefile').read_text().splitlines()
def recipe(target):
    index=next((i for i,line in enumerate(makefile) if line.startswith(target+': ') and i+1<len(makefile)
                and makefile[i+1].startswith('\t$(CC)')),None)
    if index is None:raise SystemExit('No recipe for '+target)
    parts=[];index+=1
    while True:
        line=makefile[index];parts.append(line.rstrip().removesuffix('\\'))
        if not line.rstrip().endswith('\\'):break
        index+=1
    return ' '.join(parts).replace('$(CC)',str(UNIX/'orbis-cc')).replace('$(CFLAGS)','-g -O2 '+PREFIX_MAP)
report={'schema_version':1,'wine_commit':commit,'results':[],'libraries':{}}
for lib,units in LIBS.items():
    objects=[]
    for unit in units:
        unit,platform=unit if isinstance(unit,tuple) else (unit,None)
        name=pathlib.PurePosixPath(platform).stem if platform else unit.rsplit('/',1)[1]
        output=work/(lib+'-'+name+'.o')
        command=shlex.split(recipe(unit+'.o').replace('$@',str(output)))
        if platform:
            wine_source=str(SOURCE/(unit+'.c'))
            if command.count(wine_source)!=1:raise SystemExit('Unexpected recipe for '+unit)
            command=[str(ROOT/platform) if arg==wine_source else arg for arg in command]
        command+=['-D__ORBIS__','-I'+str(ROOT/'platform/ps4'),'-ffunction-sections','-fdata-sections',
                  '-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),'-idirafter',str(ROOT/'.deps/wine/runtime/build/include'),
                  *DEFINES.get(lib,[])]
        with (work/(output.stem+'.log')).open('w') as log:
            run=subprocess.run(command,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
        report['results'].append({'unit':unit,'source':platform or unit+'.c','exit_code':run.returncode})
        if not run.returncode:objects.append(output)
    if len(objects)!=len(units):continue
    combined=work/(lib+'-combined.o');final=work/(lib+'.o')
    subprocess.run(['ld.lld','-r','-o',str(combined),*map(str,objects)],check=True)
    subprocess.run(['objcopy','--localize-hidden',
                    '--redefine-sym','__wine_unix_call_funcs=pw_%s_unix_call_funcs'%lib,
                    '--redefine-sym','__wine_unix_call_wow64_funcs=pw_%s_unix_call_wow64_funcs'%lib,
                    # the kernel's pthread_once overflows the 4-byte pthread_once_t (platform/ps4/pw_wine_once.c)
                    '--redefine-sym','pthread_once=pw_wine_pthread_once',
                    str(combined),str(final)],check=True)
    report['libraries'][lib]={'object':str(final.relative_to(ROOT)),'sha256':sha(final)}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
report['builder_sha256']=sha(pathlib.Path(__file__))
failed=[r['source'] for r in report['results'] if r['exit_code']]
print(json.dumps({'libraries':sorted(report['libraries']),'failed':failed}))
if failed:raise SystemExit(1)
