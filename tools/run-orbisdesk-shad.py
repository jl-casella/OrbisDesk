#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Leave an OrbisDesk build open in WSLg using a private, reusable runtime."""
import argparse,datetime,hashlib,json,pathlib,subprocess,tempfile,shutil
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--build',default='W284');p.add_argument('--fresh',action='store_true');args=p.parse_args()
if not args.build.startswith('W') or not args.build[1:].isdigit():p.error('expected W followed by digits')
manifest=json.loads((ROOT/('out/wine-hardware-'+args.build.lower())/'manifest.json').read_text())
app=ROOT/('build/wine-hardware-'+args.build.lower())/'app';sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
if sha(app/'eboot.bin')!=manifest['eboot_sha256']:raise SystemExit('eboot differs from manifest')
emulator=json.loads((ROOT/'build/shadPS4-linux/build-manifest.json').read_text())
if sha(ROOT/'build/shadPS4-linux/shadps4')!=emulator['executable_sha256']:raise SystemExit('emulator differs from manifest')
state=ROOT/'build/orbisdesk-shad-visible.json';previous=json.loads(state.read_text()) if state.exists() else {}
work=pathlib.Path(previous['run_dir']) if not args.fresh and previous.get('build')==args.build else None
if work is None or not (work/'data').is_dir():
 work=pathlib.Path(tempfile.mkdtemp(prefix='orbisdesk-'+args.build.lower()+'-shad-'))
 shutil.copytree(ROOT/manifest['runtime_root'],work/'data',symlinks=True)
command=['python3',str(ROOT/'tools/run-linux-shad.py'),'--fork','--config-clean','--fullscreen','false','--mount',str(work/'data'),'/data','-g',str(app/'eboot.bin')]
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def setup():pathlib.Path('/proc/self/coredump_filter').write_text('0')
with (work/('stdout-'+stamp+'.log')).open('w') as out,(work/('stderr-'+stamp+'.log')).open('w') as err:
 proc=subprocess.Popen(command,cwd=work,stdout=out,stderr=err,start_new_session=True,preexec_fn=setup)
record={'build':args.build,'pid':proc.pid,'run_dir':str(work),'command':command,'started_utc':stamp,'core_filter':'0','emulator_sha256':emulator['executable_sha256']}
state.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
