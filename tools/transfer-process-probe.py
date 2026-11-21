#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""FTP-stage a verified diagnostic, optionally its external loader. Never execute payloads."""
import argparse
import datetime
import ftplib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',choices=['P001','P002','P003','P004','P005','P007','P009','P012','P013'],required=True)
    parser.add_argument('--host',required=True)
    parser.add_argument('--port',type=int,default=2121)
    parser.add_argument('--include-loader',action='store_true')
    parser.add_argument('--loader-dir',type=Path,default=ROOT/'out/process-loader')
    args=parser.parse_args();build=args.build;stem='process-hardware-'+build.lower()
    manifest=json.loads((ROOT/'out'/stem/'manifest.json').read_text())
    package=ROOT/manifest['package']
    if digest(package)!=manifest['package_sha256']:raise RuntimeError('Package hash differs from manifest')
    items=[(package,'/data/pkg/'+package.name,manifest['package_sha256'])]
    if args.include_loader:
        if build not in ('P005','P012'):parser.error('External loader staging is only defined for P005')
        loader=json.loads((args.loader_dir/'manifest.json').read_text())
        tag=loader.get('build','P005')
        items.append((args.loader_dir/'elfldr.elf','/data/payloads/OrbisDesk-elfldr-'+tag+'.elf',loader['artifacts']['elfldr.elf']['sha256']))
        source=args.loader_dir/'source-bundle.tar.gz'
        if source.exists():items.append((source,'/data/orbisdesk/process-p005/loader-source-bundle.tar.gz',loader['source_bundle_sha256']))
        else:
            source=args.loader_dir/'upstream-source.tar.gz'
            items.append((source,'/data/orbisdesk/process-p005/loader-source.tar.gz',loader['pins']['elfldr']['sha256']))
    for path,remote,expected in items:
        if digest(path)!=expected:raise RuntimeError('Artifact hash differs: '+str(path))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_dir=ROOT/'reports'/stem/('ftp-'+stamp);report_dir.mkdir(parents=True)
    result={'build':build,'host':args.host,'port':args.port,'execution_performed':False,'transfers':[],'removed_previous':[]}
    ftp=ftplib.FTP();ftp.connect(args.host,args.port,timeout=30);ftp.login()
    def ensure(directory):
        current=''
        for part in directory.split('/'):
            if not part:continue
            current+='/'+part
            try:ftp.mkd(current)
            except ftplib.error_perm as error:
                # Verify it is an existing directory rather than suppressing arbitrary errors.
                ftp.cwd(current);ftp.cwd('/')
    def remote_hash(remote):
        h=hashlib.sha256();ftp.retrbinary('RETR '+remote,h.update);return h.hexdigest()
    try:
        for path,remote,expected in items:
            ensure(str(Path(remote).parent).replace('\\','/'))
            with path.open('rb') as src:ftp.storbinary('STOR '+remote,src)
            actual=remote_hash(remote)
            if actual!=expected:raise RuntimeError('FTP readback hash mismatch: '+remote)
            result['transfers'].append({'remote':remote,'local':str(path.relative_to(ROOT)),
                                        'sha256':actual,'bytes':path.stat().st_size,'verified':True})
            print('verified '+remote,flush=True)
        # User requested keeping only the newest diagnostic PKG. Never touch the product PKG.
        for previous in ('P001','P002','P003','P004','P005','P007','P009','P012','P013'):
            if previous==build:continue
            prior=ROOT/'out'/('process-hardware-'+previous.lower())/'manifest.json'
            if not prior.exists():continue
            spec=json.loads(prior.read_text());remote='/data/pkg/'+Path(spec['package']).name
            try:actual=remote_hash(remote)
            except ftplib.error_perm:continue
            if actual!=spec['package_sha256']:continue
            ftp.delete(remote);result['removed_previous'].append(remote)
        result['status']='staged_hash_verified'
    finally:
        (report_dir/'transfer.json').write_text(json.dumps(result,indent=2)+'\n')
        ftp.close()
    (ROOT/'out'/stem/'ftp-handoff.json').write_text(json.dumps(result,indent=2)+'\n')
    print(report_dir/'transfer.json')
if __name__=='__main__':main()
