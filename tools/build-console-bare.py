#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Same console test with a direct Win32 entry point and no C runtime DLL."""
import hashlib,json,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];out=ROOT/'out/console32-bare.exe'
inputs=[ROOT/'fixtures/win32/console.c',ROOT/'fixtures/win32/console_entry.c']
command=['i686-w64-mingw32-gcc','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-stack-protector',
         '-fno-asynchronous-unwind-tables','-nostdlib','-Dmain=console_main',*map(str,inputs),
         '-Wl,--entry,_entry,--no-insert-timestamp','-lkernel32','-o',str(out)]
subprocess.run(command,check=True)
headers=subprocess.check_output(['i686-w64-mingw32-objdump','-p',str(out)],text=True)
imports=re.findall(r'DLL Name: (\S+)',headers)
if [name.lower() for name in imports]!=['kernel32.dll']:raise SystemExit('Unexpected imports: '+str(imports))
manifest={'command':command,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'imports':imports,
          'inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
          'runtime_verified':False,'hardware_status':'pending'}
(ROOT/'out/console32-bare.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))
