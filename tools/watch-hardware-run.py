#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Wait, polling the console over FTP, until a run of a given program has ended.

Read-only: lists /data/orbisdesk/<build>/ and reads the head and tail of each new run log
(REST offsets, never the whole file). Exits 0 and prints one line when a run whose launcher
started the program (launch_arg --wine-exe=...<program>) logs process_exit; exits 2 after the
time limit. Used so a session can resume when the user has finished a hardware test.

  python3 tools/watch-hardware-run.py --build W133 --host 192.168.68.104 --program SuperMarioKart.exe
"""
import argparse,ftplib,io,sys,time
parser=argparse.ArgumentParser()
parser.add_argument('--build',required=True);parser.add_argument('--host',required=True)
parser.add_argument('--port',type=int,default=2121);parser.add_argument('--program',required=True)
parser.add_argument('--interval',type=int,default=120);parser.add_argument('--limit-hours',type=float,default=6)
args=parser.parse_args()
folder='/data/orbisdesk/'+args.build.lower()
deadline=time.time()+args.limit_hours*3600
known={}
def connect():
    ftp=ftplib.FTP();ftp.connect(args.host,args.port,timeout=60);ftp.login();return ftp
def part(path,offset,length):
    """Bytes [offset, offset+length) of a file, on a connection of its own: the console's
    FTP server closes the control connection when a transfer is cut short."""
    data=io.BytesIO()
    class Done(Exception):pass
    def sink(chunk):
        data.write(chunk)
        if data.tell()>=length:raise Done
    ftp=connect()
    try:ftp.retrbinary('RETR '+path,sink,rest=offset)
    except Done:pass
    finally:
        try:ftp.close()
        except Exception:pass
    return data.getvalue()[:length].decode('latin1')
while time.time()<deadline:
    try:
        ftp=connect()
        for name in sorted(n.rsplit('/',1)[-1] for n in ftp.nlst(folder)):
            if not name.startswith('run-') or not name.endswith('.log'):continue
            path=folder+'/'+name
            # A log the title is writing can answer SIZE/RETR with 550: skip it this pass rather
            # than lose the whole pass (W134: every pass failed and the run went unnoticed).
            try:size=ftp.size(path) or 0
            except ftplib.error_perm:continue
            entry=known.setdefault(name,{'program':None,'size':-1})
            if entry['program'] is None:
                try:head=part(path,0,64*1024)
                except (ftplib.Error,OSError,EOFError):continue
                launch=[l for l in head.splitlines() if 'launch_arg --wine-exe=' in l]
                if launch:entry['program']=launch[0].split('--wine-exe=',1)[1].strip()
            if size!=entry['size']:
                entry['size']=size
                if entry['program'] and entry['program'].lower().endswith(args.program.lower()):
                    try:tail=part(path,max(0,size-8192),8192)
                    except (ftplib.Error,OSError,EOFError):entry['size']=-1;continue
                    if 'process_exit' in tail:
                        print('run ended: %s %s (%d bytes)'%(name,entry['program'],size),flush=True)
                        ftp.quit();sys.exit(0)
        ftp.quit()
    except (OSError,EOFError,ftplib.Error) as error:
        print('poll error: %s'%error,file=sys.stderr,flush=True)
    time.sleep(args.interval)
print('time limit reached without a finished run of '+args.program,flush=True)
sys.exit(2)
