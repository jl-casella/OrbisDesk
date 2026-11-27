#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import pathlib,subprocess,tempfile
r=pathlib.Path(__file__).resolve().parents[1]
code='\n#include <assert.h>\n#include <stdio.h>\n#include <string.h>\n#include "pw_compiler_policy.h"\nint main(void){\n char out[4096];const char *user="dxvk.numCompilerThreads=4;d3d9.maxFrameLatency=3";\n assert(pw_compiler_clean(user,out,sizeof(out))&&!strcmp(out,user));\n assert(pw_compiler_clean("dxvk.numCompilerThreads=4" PW_COMPILER_MARK ";[game.exe];dxvk.numCompilerThreads=2",out,sizeof(out))&&!strcmp(out,"dxvk.numCompilerThreads=4"));\n assert(pw_compiler_clean(PW_COMPILER_MARK ";[other.exe];dxvk.numCompilerThreads=2",out,sizeof(out))&&!out[0]);\n assert(pw_compiler_clean(NULL,out,sizeof(out))&&!out[0]);\n strcpy(out,"sentinel");assert(!pw_compiler_clean("long",out,4)&&!strcmp(out,"sentinel"));\n assert(!pw_compiler_clean(NULL,NULL,0));\n const char unicode[]={\'u\',\'s\',\'e\',\'r\',\'=\',(char)0xc3,(char)0xb1,0};\n assert(pw_compiler_clean(unicode,out,sizeof(out))&&!memcmp(out,unicode,sizeof(unicode)));\n puts("PASS: migration removes only the marked OrbisDesk suffix; explicit compiler settings, Unicode and user sections preserved; capacity failure is non-destructive");\n}\n'

with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-no-pie','-I'+str(r/'platform/ps4'),str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],cwd=p,check=True)
