# SPDX-License-Identifier: LGPL-2.1-or-later
"""Resolve Wine import-library aliases and PE forwarded-export module names."""
import re
import struct


def configured_pe_targets(makefile):
    # Wine also builds PE wrappers with legacy names such as krnl386.exe16.
    suffix = r'(?:dll|exe|sys|drv|ocx|cpl|acm|ax|ds|dll16|drv16|exe16)'
    pattern = r'^((?:dlls|programs)/[^/ :]+/(i386|x86_64)-windows/([^/ :]+\.' + suffix + r')):'
    return {(m[2], m[3].lower()): m[1] for m in re.finditer(pattern, makefile, re.M)}


def import_library_alias(definition):
    text = definition.replace('\\\n', ' ')
    match = re.search(r'^IMPORTLIB[ \t]*=[ \t]*([^\r\n#]*)', text, re.M)
    if not match:
        return None
    name = match[1].strip().lower()
    if not name:
        return None
    if len(name.split()) != 1 or '$' in name or '/' in name or '\\' in name:
        raise ValueError('Unsupported Wine IMPORTLIB: ' + name)
    return name


def register_alias(aliases, arch, alias, module):
    if alias is None:
        return
    key = (arch, alias.lower())
    module = module.lower()
    if key in aliases and aliases[key] != module:
        raise ValueError('Ambiguous Wine import library: ' + repr(key))
    aliases[key] = module


def resolve_import_library(name, arch, aliases):
    name = name.lower()
    if '$' in name:
        raise ValueError('Unexpanded Wine import library: ' + name)
    if (arch, name) in aliases:
        return aliases[(arch, name)]
    return name if '.' in name else name + '.dll'


def forwarded_modules(path):
    """Read real PE export forwarders, whose providers are not normal imports."""
    data = path.read_bytes()
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Not a PE image: ' + str(path))
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if pe + 24 > len(data) or data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Invalid PE header: ' + str(path))
    sections = struct.unpack_from('<H', data, pe + 6)[0]
    optional = pe + 24
    size = struct.unpack_from('<H', data, pe + 20)[0]
    if size < 64 or optional + size + sections * 40 > len(data):
        raise ValueError('Truncated PE headers: ' + str(path))
    magic = struct.unpack_from('<H', data, optional)[0]
    if magic not in (0x10b, 0x20b):
        raise ValueError('Unsupported PE optional header')
    directory = optional + (112 if magic == 0x20b else 96)
    if directory + 8 > optional + size:
        raise ValueError('Missing PE data directory')
    export_rva, export_size = struct.unpack_from('<II', data, directory)
    if not export_rva:
        return []
    header_size = struct.unpack_from('<I', data, optional + 60)[0]

    def offset(rva, width):
        if rva < header_size and rva + width <= min(header_size, len(data)):
            return rva
        for index in range(sections):
            section = optional + size + index * 40
            _, base, raw, pointer = struct.unpack_from('<IIII', data, section + 8)
            delta = rva - base
            if 0 <= delta and delta + width <= raw and pointer + delta + width <= len(data):
                return pointer + delta
        raise ValueError('Unmapped PE export RVA: ' + str(path))

    if export_size < 40:
        raise ValueError('Truncated PE export directory')
    at = offset(export_rva, 40)
    count = struct.unpack_from('<I', data, at + 20)[0]
    table_rva = struct.unpack_from('<I', data, at + 28)[0]
    if not count:
        return []
    table = offset(table_rva, count * 4)
    modules = set()
    for index in range(count):
        rva = struct.unpack_from('<I', data, table + index * 4)[0]
        if not export_rva <= rva < export_rva + export_size:
            continue
        width = min(4096, export_rva + export_size - rva)
        at = offset(rva, width)
        end = data.find(b'\0', at, at + width)
        if end < 0:
            raise ValueError('Unterminated PE export forwarder')
        text = data[at:end].decode('ascii')
        module, separator, function = text.rpartition('.')
        if not separator or not module or not function or '/' in module or '\\' in module:
            raise ValueError('Invalid PE export forwarder: ' + text)
        modules.add(module.lower())
    return sorted(modules)
