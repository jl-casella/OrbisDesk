#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build native Wine launchers, server and Unix libraries for prefix preparation."""
import hashlib,json,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];BUILD=ROOT/'.deps/wine/runtime/build'
report=json.loads((ROOT/'reports/increment15/host-build/report.json').read_text())
targets=set();skipped=[]
for entry in report['modules'].values():
    directory=pathlib.Path(entry['path']).parent.parent.relative_to('.deps/wine/runtime/build')
    source=ROOT/'.deps/wine/source'/directory/'Makefile.in'
    match=re.search(r'^UNIXLIB\s*=\s*(\S+)',source.read_text(),re.M)
    if not match:continue
    if directory.name=='wineusb.sys':
        skipped.append({'module':str(directory),'reason':'USB host backend unavailable; PE resources only'})
        continue
    targets.add(str(directory/match[1]))
out=ROOT/'reports/increment15/host-build'
inf=(ROOT/'.deps/wine/source/loader/wine.inf.in').read_text()
winmd=re.search(r'^\[WinmdFiles\]\n(.*?)(?=^\[)',inf,re.M|re.S).group(1)
metadata=['include/'+name.strip() for name in winmd.splitlines() if name.strip() and not name.startswith(';')]
# Libraries alone do not build the native entry points. loader/all also
# generates wine.inf and the Linux preloader used when starting wineboot.
programs=('loader/wine','loader/wine-preloader','server/wineserver')
command=['make','-j12','loader/all','server/wineserver',*sorted(targets),'nls/all',*metadata]
with (out/'unix-build.log').open('w') as log:subprocess.run(command,cwd=BUILD,stdout=log,stderr=subprocess.STDOUT,check=True)
result={'scope':'Native Linux host libraries, not PS4 runtime','command':command,'skipped':skipped,
        'programs':{target:hashlib.sha256((BUILD/target).read_bytes()).hexdigest() for target in programs},
        'libraries':{target:hashlib.sha256((BUILD/target).read_bytes()).hexdigest() for target in sorted(targets)},
        'data_files':{str(path.relative_to(BUILD)):hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in [BUILD/'loader/wine.inf',*(BUILD/name for name in metadata),*sorted((BUILD/'nls').glob('*.nls'))]}}
(out/'unix-report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
