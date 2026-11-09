# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verify deliberate overlays of identical Wine modules from multiple producers."""
import hashlib
import struct


def verify_module_copy(arch, name, source, data, origin, expected_sha=None):
    expected = {'i386-windows': (0x14c, 0x10b), 'x86_64-windows': (0x8664, 0x20b)}[arch]
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError(f'{origin}: {name} is not a PE image')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if pe + 26 > len(data) or data[pe:pe + 4] != b'PE\0\0':
        raise ValueError(f'{origin}: {name} has an invalid PE header')
    actual = (struct.unpack_from('<H', data, pe + 4)[0],
              struct.unpack_from('<H', data, pe + 24)[0])
    if actual != expected:
        raise ValueError(f'{origin}: {name} has the wrong architecture for {arch}')
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha is not None and digest != expected_sha:
        raise ValueError(f'{origin}: {name} differs from its provider manifest')
    if digest != hashlib.sha256(source.read_bytes()).hexdigest():
        raise ValueError(f'{origin}: {name} differs from the configured Wine build')
    return {'origin': origin, 'sha256': digest, 'bytes': len(data), 'machine': actual[0]}
