#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W011 emulator smoke check: the packaged launcher with its staged /data runtime."""
import argparse,datetime,hashlib,json,os,pathlib,re,shutil,signal,subprocess,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--timeout',type=int,default=180);args=parser.parse_args()
work_root=ROOT/'build/wine-hardware-w011';app=work_root/'app';runtime=work_root/'runtime'
out=ROOT/'reports/wine-hardware-w011'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out.mkdir(parents=True)
manifest=json.loads((ROOT/'out/wine-hardware-w011/manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if sha(app/'eboot.bin')!=manifest['eboot_sha256']:raise SystemExit('eboot differs from the W011 manifest')
reference=(ROOT/manifest['expected_result']).read_bytes()
with tempfile.TemporaryDirectory(prefix='orbis-w011-') as tmp:
    work=pathlib.Path(tmp);data=work/'data'
    shutil.copytree(runtime,data,symlinks=True)
    for name,entry in manifest['runtime_files'].items():
        if sha(data/name)!=entry['sha256']:raise SystemExit('staged runtime differs: '+name)
    command=['python3',str(ROOT/'tools/run-linux-shad.py'),'--fork','--config-clean','--fullscreen','false',
             '--mount',str(data),'/data','-g',str(app/'eboot.bin')]
    timed_out=False
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        proc=subprocess.Popen(command,cwd=work,stdout=stdout,stderr=stderr,start_new_session=True)
        try:proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:timed_out=True;os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    if (data/'orbisdesk/w011').exists():shutil.copytree(data/'orbisdesk/w011',out/'w011',symlinks=True)
    result=data/'wine-prefix/drive_c/orbis/result.txt'
    if result.exists():shutil.copyfile(result,out/'result.txt')
logs=sorted((out/'w011').glob('run-*.log')) if (out/'w011').exists() else []
log=logs[-1].read_text(errors='replace') if logs else ''
markers=re.findall(r'^(?:W011|PWBOOT) [^\r\n]*',log,re.M)
exit_match=re.search(r'W011 process_exit method=\S+ status=0x([0-9a-f]{8})',log)
boot_return=re.search(r'W011 boot_main_return rc=(-?\d+)',log)
text=(out/'stdout.log').read_text(errors='replace')
STUB=r'\bStub: ([^\r\n(]+) \(nid:'
stubs=sorted(set(re.findall(STUB,text)))
matches=(out/'result.txt').exists() and (out/'result.txt').read_bytes()==reference
exit_code=int(exit_match.group(1),16) if exit_match else int(boot_return.group(1)) if boot_return else None
# dup2 and fcntl are fork stubs used only by the launcher's verified stderr redirect;
# Wine itself must not reach any stub after the launcher hands over.
launcher_text,_,wine_text=text.partition('W011 calling_wine_boot_main')
launcher_stubs=set(re.findall(STUB,launcher_text))
wine_stubs=sorted(set(re.findall(STUB,wine_text)))
unexpected=sorted(launcher_stubs-{'_dup2','_fcntl'})+wine_stubs
status='passed' if matches and exit_code==0 and not unexpected else 'blocked' if markers else 'failed'
report={'build':'W011','status':status,'classification':'emulator smoke check only','hardware_status':'pending',
    'timed_out':timed_out,'exit_code':exit_code,'result_matches_windows_reference':matches,
    'last_marker':markers[-1] if markers else None,'markers':len(markers),
    'invoked_stubs':stubs,'wine_stubs':wine_stubs,'unexpected_stubs':unexpected,'eboot_sha256':manifest['eboot_sha256'],'log':str(logs[-1].relative_to(out)) if logs else None}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(out/'report.json');print(json.dumps({k:report[k] for k in ('status','exit_code','last_marker','invoked_stubs')}))
if status!='passed':raise SystemExit('W011 smoke check did not pass')
