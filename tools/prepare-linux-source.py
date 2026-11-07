#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Normalize AWK build inputs from a Windows checkout without changing blobs."""
import hashlib,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
source=ROOT/'.deps/shadPS4-fork/externals/libpng';records=[]
for relative in ('scripts/options.awk','scripts/pnglibconf.dfa','png.h','pngconf.h'):
    path=source/relative;before=path.read_bytes();after=before.replace(b'\r\n',b'\n')
    blob=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+relative])
    if after!=blob:raise SystemExit('Unexpected libpng source content: '+relative)
    if before!=after:path.write_bytes(after)
    records.append({'path':relative,'before_sha256':hashlib.sha256(before).hexdigest(),
                    'normalized_sha256':hashlib.sha256(after).hexdigest(),'matches_committed_blob':True})
(ROOT/'build/increment11-source-normalization.json').write_text(json.dumps(records,indent=2)+'\n')
print('libpng AWK input blobs verified and normalized')
