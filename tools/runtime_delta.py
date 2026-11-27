#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Publish a verified PE runtime delta without overwriting a mapped file inode.

Backups stay beside each destination for explicit rollback. No directory scan,
installation, execution or deletion of console data is performed.
"""
import hashlib
import io
import posixpath
import re


def remote_sha(ftp, path):
    digest=hashlib.sha256()
    ftp.retrbinary('RETR '+path,digest.update)
    return digest.hexdigest()


def _check_path(path, token):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',token):
        raise ValueError('Invalid delta token')
    roots=('/data/wine/lib/wine/','/data/wine-prefix/drive_c/windows/')
    if (not path.startswith(roots) or posixpath.normpath(path)!=path or
            any(c in path for c in '\r\n') or not path.lower().endswith(('.dll','.exe'))):
        raise ValueError('Not a canonical PE runtime destination')


def _listed_sha(ftp,path):
    # A 550 from RETR/SIZE is not proof of absence: it can mean permissions.
    names={posixpath.basename(x.rstrip('/')) for x in ftp.nlst(posixpath.dirname(path))}
    return remote_sha(ftp,path) if posixpath.basename(path) in names else None


def _check_record(record):
    target=record['remote']
    prefix=target+'.before-'
    if not record['backup'].startswith(prefix):
        raise ValueError('Invalid delta backup')
    token=record['backup'][len(prefix):]
    _check_path(target,token)
    if record['temporary']!=target+'.stage-'+token:
        raise ValueError('Invalid delta staging path')


def recover_pe(ftp, record):
    """Reconcile a journal after reconnect, including an unacknowledged rename."""
    _check_record(record)
    target=record['remote']
    current=_listed_sha(ftp,target)
    if current==record['old_sha256']:
        record['state']='original-restored'
        return
    backup=_listed_sha(ftp,record['backup'])
    if backup!=record['old_sha256']:
        raise RuntimeError('No verified original for runtime recovery: '+target)
    if current==record['new_sha256']:
        record['state']='published'
        rollback_pe(ftp,record)
    elif current is None:
        ftp.rename(record['backup'],target)
        if remote_sha(ftp,target)!=record['old_sha256']:
            raise RuntimeError('Recovery read-back mismatch: '+target)
        record['state']='original-restored'
    else:
        raise RuntimeError('Unexpected runtime during recovery: '+target)


def rollback_pe(ftp, record):
    """Restore only our exact verified publication; retain both file versions."""
    _check_record(record)
    if record['state']!='published':
        return
    target=record['remote']
    if remote_sha(ftp,target)!=record['new_sha256']:
        raise RuntimeError('Runtime changed after publication; refusing rollback: '+target)
    if remote_sha(ftp,record['backup'])!=record['old_sha256']:
        raise RuntimeError('Backup differs; refusing rollback: '+target)
    rejected=record['temporary']+'.rolled-back'
    ftp.rename(target,rejected)
    try:
        ftp.rename(record['backup'],target)
    except Exception:
        ftp.rename(rejected,target)
        raise
    if remote_sha(ftp,target)!=record['old_sha256']:
        raise RuntimeError('Rollback read-back mismatch: '+target)
    record['state']='rolled-back'
    record['retained_new']=rejected


def publish_pe(ftp, local, remote, expected_old, expected_new, token, journal=None):
    """Stage/read back, preserve old inode, rename, chmod and read back again."""
    _check_path(remote,token)
    data=local.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_new:
        raise RuntimeError('Local delta differs from its manifest')
    old=remote_sha(ftp,remote)
    record=dict(remote=remote,old_sha256=old,new_sha256=expected_new,bytes=len(data),
                backup=remote+'.before-'+token,temporary=remote+'.stage-'+token,state='present',
                mode=0o666 if remote.startswith('/data/wine-prefix/') else 0o644)
    if old==expected_new:
        record['readback_verified']=True
        return record
    if old!=expected_old:
        raise RuntimeError('Unexpected installed runtime; refusing replacement: '+remote)
    # Token names must be new. Never let an FTP implementation overwrite an
    # existing backup/staging file through its rename behavior.
    existing={posixpath.basename(x.rstrip('/')) for x in ftp.nlst(posixpath.dirname(remote))}
    for path in (record['backup'],record['temporary'],record['temporary']+'.rolled-back',record['temporary']+'.failed'):
        if posixpath.basename(path) in existing:
            raise RuntimeError('Delta recovery path already exists: '+path)
    # Persist the recovery coordinates before any mutation, so a caller can
    # reconnect and inspect reality if a rename's reply is lost.
    if journal:journal(record)
    ftp.storbinary('STOR '+record['temporary'],io.BytesIO(data),blocksize=1<<20)
    if remote_sha(ftp,record['temporary'])!=expected_new:
        raise RuntimeError('Staged runtime read-back mismatch: '+remote)
    # Recheck after upload in case another deployment changed the destination.
    if remote_sha(ftp,remote)!=expected_old:
        raise RuntimeError('Runtime changed while staging: '+remote)
    ftp.rename(remote,record['backup'])
    try:
        ftp.rename(record['temporary'],remote)
    except Exception:
        ftp.rename(record['backup'],remote)
        raise
    record['state']='published'
    try:
        # Match upload-hardware.py: the live Wine prefix remains writable,
        # while the external library copy only needs read access.
        ftp.sendcmd('SITE CHMOD %o '%record['mode']+remote)
        if remote_sha(ftp,remote)!=expected_new:
            raise RuntimeError('Published runtime read-back mismatch: '+remote)
    except Exception:
        # If the new file itself cannot be verified, preserve it and restore the
        # verified backup rather than mutating either payload in place.
        ftp.rename(remote,record['temporary']+'.failed')
        ftp.rename(record['backup'],remote)
        if remote_sha(ftp,remote)!=expected_old:
            raise RuntimeError('Failed publication and rollback verification: '+remote)
        raise
    record['readback_verified']=True
    return record
