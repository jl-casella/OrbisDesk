#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Upload tools/build-pop-wine-child.py's outputs to the console's /data/orbisdesk and verify them.

GoldHEN's FTP needs two precautions here (docs/POP_SEPARATE_PROCESS.md):
- Overwriting a SELF/PRX in place left the console loading the previous build (2026-11-12): each remote file is
  deleted before it is stored.
- RETR of a SELF/PRX returns the decrypted ELF, not the stored bytes: a PRX is verified by finding a slice of its
  ELF's text in the decrypted image; other files by sha256 of the readback.
Writes reports/pop-separate/transfers/<UTC>.json. Never touches /data/wine or the prefix.
"""
import argparse, datetime, ftplib, hashlib, io, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/pop-wine-child'
ELF_OF = {'pop-wine-child.prx': 'pop_wine_child.elf', 'pop-prx-probe.prx': 'pop_prx_probe.elf'}
STALE = ('process-p014/separate-d1.txt', 'process-p014/separate-d2.txt', 'process-p014/separate-launcher.txt',
         'process-p014/separate-game.txt', 'process-p014/wine-child.jsonl', 'process-p014/prx-probe.txt')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=2121)
    args = parser.parse_args()
    manifest = json.loads((WORK / 'manifest.json').read_text())
    remote_dir = manifest['remote_dir']
    ftp = ftplib.FTP(); ftp.connect(args.host, args.port, timeout=120); ftp.login(); ftp.set_pasv(True)
    record = {'host': args.host, 'files': {}}
    for name, entry in manifest['outputs'].items():
        data = (WORK / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise SystemExit(name + ' differs from build/pop-wine-child/manifest.json')
        remote = remote_dir + '/' + name
        try:
            ftp.delete(remote)
        except ftplib.error_perm:
            pass
        ftp.storbinary('STOR ' + remote, io.BytesIO(data))
        readback = bytearray(); ftp.retrbinary('RETR ' + remote, readback.extend)
        if name in ELF_OF:
            elf = (WORK / ELF_OF[name]).read_bytes()
            ok = len(readback) > len(data) and elf[0x4000:0x4000 + 0x10000] in readback
            how = 'decrypted text slice'
        else:
            ok = hashlib.sha256(readback).hexdigest() == entry['sha256']
            how = 'sha256'
        record['files'][name] = {'remote': remote, 'sha256': entry['sha256'], 'verified': ok, 'by': how}
        print('verified' if ok else 'MISMATCH', remote, how)
    for stale in STALE:
        try:
            ftp.delete(remote_dir + '/' + stale)
        except ftplib.error_perm:
            pass
    ftp.quit()
    out = ROOT / 'reports/pop-separate/transfers' / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print(out)
    if not all(f['verified'] for f in record['files'].values()):
        raise SystemExit('some files did not verify')


if __name__ == '__main__':
    main()
