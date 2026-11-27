#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify inode-preserving PE publication, refusal and rollback behavior."""
import ftplib
import hashlib
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from runtime_delta import publish_pe,rollback_pe,recover_pe


class FTP:
    def __init__(self,path,old):
        self.files={path:old};self.fail_commit=False;self.fail_chmod=False
    def retrbinary(self,command,write):
        path=command.removeprefix('RETR ')
        if path not in self.files:raise ftplib.error_perm('550 absent')
        write(self.files[path])
    def size(self,path):
        if path not in self.files:raise ftplib.error_perm('550 absent')
        return len(self.files[path])
    def nlst(self,path):
        return [p for p in self.files if p.rsplit('/',1)[0]==path]
    def storbinary(self,command,stream,blocksize):
        self.files[command.removeprefix('STOR ')]=stream.read()
    def rename(self,a,b):
        if self.fail_commit and '.stage-' in a:
            self.fail_commit=False;raise ftplib.error_perm('550 injected commit failure')
        assert a in self.files and b not in self.files
        self.files[b]=self.files.pop(a)
    def sendcmd(self,command):
        assert command.startswith(('SITE CHMOD 644 ','SITE CHMOD 666 '))
        if self.fail_chmod:raise ftplib.error_perm('550 injected chmod failure')
        return '200 ok'


with tempfile.TemporaryDirectory() as tmp:
    target='/data/wine-prefix/drive_c/windows/syswow64/winevulkan.dll'
    old=b'old PE';new=b'new PE';old_sha=hashlib.sha256(old).hexdigest();new_sha=hashlib.sha256(new).hexdigest()
    local=Path(tmp)/'delta.dll';local.write_bytes(new)
    ftp=FTP(target,old);mapped_old=ftp.files[target]
    record=publish_pe(ftp,local,target,old_sha,new_sha,'test')
    assert record['readback_verified'] and record['state']=='published'
    assert record['mode']==0o666
    assert ftp.files[target]==new and mapped_old is ftp.files[record['backup']] and mapped_old==old
    rollback_pe(ftp,record);assert ftp.files[target]==old and record['state']=='rolled-back'
    ftp=FTP(target,old);ftp.fail_commit=True
    try:publish_pe(ftp,local,target,old_sha,new_sha,'fail')
    except ftplib.error_perm:pass
    else:raise AssertionError('commit failure hidden')
    assert ftp.files[target]==old
    ftp=FTP(target,old);ftp.fail_chmod=True
    try:publish_pe(ftp,local,target,old_sha,new_sha,'chmod')
    except ftplib.error_perm:pass
    else:raise AssertionError('chmod failure hidden')
    assert ftp.files[target]==old
    # A connection may drop after the server moved the old inode but before
    # the client received its reply. Recovery uses hashes, not the last reply.
    ftp=FTP(target,old);journal=[]
    record=publish_pe(ftp,local,target,old_sha,new_sha,'recover',lambda r:journal.append(dict(r)))
    assert journal
    ftp.files.pop(target)
    recover_pe(ftp,journal[0]);assert ftp.files[target]==old
    ftp=FTP(target,old);journal=[]
    record=publish_pe(ftp,local,target,old_sha,new_sha,'recover2',lambda r:journal.append(dict(r)))
    recover_pe(ftp,journal[0]);assert ftp.files[target]==old
    ftp=FTP(target,b'other installed PE')
    try:publish_pe(ftp,local,target,old_sha,new_sha,'refuse')
    except RuntimeError:pass
    else:raise AssertionError('unexpected runtime replaced')
    assert len(ftp.files)==1
    ftp=FTP(target,old)
    try:publish_pe(ftp,local,'/data/user-documents/x.dll',old_sha,new_sha,'refuse')
    except ValueError:pass
    else:raise AssertionError('unrelated destination accepted')
print('PASS: PE stage/readback, old mapped inode retained, rename/chmod rollback and unexpected-runtime refusal')
