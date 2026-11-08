"""Derive the existing OpenOrbis libc selection without modifying the SDK."""
import hashlib
from pathlib import Path
import shutil
import subprocess


def derive_libc(original, destination, boot=False):
    original, destination = Path(original), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, destination)
    removed = ['lstat.lo']
    if boot:
        removed += ['socketpair.lo', 'sendmsg.lo', 'recvmsg.lo', 'poll.lo',
                    'sigaction.lo', 'sigprocmask.lo', 'pthread_sigmask.lo',
                    'fcntl.lo', 'readlink.lo', 'rename.lo']
    subprocess.run(['ar', 'd', str(destination), *removed], check=True)
    return {'original_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
            'derived_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            'removed_members': removed, 'provider': 'libkernel imports instead of SDK fallback stubs'}
