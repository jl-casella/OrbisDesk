#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify a preserved build and exact guest ELF in each runtime archive."""
import argparse,hashlib,json,pathlib,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('snapshot',type=pathlib.Path)
parser.add_argument('--run',type=pathlib.Path,action='append',default=[]);args=parser.parse_args()
snapshot=args.snapshot.resolve();evidence=json.loads((snapshot/'evidence.json').read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
for relative,entry in evidence['files'].items():
    path=(snapshot/relative).resolve()
    if not path.is_relative_to(snapshot) or sha(path.read_bytes())!=entry['sha256']:
        raise SystemExit('Evidence mismatch: '+relative)
elf_sha=evidence['files']['build/wine-boot/eboot.bin']['sha256'];runs=[]
for directory in args.run:
    report=json.loads((directory/'report.json').read_text())
    with tarfile.open(directory/'runtime.tar.gz','r:gz') as archive:
        guest=archive.extractfile('runtime/guest/eboot.bin')
        actual=sha(guest.read())
    if actual!=report['elf_sha256'] or actual!=elf_sha:raise SystemExit('Runtime ELF mismatch: '+str(directory))
    if report['Wine_booted'] or report.get('windows_execution_verified'):raise SystemExit('Unexpected successful startup claim')
    runs.append({'path':str(directory),'elf_matches':True})
result={'status':'passed','scope':'Artifact integrity only; startup remains blocked','files_verified':len(evidence['files']),
        'runs':runs,'Wine_booted':False,'hardware_status':'pending'}
(snapshot/'evidence-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
