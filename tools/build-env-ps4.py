#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W130: ntdll's env.c with the initial directory a program started on its own gets.

The title may not chdir (W129: EPERM), so a program the launcher starts by itself (a 32-bit
one, relaunched) began wherever the title's Unix cwd was, not in its own folder as Explorer
starts it. SuperMarioKart.exe (Blitz3D) loads its data by relative path and read through a
NULL pointer (W128/W129). get_initial_directory takes PW_PROGRAM_DIR (a Unix path the launcher
sets, native/wine_hardware.c) before the Unix cwd. The proven source is checked by hash and
compiled with its own recipe, as tools/build-telemetry-ps4.py does for system.c.
"""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
UNIX=ROOT/'.deps/wine/ps4-unix';work=ROOT/'build/env-ps4';work.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
base=json.loads((ROOT/'build/wine-boot/report.json').read_text())
entry=next(e for e in base['results'] if e['unit']=='env')
original=ROOT/'.deps/wine/ps4-overlay/dlls/ntdll/unix/env.c'
if sha(original)!=entry['source_sha256']:raise SystemExit('env.c differs from the proven build input')
text=original.read_text()
old='''    /* try to get it from the Unix cwd */
'''
new='''#ifdef __ORBIS__
    /* OrbisDesk W130: the folder of a program started on its own (the title cannot chdir) */
    if ((pwd = getenv( "PW_PROGRAM_DIR" )) && !unix_to_nt_file_name( pwd, &ret, FILE_OPEN ))
    {
        ULONG len = wcslen( ret );
        fprintf( stderr, "PWBOOT initial_directory %s\\n", pwd );
        if (len && ret[len - 1] != '\\\\')
        {
            WCHAR *tmp = malloc( (len + 2) * sizeof(WCHAR) );
            wcscpy( tmp, ret );
            wcscat( tmp, backslashW );
            free( ret );
            ret = tmp;
        }
        return ret;
    }
    if (pwd) fprintf( stderr, "PWBOOT initial_directory unmapped %s\\n", pwd );
#endif
    /* try to get it from the Unix cwd */
'''
if text.count(old)!=1:raise SystemExit('env.c context changed')
text=text.replace(old,new,1)
selected=work/'env.c';selected.write_text(text)
obj=work/'env.o'
command=[str(selected) if arg==str(original) else str(obj) if arg==str(ROOT/'build/wine-boot/env.o') else arg for arg in entry['command']]
if str(obj) not in command or str(selected) not in command:raise SystemExit('env.o recipe changed')
with (work/'env.log').open('w') as log:
    run=subprocess.run(command,cwd=UNIX,stdout=log,stderr=subprocess.STDOUT)
if run.returncode:raise SystemExit('cannot compile env.c; see '+str(work/'env.log'))
report={'wine_commit':base['wine_commit'],'original_source_sha256':sha(original),'source_sha256':sha(selected),
        'object':str(obj.relative_to(ROOT)),'object_sha256':sha(obj),'builder_sha256':sha(pathlib.Path(__file__))}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
