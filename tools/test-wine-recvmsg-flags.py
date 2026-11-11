#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Host-only flag-decoding regression, including a failing pre-fix negative control."""
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
work=ROOT/'build/recvmsg-flags-test';stub=work/'include/orbis';stub.mkdir(parents=True,exist_ok=True)
(stub/'libkernel.h').write_text('int sceKernelDebugOutText(int, const char *);\nint sceKernelUsleep(unsigned int);\n')
source=ROOT/'platform/ps4/pw_wine_net.c'
text=source.read_text();fixed='wire.flags & ~(kernel & KERNEL_MSG_DONTWAIT)'
if text.count(fixed)!=1:raise SystemExit('Unexpected production flag-decoding context')
legacy=work/'legacy-net.c';legacy.write_text(text.replace(fixed,'wire.flags'))
results={}
for name,net in [('legacy',legacy),('fixed',source)]:
    binary=work/name
    command=['cc','-O2','-ffunction-sections','-fdata-sections','-I'+str(work/'include'),
             '-I'+str(ROOT/'platform/ps4'),'-DPROBE_NET_SOURCE="'+str(net)+'"',
             str(ROOT/'tests/wine_recvmsg_flags.c'),'-Wl,--gc-sections','-pthread','-o',str(binary)]
    subprocess.run(command,check=True)
    result=subprocess.run([str(binary)],capture_output=True,text=True)
    results[name]={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
passed=results['legacy']['exit_code']!=0 and results['fixed']['exit_code']==0
report={'classification':'host_unit_synthetic_kernel_replies','passed':passed,'results':results,'hardware_verified':False}
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
raise SystemExit(0 if passed else 1)
