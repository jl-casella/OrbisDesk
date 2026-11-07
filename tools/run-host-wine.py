#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Reference execution with pinned native Linux Wine, never PS4 validation."""
import argparse,datetime,hashlib,json,os,pathlib,signal,subprocess,tarfile,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1];wine=ROOT/'.deps/wine/runtime/build'
parser=argparse.ArgumentParser();parser.add_argument('--exe',type=pathlib.Path,default=ROOT/'out/console32.exe')
parser.add_argument('--timeout',type=int,default=25);args=parser.parse_args()
if not 1<=args.timeout<=120:parser.error('timeout must be 1..120 seconds')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out=ROOT/'reports/host-wine-runs'/stamp;out.mkdir(parents=True)
start=time.monotonic()
with tempfile.TemporaryDirectory(prefix='orbis-host-wine-') as temporary:
    directory=pathlib.Path(temporary);prefix=directory/'prefix';run=directory/'run';run.mkdir()
    env=dict(os.environ,WINEPREFIX=str(prefix),WINEDEBUG='-all,err+all')
    with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
        process=subprocess.Popen([str(wine/'loader/wine'),str(args.exe.resolve())],cwd=run,
                                 env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        timed_out=False
        try:code=process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(process.pid,signal.SIGKILL);code=process.wait()
    try:
        cleanup=subprocess.run([str(wine/'server/wineserver'),'-k'],env=env,capture_output=True,timeout=5)
        cleanup_code=cleanup.returncode
    except subprocess.TimeoutExpired:cleanup_code=None
    try:
        stopped=subprocess.run([str(wine/'server/wineserver'),'-w'],env=env,capture_output=True,timeout=5)
        stopped_code=stopped.returncode
    except subprocess.TimeoutExpired:stopped_code=None
    expected=b'sum=500500;thread=ok;dll=ok\r\n';result=run/'result.txt'
    actual=result.read_bytes() if result.is_file() else b''
    if result.is_file():(out/'result.txt').write_bytes(actual)
    with tarfile.open(out/'prefix.tar.gz','w:gz') as archive:
        if prefix.exists():archive.add(prefix,arcname='prefix')
    report={'status':'passed' if code==0 and actual==expected and not timed_out and stopped_code==0 else 'blocked',
            'environment':'Native Linux Wine reference, not shadPS4 or PS4',
            'exit_code':code,'timed_out':timed_out,'result_matches':actual==expected,
            'wine_commit':json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit'],
            'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),
            'duration_seconds':round(time.monotonic()-start,3),'server_cleanup_code':cleanup_code,
            'server_stopped_code':stopped_code,
            'prefix_ready_for_ps4':False,'hardware_status':'pending'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));print(out/'report.json')
