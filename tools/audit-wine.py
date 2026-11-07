#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Inventory actual Wine PE requirements; this is not an alternative loader."""
import hashlib
import json
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]


def inventory(path):
    data = path.read_bytes()
    def u16(at): return struct.unpack_from('<H', data, at)[0]
    def u32(at): return struct.unpack_from('<I', data, at)[0]
    pe = u32(0x3c)
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0' or u16(pe+4) != 0x14c or u16(pe+24) != 0x10b:
        raise ValueError('Expected i386 PE32')
    opt = pe+24
    table = opt+u16(pe+20)
    sections = []
    for i in range(u16(pe+6)):
        s = table+i*40
        sections.append({'name': data[s:s+8].split(b'\0')[0].decode('ascii'),
                         'rva': u32(s+12), 'bytes': u32(s+8), 'raw_bytes': u32(s+16),
                         'offset': u32(s+20), 'flags': u32(s+36)})
    def at(rva, size=1):
        for s in sections:
            delta = rva-s['rva']
            if delta >= 0 and delta+size <= s['raw_bytes'] and s['offset']+delta+size <= len(data):
                return s['offset']+delta
        raise ValueError(f'Unbacked RVA {rva:#x}')
    def text(rva):
        start = at(rva)
        stop = data.find(b'\0', start, min(start+4096, len(data)))
        if stop < 0: raise ValueError('Unterminated PE string')
        at(rva, stop-start+1)
        return data[start:stop].decode('ascii')
    directories = [(u32(opt+96+i*8), u32(opt+100+i*8)) for i in range(u32(opt+92))]
    imports = []
    rva, size = directories[1]
    if rva:
        for i in range(size//20):
            d = at(rva+i*20, 20)
            lookup, stamp, chain, name, iat = struct.unpack_from('<IIIII', data, d)
            if not (lookup|stamp|chain|name|iat): break
            symbols = []
            for n in range(65536):
                value = u32(at((lookup or iat)+n*4, 4))
                if not value: break
                symbols.append({'ordinal': value&0xffff} if value&0x80000000 else {'name': text(value+2)})
            else: raise ValueError('Import table too long')
            imports.append({'module': text(name), 'symbols': symbols})
    exports = {'slots': 0, 'named': 0, 'forwarders': [], 'data_exports': 0}
    rva, size = directories[0]
    if rva:
        e = at(rva, 40)
        exports['slots'], exports['named'] = u32(e+20), u32(e+24)
        eat = u32(e+28)
        for i in range(exports['slots']):
            target = u32(at(eat+i*4, 4))
            if not target: continue
            if rva <= target < rva+size:
                exports['forwarders'].append(text(target))
            elif not any(s['rva'] <= target < s['rva']+s['bytes'] and s['flags']&0x20000000 for s in sections):
                exports['data_exports'] += 1
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'preferred_base': u32(opt+28), 'image_bytes': u32(opt+56), 'entry_rva': u32(opt+16),
            'sections': sections, 'directories': directories, 'imports': imports, 'exports': exports,
            'import_count': sum(len(item['symbols']) for item in imports)}


def main():
    manifest = json.loads((ROOT/'out/wine/wine-runtime-manifest.json').read_text())
    expected = json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']
    if manifest['wine']['commit'] != expected: raise SystemExit('Wine revision mismatch')
    modules = {}
    for module in manifest['modules']:
        result = inventory(ROOT/'out/wine'/module['path'])
        if result['sha256'] != module['sha256']: raise SystemExit('Wine DLL hash mismatch')
        modules[module['name']] = result
    report = {'schema_version': 1, 'wine_commit': expected, 'kind': 'host inventory, not execution',
              'modules': modules, 'hardware_status': 'pending'}
    (ROOT/'out/wine-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    for name, module in modules.items():
        print(name, module['bytes'], 'bytes;', module['import_count'], 'imports;', module['exports']['slots'], 'export slots')


if __name__ == '__main__':
    main()
