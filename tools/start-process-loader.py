#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Identify the external loader, optionally send its verified bootstrap to GoldHEN BinLoader."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import socket
import time

ROOT=Path(__file__).resolve().parents[1]
def identify(host,expected_recipe=None):
    connected=False
    try:
        with socket.create_connection((host,9021),timeout=2) as connection:
            connected=True
            # P011 handles this identity-only request; old elfldr rejects it without spawning.
            connection.sendall(b'ODI?');connection.shutdown(socket.SHUT_WR)
            response=bytearray()
            while len(response)<1024:
                part=connection.recv(1024-len(response))
                if not part:break
                response.extend(part)
                if b'\n' in response:break
        decoded=response.decode('ascii','replace')
        try:identity=json.loads(decoded)
        except ValueError:identity={}
        modern=identity.get('service')=='orbisdesk-loader' and identity.get('protocol')==1 and isinstance(identity.get('pid'),int)
        legacy=b'[elfldr.elf] Unknown payload format' in response
        return {'connected':True,'identified':modern or legacy,'identity':identity if modern else None,
                'recipe_matches':not expected_recipe or modern and identity.get('recipe')==expected_recipe,
                'legacy_identity_only':legacy,'response':decoded}
    except OSError as error:return {'connected':connected,'identified':False,'recipe_matches':False,'error':str(error)}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True)
    parser.add_argument('--artifact-dir',type=Path,default=ROOT/'out/process-loader',help='Directory containing the verified bootstrap and its manifest')
    parser.add_argument('--payload-format',choices=['elf','bin'],default='elf',help='GoldHEN rejected our headerless BIN; use the ELF by default')
    parser.add_argument('--firmware',choices=['12.50','12.52'],help='Operator-reported console firmware; required with --start, not automatically detected')
    parser.add_argument('--start',action='store_true',help='Execute the audited bootstrap through GoldHEN 9090; changes kernel/session state')
    parser.add_argument('--replace',action='store_true',help='With --start: send even if a loader answers (a new socksrv ends the older elfldr.elf first), e.g. to load P010')
    args=parser.parse_args()
    if args.start and not args.firmware:parser.error('--start requires an explicit --firmware; do not infer the console version')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=ROOT/'reports'/(args.artifact_dir.name if args.artifact_dir.name.startswith('process-loader-p') else 'process-hardware-p005')/('loader-'+stamp);directory.mkdir(parents=True)
    manifest=json.loads((args.artifact_dir/'manifest.json').read_text())
    expected=manifest.get('recipe_sha256')
    result={'classification':'physical_console_network_observation','host':args.host,'expected_recipe':expected,
            'bootstrap_sent':False,'native_child_verified':False,'before':identify(args.host,expected)}
    try:
        if result['before']['identified'] and not (args.start and args.replace):
            result['status']='existing_loader_identified' if result['before']['recipe_matches'] else 'loader_identity_mismatch'
        elif result['before']['connected'] and not result['before']['identified']:result['status']='unknown_endpoint_not_replaced'
        elif not args.start:result['status']='loader_not_available'
        else:
            name='elfldr.'+args.payload_format
            path=args.artifact_dir/name;raw=path.read_bytes()
            sha=hashlib.sha256(raw).hexdigest()
            if sha!=manifest['artifacts'][name]['sha256']:raise RuntimeError('Bootstrap hash mismatch')
            result['bootstrap_sha256']=sha;result['manifest']=manifest
            result['bootstrap_format']=args.payload_format
            result['reported_console']={'firmware':args.firmware,'firmware_source':'operator_cli','GoldHEN':'2.4; beta suffix unknown'}
            with socket.create_connection((args.host,9090),timeout=5) as connection:
                connection.sendall(raw);connection.shutdown(socket.SHUT_WR)
            result['bootstrap_sent']=True;result['bootstrap_bytes']=len(raw)
            result['status']='bootstrap_sent_loader_not_identified'
            for _ in range(8):
                time.sleep(.5);result['after']=identify(args.host,expected)
                if result['after']['identified'] and result['after']['recipe_matches']:
                    result['status']='loader_identified_after_bootstrap';break
    except Exception as error:
        result['status']='failed';result['error']=str(error)
    finally:
        (directory/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='manifest'},indent=2))
    print(directory/'report.json')
    return 0 if result['status'] in ('existing_loader_identified','loader_identified_after_bootstrap') else 1
if __name__=='__main__':raise SystemExit(main())
