# SPDX-License-Identifier: LGPL-2.1-or-later
"""Validate and stage the portable prefix without following archive links."""
import hashlib
import io
import json
import pathlib
import shutil
import struct
import tarfile

REGISTRY = ('system.reg', 'user.reg', 'userdef.reg')
PE_FILES = {'drive_c/orbis/console32.exe': 0x14c}
for directory, machine, modules in (
        ('system32', 0x8664, ('ntdll', 'kernel32', 'kernelbase', 'wow64', 'wow64win', 'apisetschema')),
        ('syswow64', 0x14c, ('ntdll', 'kernel32', 'kernelbase'))):
    PE_FILES.update({f'drive_c/windows/{directory}/{name}.dll': machine for name in modules})

def digest(data):
    return hashlib.sha256(data).hexdigest()

def pe_machine(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Invalid DOS header')
    offset = struct.unpack_from('<I', data, 60)[0]
    if offset > len(data) - 26 or data[offset:offset+4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    machine = struct.unpack_from('<H', data, offset+4)[0]
    magic = struct.unpack_from('<H', data, offset+24)[0]
    if (machine, magic) not in ((0x14c, 0x10b), (0x8664, 0x20b)):
        raise ValueError('Invalid PE machine/optional header')
    return machine

def validate_package(directory, wine_commit):
    directory = pathlib.Path(directory).resolve()
    manifest_bytes = (directory/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get('schema_version') != 1 or manifest.get('status') != 'packaged-for-preflight'
            or manifest.get('wine_commit') != wine_commit
            or manifest.get('native_console32_verified') is not True
            or manifest.get('placement') != '/data/wine-prefix'
            or manifest.get('exe', '').replace('\\\\', '\\') != 'C:\\orbis\\console32.exe'):
        raise ValueError('Prefix manifest/revision is incompatible')
    archive = (directory/'prefix.tar.gz').read_bytes()
    if digest(archive) != manifest.get('archive_sha256'):
        raise ValueError('Prefix archive hash mismatch')
    entries = manifest['entries']
    for name in (*REGISTRY, *PE_FILES):
        if entries.get(name, {}).get('type') != 'file':
            raise ValueError('Required prefix file missing: '+name)
    if any(pathlib.PurePosixPath(name).name.lower() == 'wow64cpu.dll' for name in entries):
        raise ValueError('Host CPU provider is forbidden')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as stream:
        seen = set()
        for member in stream:
            path = pathlib.PurePosixPath(member.name)
            if member.name == 'prefix' and member.isdir():
                continue
            if (path.is_absolute() or '..' in path.parts or '\\' in member.name or
                    not path.parts or path.parts[0] != 'prefix'):
                raise ValueError('Unsafe archive path: '+member.name)
            name = path.relative_to('prefix').as_posix()
            if name in seen or name not in entries:
                raise ValueError('Duplicate or unlisted entry: '+name)
            seen.add(name)
            entry = entries[name]
            for parent in pathlib.PurePosixPath(name).parents:
                if str(parent) != '.' and entries.get(str(parent), {}).get('type') != 'directory':
                    raise ValueError('Non-directory parent: '+name)
            if member.isdir() and entry['type'] == 'directory':
                continue
            if member.issym() and entry['type'] == 'symlink':
                expected = {'dosdevices/c:': '../drive_c', 'dosdevices/z:': '../..'}
                if member.linkname != entry.get('target') or expected.get(name) != member.linkname:
                    raise ValueError('Unexpected prefix link: '+name)
                continue
            if not member.isfile() or entry['type'] != 'file':
                raise ValueError('Unsupported archive entry: '+name)
            data = stream.extractfile(member).read()
            if digest(data) != entry.get('sha256') or len(data) != entry.get('bytes'):
                raise ValueError('Prefix file hash/size mismatch: '+name)
            if name in REGISTRY and not data.startswith(b'WINE REGISTRY Version 2'):
                raise ValueError('Invalid Wine registry: '+name)
            if name in PE_FILES and pe_machine(data) != PE_FILES[name]:
                raise ValueError('Unexpected PE architecture: '+name)
        if seen != set(entries):
            raise ValueError('Archive/manifest entry set differs')
    for name, target in (('dosdevices/c:', '../drive_c'), ('dosdevices/z:', '../..')):
        if entries.get(name) != {'type': 'symlink', 'target': target}:
            raise ValueError('DOS drive is missing or invalid: '+name)
    return {'directory': str(directory), 'manifest_sha256': digest(manifest_bytes),
            'archive_sha256': digest(archive), 'wine_commit': wine_commit,
            'entries_verified': len(entries), 'exe_sha256': entries['drive_c/orbis/console32.exe']['sha256']}

def stage_package(directory, destination, wine_commit):
    verified = validate_package(directory, wine_commit)
    destination = pathlib.Path(destination)
    if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
        raise ValueError('Prefix destination must be an empty real directory')
    links = []
    # Validate and extract from one immutable in-memory archive to avoid replacing it between passes.
    archive = (pathlib.Path(directory)/'prefix.tar.gz').read_bytes()
    if digest(archive) != verified['archive_sha256']:
        raise ValueError('Prefix archive changed before staging')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as stream:
        for member in stream:
            relative = pathlib.PurePosixPath(member.name).relative_to('prefix')
            path = destination.joinpath(*relative.parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                links.append((path, member.linkname))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with stream.extractfile(member) as source, path.open('wb') as output:
                    shutil.copyfileobj(source, output)
    for path, target in links:
        path.symlink_to(target)
    return verified
