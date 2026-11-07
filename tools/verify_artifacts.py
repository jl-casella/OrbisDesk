#!/usr/bin/env python3
"""Check target architectures and reject duplicate OELF load segments."""
import argparse
import json
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]


def verify_elf(path):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 62:
        raise ValueError(f"Not an x86-64 little-endian ELF: {path}")
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    loads = set()
    for i in range(count):
        header = struct.unpack_from("<IIQQQQQQ", data, offset + size * i)
        if header[0] == 1:
            key = (header[3], header[6])
            if key in loads:
                raise ValueError(f"Duplicate PT_LOAD in {path}")
            loads.add(key)
    if not loads:
        raise ValueError(f"ELF has no loadable segments: {path}")
    return {"architecture": "x86_64", "load_segments": len(loads)}


def verify_pe32(path):
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"Not PE: {path}")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"Invalid PE header: {path}")
    machine = struct.unpack_from("<H", data, pe + 4)[0]
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    if machine != 0x14c or magic != 0x10b:
        raise ValueError(f"Fixture is not i386 PE32: {path}")
    return {"architecture": "i386", "format": "PE32"}


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--fixtures-only",action="store_true");args=parser.parse_args()
    results = {name: verify_elf(ROOT / "out" / name) for name in (() if args.fixtures_only else ("probe.elf", "probe.oelf"))}
    results.update({name: verify_pe32(ROOT / "out" / name) for name in ("console32.exe", "console32-bare.exe", "gdi32.exe", "minimal32.exe", "minimal4k32.exe",
                                                                  "imports32.exe", "testmath.dll", "nested.dll", "lifecycle.dll",
                                                                  "lifecycle-peer.dll", "lifecycle-fail.dll", "lifecycle-host.exe", "process32.exe")})
    (ROOT / "out/verification.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
