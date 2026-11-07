#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W178 (phase 9): bcrypt.dll for 64-bit programs, which the pinned host tree never linked.

W177: Wine Gecko's xul.dll imports wintrust, which imports crypt32, which imports bcrypt (and
ncrypt, which imports bcrypt too). The sealed prefix has crypt32/ncrypt/wintrust in both views but
no bcrypt.dll, so xul.dll did not load ("Library bcrypt.dll (which is needed by crypt32.dll) not
found", then mshtml "Failed to init Gecko"). Pale Moon's xul.dll imports wintrust and crypt32 too.

The i386 bcrypt.dll is built in .deps/wine/runtime/build; the x86_64 one is not, and cannot be
linked there: its libsymcrypt.a holds objects from an older clang build (llvm_addrsig sections;
clang < 19 sets SYMCRYPT_IGNORE_PLATFORM, so cpuid.o is empty and SymCryptDetectCpuFeaturesByCpuid
is missing). The Makefile compiles symcrypt with x86_64-w64-mingw32-gcc. This builder runs those
exact commands, read from the tree's compile_commands.json, with outputs in build/bcrypt-x64
(the host tree is not written), then the archive and link commands of the Makefile rules.
bcrypt's crypto is SymCrypt (PE code); it has no Unix side to miss. Nothing is patched.
Output: out/bcrypt-x64/x86_64-windows/bcrypt.dll and manifest.json; tools/stage-mshtml-hw.py stages it.
"""
import hashlib,json,pathlib,shlex,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
work=ROOT/'build/bcrypt-x64';out=ROOT/'out/bcrypt-x64'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
wine_commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if wine_commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('bcrypt requires the pinned Wine revision')
commands=json.loads((BUILD/'compile_commands.json').read_text())
def objects(prefix):
    """The tree's compile commands whose output starts with prefix, rewritten to write in work."""
    found=[]
    for entry in commands:
        if not entry['output'].startswith(prefix):continue
        argv=shlex.split(entry['command'])
        if argv[0]!='x86_64-w64-mingw32-gcc' or argv[1:3]!=['-c','-o'] or argv[3]!=entry['output']:
            raise SystemExit('Unexpected compile command for '+entry['output'])
        target=work/entry['output'];argv[3]=str(target)
        found.append((argv,target))
    return found
symcrypt=objects('libs/symcrypt/x86_64-windows/')
main=objects('dlls/bcrypt/x86_64-windows/bcrypt_main.o')
if len(symcrypt)<100 or len(main)!=1:raise SystemExit('compile_commands.json: %d symcrypt objects, %d bcrypt_main'%(len(symcrypt),len(main)))
if work.exists():shutil.rmtree(work)
log_path=work/'build.log'
for argv,target in symcrypt+main:target.parent.mkdir(parents=True,exist_ok=True)
with log_path.open('w') as log:
    def run(argv):
        log.write(' '.join(map(str,argv))+'\n');log.flush()
        subprocess.run(list(map(str,argv)),cwd=BUILD,check=True,stdout=log,stderr=subprocess.STDOUT)
    for argv,target in symcrypt+main:run(argv)
    # libs/symcrypt: the Makefile's static library rule
    archive=work/'libs/symcrypt/x86_64-windows/libsymcrypt.a'
    run(['tools/winebuild/winebuild','-w','--staticlib','-o',archive,'--cc-cmd=x86_64-w64-mingw32-gcc','-b','x86_64-w64-mingw32',
         *[target for _,target in symcrypt]])
    # dlls/bcrypt: the Makefile's link rule (make -n dlls/bcrypt/x86_64-windows/bcrypt.dll), with these two inputs
    dll=work/'dlls/bcrypt/x86_64-windows/bcrypt.dll'
    run(['tools/winegcc/winegcc','-o',dll,'--wine-objdir','.','--cc-cmd=x86_64-w64-mingw32-gcc','-b','x86_64-w64-mingw32',
         '-Wl,--wine-builtin','-shared','../../source/dlls/bcrypt/bcrypt.spec',main[0][1],'dlls/bcrypt/version.res',
         archive,'dlls/advapi32/x86_64-windows/libadvapi32.a','libs/winecrt0/x86_64-windows/libwinecrt0.a',
         'libs/compiler-rt/x86_64-windows/libcompiler-rt.a','dlls/ucrtbase/x86_64-windows/libucrtbase.a',
         'dlls/kernel32/x86_64-windows/libkernel32.a','dlls/ntdll/x86_64-windows/libntdll.a','-Wl,--build-id'])
(out/'x86_64-windows').mkdir(parents=True,exist_ok=True)
shutil.copyfile(dll,out/'x86_64-windows/bcrypt.dll')
manifest={'schema_version':1,'wine_commit':wine_commit,
          'bcrypt':{'path':'x86_64-windows/bcrypt.dll','sha256':sha(out/'x86_64-windows/bcrypt.dll')},
          'objects':len(symcrypt)+1,'compiler':'x86_64-w64-mingw32-gcc (the tree Makefile\'s x86_64_CC)',
          'build_log':str(log_path.relative_to(ROOT)),'source_patches':False,'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'bcrypt':manifest['bcrypt'],'objects':manifest['objects']}))
