# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fake SELF helpers on top of the OpenOrbis create-fself output."""
import hashlib,struct

ET_SCE_EXEC=0xFE00
ET_SCE_EXEC_ASLR=0xFE10

def set_exec_type(oelf_path,self_path):
    """Make an eboot ET_SCE_EXEC (no ASLR), so the kernel loads it at its link address.

    create-fself has no option for the type and always writes ET_SCE_EXEC_ASLR; the SDK's
    make_fself.py is Python 2 only. The fake SELF holds a copy of the OELF's ELF header (after
    the entry table) and the SHA-256 of the whole OELF; the segment digests do not cover the
    header. Both are changed, each checked first. B006 stage b (0x1100000000) ran this way.
    Returns the changed OELF bytes, for the caller to keep beside the SELF."""
    oelf=bytearray(oelf_path.read_bytes());signed=bytearray(self_path.read_bytes())
    kind,=struct.unpack_from('<H',oelf,0x10)
    if kind!=ET_SCE_EXEC_ASLR:raise SystemExit('%s e_type 0x%x, expected 0x%x'%(oelf_path.name,kind,ET_SCE_EXEC_ASLR))
    entries,=struct.unpack_from('<H',signed,0x18);header=0x20+entries*0x20
    if signed[header:header+0x40]!=oelf[:0x40]:raise SystemExit('%s: ELF header copy not at 0x%x'%(self_path.name,header))
    old=hashlib.sha256(oelf).digest()
    if signed.count(old)!=1:raise SystemExit('%s: OELF digest found %d times'%(self_path.name,signed.count(old)))
    digest_at=signed.find(old)
    struct.pack_into('<H',oelf,0x10,ET_SCE_EXEC);struct.pack_into('<H',signed,header+0x10,ET_SCE_EXEC)
    signed[digest_at:digest_at+32]=hashlib.sha256(oelf).digest()
    self_path.write_bytes(signed)
    return bytes(oelf)

def load_segments(elf_path):
    """(vaddr, memsz) of each PT_LOAD, in order."""
    data=elf_path.read_bytes();phoff,=struct.unpack_from('<Q',data,0x20);phent,phnum=struct.unpack_from('<HH',data,0x36)
    loads=[]
    for i in range(phnum):
        at=phoff+i*phent;kind,=struct.unpack_from('<I',data,at)
        if kind==1:loads.append((struct.unpack_from('<Q',data,at+16)[0],struct.unpack_from('<Q',data,at+40)[0]))
    return loads
