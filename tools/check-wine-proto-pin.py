#!/usr/bin/env python3
"""Verify native/pop_wine_proto.h still matches the pinned wine server protocol.

The Phase B slim client (native/pop_wine_join_core.h) speaks the wineserver wire protocol with hand-written
struct layouts in native/pop_wine_proto.h, because include/wine/server_protocol.h cannot be included alone
(it pulls in the full Windows headers). This check re-reads the pinned header and asserts the version and the
REQ_* enum ordinals the client bakes in are still correct, so a wine bump that changes them fails loudly
instead of silently breaking the handshake. The client also checks the version at runtime against what the
server sends; this is the build-time guard."""
import pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
proto=(ROOT/'native/pop_wine_proto.h').read_text()
header=(ROOT/'.deps/wine/source/include/wine/server_protocol.h').read_text()

def proto_def(name):
    m=re.search(r'#define\s+%s\s+(\d+)'%name,proto)
    if not m:sys.exit('pop_wine_proto.h: missing '+name)
    return int(m.group(1))

# wine's authoritative values
mv=re.search(r'#define\s+SERVER_PROTOCOL_VERSION\s+(\d+)',header)
if not mv:sys.exit('server_protocol.h: no SERVER_PROTOCOL_VERSION')
wine_version=int(mv.group(1))
names=re.findall(r'REQ_(\w+)',header[header.index('enum request'):])
order={}
seen=set()
for n in names:
    if n=='NB_REQUESTS':break
    if n in seen:continue
    seen.add(n);order[n]=len(order)

errors=[]
if proto_def('POP_SERVER_PROTOCOL_VERSION')!=wine_version:
    errors.append('version: proto %d != wine %d'%(proto_def('POP_SERVER_PROTOCOL_VERSION'),wine_version))
import re as _re
for macro,req in [(m,m[len('POP_REQ_'):]) for m in _re.findall(r'#define\s+(POP_REQ_\w+)',proto)]:
    if req not in order:errors.append('wine enum missing REQ_'+req);continue
    if proto_def(macro)!=order[req]:
        errors.append('%s: proto %d != wine ordinal %d'%(macro,proto_def(macro),order[req]))

if errors:
    print('check-wine-proto-pin: DRIFT\n  '+'\n  '.join(errors));sys.exit(1)
print('check-wine-proto-pin OK: version %d, %d request ordinals match'%(
      wine_version,len(_re.findall(r'#define\s+POP_REQ_\w+',proto))))
