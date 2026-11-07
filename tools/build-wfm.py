#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build WFM (Winlator File Manager, https://github.com/brunodev85/wfm, MIT) as PE64.

W058. The sources are a clone in .deps/wfm at a recorded commit; they are compiled with
the flags of WFM's own Makefile (CFLAGS, include dirs, libraries, windows subsystem),
using the mingw-w64 cross compiler instead of w64devkit. ISO extraction links against the
repository's prebuilt libcdio.dll (PE32+, imports KERNEL32 and msvcrt), shipped as is,
with its hash recorded. Output: out/wfm/wfm.exe, libcdio.dll, LICENSE, manifest.json.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wfm';work=ROOT/'build/wfm';out=ROOT/'out/wfm'
COMMIT='6b1860895885a6d65c37815308260293341acb5f'
LIBCDIO_SHA256='cc9b86da2a437fd6859acaaf7de71ef271d4b7ba8274ebe7cfc92d86ce51ed09'
CC='x86_64-w64-mingw32-gcc';RC='x86_64-w64-mingw32-windres'
CFLAGS=['-O2','-std=c99','-DUNICODE','-D_UNICODE','-DCOBJMACROS','-DWINVER=0x0600','-Wall',
        '-include',str(ROOT/'tools/wfm-debug.h')]
INCLUDE=['-I'+str(SOURCE/'include'),'-I'+str(SOURCE/'include/libcdio'),'-I'+str(ROOT/'platform/ps4')]
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=COMMIT:raise SystemExit('WFM clone is at %s, expected %s'%(commit,COMMIT))
if sha(SOURCE/'libcdio.dll')!=LIBCDIO_SHA256:raise SystemExit('libcdio.dll differs from the recorded binary')
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
# Sources are compiled from a copy, with these changes (the clone stays as fetched).
REVISIONS=[('main.c','''            if (MessageBox(NULL, lc_str.msg_confirm_exit_app, lc_str.confirm_exit, MB_YESNO | MB_ICONQUESTION) == IDYES) {
                PostQuitMessage(0);
            }''','''            /* PS4 hardware build (W060): closing does not ask for confirmation */
            PostQuitMessage(0);''',"Close without the exit confirmation, at the user's request.")]
if (work/'src').exists():shutil.rmtree(work/'src')
shutil.copytree(SOURCE/'src',work/'src')
for name,old,new,why in REVISIONS:
    text=(work/'src'/name).read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in %s: %s'%(name,old[:60]))
    (work/'src'/name).write_text(text.replace(old,new))
subprocess.run(['python3',str(ROOT/'tools/patch-wfm-files.py'),str(work/'src')],check=True)
objects=[]
for source in sorted((work/'src').glob('*.c')):
    obj=work/(source.stem+'.o')
    subprocess.run([CC,*CFLAGS,*INCLUDE,'-c',str(source),'-o',str(obj)],check=True)
    objects.append(obj)
resource=work/'resource.o'
subprocess.run([RC,*INCLUDE,'-I'+str(SOURCE/'res'),'-i',str(SOURCE/'res/resource.rc'),'-o',str(resource)],check=True,cwd=SOURCE/'res')
objects.append(resource)
exe=out/'wfm.exe'
subprocess.run([CC,'-o',str(exe),*map(str,objects),'-s','-lcomctl32','-lgdi32','-lole32','-luuid',str(SOURCE/'libcdio.dll'),
                '-Wl,--subsystem,windows','-Wl,--no-insert-timestamp'],check=True)
shutil.copyfile(SOURCE/'libcdio.dll',out/'libcdio.dll')
shutil.copyfile(SOURCE/'LICENSE',out/'LICENSE')
manifest={'schema_version':1,'source':'https://github.com/brunodev85/wfm','commit':commit,'license':'MIT',
          'files':{name:{'path':name,'sha256':sha(out/name)} for name in ('wfm.exe','libcdio.dll','LICENSE')},
          'revisions':[{'path':'src/'+n,'why':w} for n,_,_,w in REVISIONS]+[{'path':'src/file_node.c, src/content_view.c','why':'W105: validate enumeration handles, list regular files regardless of archive flag, log real errors.'}],
          'patch_sha256':sha(ROOT/'tools/patch-wfm-files.py'),
          'operations_sha256':sha(ROOT/'tools/wfm-operations.h'),
          'debug_header_sha256':sha(ROOT/'tools/wfm-debug.h'),
          'open_protocol_sha256':sha(ROOT/'platform/ps4/pw_shell_open.h'),
          'source_hashes':{p.name:sha(p) for p in sorted((work/'src').glob('*.c'))},
          'cflags':CFLAGS,'libraries':['comctl32','gdi32','ole32','uuid','libcdio.dll']}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({name:e['sha256'] for name,e in manifest['files'].items()}))
