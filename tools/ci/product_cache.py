#!/usr/bin/env python3
"""Verified, allowlisted product build snapshots; never cache prefixes or PKGs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from common import ROOT, RESULTS, phase, revision, sha, write_json

BASE = ROOT / '.deps/product-cache'
DOWNLOADS = ROOT / '.deps/product-downloads'
INPUTS = RESULTS / 'product-cache-inputs.json'
STATUS = RESULTS / 'product-cache-status.json'
DOWNLOAD_STATUS = RESULTS / 'product-download-cache.json'
BLOCKS = ('graphics', 'wine')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def output(name, value):
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write(name + '=' + str(value).lower() + '\n')


def download_specs():
    specs = [json.loads((ROOT / 'artifacts.lock.json').read_text())['openorbis']]
    specs += list(json.loads((ROOT / 'dependencies.lock.json').read_text())['archives'].values())
    specs += list(json.loads((ROOT / 'product-assets.lock.json').read_text())['downloads'].values())
    return {entry['sha256']: entry for entry in specs}


def unlinked_location(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Cache location has a symbolic-link ancestor: ' + str(path))


def product_download(spec, name):
    from bootstrap import download
    cached = DOWNLOADS / spec['sha256']
    unlinked_location(DOWNLOADS)
    reused = cached.exists()
    if cached.exists() or cached.is_symlink():
        if cached.is_symlink() or not cached.is_file() or sha(cached) != spec['sha256']:
            raise ValueError('Altered product download cache: ' + str(cached))
        target = ROOT / '.deps/downloads/ci' / name
        unlinked_location(target.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError('Download destination is a symlink')
        shutil.copyfile(cached, target)
    result = download(spec, name)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    if not cached.exists():
        shutil.copyfile(result, cached)
    record = json.loads(DOWNLOAD_STATUS.read_text()) if DOWNLOAD_STATUS.exists() else {'files': {}}
    record['files'][spec['sha256']] = {'name': name, 'reused': reused}
    write_json(DOWNLOAD_STATUS, record)
    return result


def mounts(block):
    if block == 'graphics':
        return {'vk': Path.home() / 'vk-h0'}
    if block == 'wine':
        return {'runtime': ROOT / '.deps/wine/runtime', 'pe': ROOT / 'out/wine',
                'build-report': ROOT / 'out/wine-build.json',
                'closure': ROOT / 'reports/increment15/host-build'}
    raise ValueError('Unknown product cache block')


def allowed_links(block):
    # These directories are restored from pinned inputs before a snapshot is used.
    return [*mounts(block).values(), ROOT / '.deps/sdk', ROOT / '.deps/wine/source']


def inside(path, roots):
    return '.git' not in path.parts and any(path.is_relative_to(root.resolve()) for root in roots)


def destination(name, destinations):
    parts = PurePosixPath(name).parts
    if (not parts or PurePosixPath(name).is_absolute() or '\\' in name or
            any(part in ('.', '..') for part in parts) or '/'.join(parts) != name or
            parts[0] not in destinations):
        raise ValueError('Unsafe product cache path: ' + name)
    return destinations[parts[0]].joinpath(*parts[1:])


def inventory(destinations, permitted_links, exclude=None):
    result = {}
    for label, root in destinations.items():
        if not root.exists() or root.is_symlink():
            raise ValueError('Missing or linked cache mount: ' + str(root))
        pending = [(label, root)]
        while pending:
            name, path = pending.pop()
            if exclude and exclude(name):
                continue
            info = path.lstat()
            entry = {'mode': stat.S_IMODE(info.st_mode) & 0o777, 'mtime_ns': info.st_mtime_ns}
            if path.is_symlink():
                link = os.readlink(path)
                if not inside((path.parent / link).resolve(), permitted_links):
                    raise ValueError('External cache symlink: ' + str(path))
                entry.update(kind='symlink', target=link)
            elif path.is_dir():
                entry['kind'] = 'directory'
                pending += [(name + '/' + child.name, child) for child in path.iterdir()]
            elif path.is_file():
                entry.update(kind='file', size=info.st_size, sha256=sha(path))
            else:
                raise ValueError('Unsupported cache file: ' + str(path))
            result[name] = entry
    return dict(sorted(result.items()))


def excluded_graphics(name):
    parts = PurePosixPath(name).parts
    allowed = {'build', 'sysroot', 'host-tools', 'llvm-mingw', 'vk-headers',
               'src', 'dolphin', 'crema', 'mesa-pkgconfig'}
    return (len(parts) > 1 and parts[1] not in allowed or '.git' in parts or
            len(parts) > 2 and parts[:2] == ('vk', 'src') and
            (parts[2].startswith('llvm-project-') or parts[2] in
             ('llvm.tar.xz', 'Vulkan-Headers', 'Vulkan-Loader', 'Vulkan-Tools')))


def seal(bundle, key_record, destinations, permitted_links, exclude=None):
    unlinked_location(bundle)
    bundle.mkdir(parents=True, exist_ok=True)
    if list(bundle.iterdir()):
        raise ValueError('Refusing to overwrite an existing product snapshot')
    entries = inventory(destinations, permitted_links, exclude)
    archive = bundle / 'payload.tar.gz'
    with tarfile.open(archive, 'w:gz', compresslevel=1) as target:
        for name, entry in entries.items():
            if entry['kind'] != 'file':
                continue
            info = tarfile.TarInfo(name)
            info.size = entry['size']
            info.mode = entry['mode']
            with destination(name, destinations).open('rb') as source:
                target.addfile(info, source)
    manifest = {'schema_version': 1, 'key_record': key_record, 'entries': entries,
                'payload_sha256': sha(archive), 'producer_sha': revision(),
                'run_id': os.environ.get('GITHUB_RUN_ID', 'local'),
                'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT', 'local')}
    write_json(bundle / 'manifest.json', manifest)
    return manifest


def verify_bundle(bundle, key_record):
    unlinked_location(bundle)
    if ({p.name for p in bundle.iterdir()} != {'payload.tar.gz', 'manifest.json'} or
            any(p.is_symlink() or not p.is_file() for p in bundle.iterdir())):
        raise ValueError('Unexpected product snapshot files')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('schema_version') != 1 or manifest['key_record'] != key_record:
        raise ValueError('Product snapshot inputs differ')
    if sha(bundle / 'payload.tar.gz') != manifest['payload_sha256']:
        raise ValueError('Product snapshot payload was altered')
    return manifest


def restore(bundle, key_record, destinations, permitted_links):
    manifest = verify_bundle(bundle, key_record)
    entries = manifest['entries']
    for name, entry in entries.items():
        path = destination(name, destinations)
        if entry['kind'] not in ('file', 'directory', 'symlink'):
            raise ValueError('Invalid product snapshot entry kind')
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError('Snapshot destination has a linked ancestor')
        # Prevent file entries below a cached symlink, regardless of entry order.
        parent = PurePosixPath(name).parent
        while str(parent) != '.':
            if parent.as_posix() not in entries or entries[parent.as_posix()]['kind'] != 'directory':
                raise ValueError('Snapshot entry has a non-directory parent')
            parent = parent.parent
        if path.is_symlink() or path.exists() and (entry['kind'] != 'directory' or not path.is_dir()):
            raise ValueError('Snapshot would overwrite an existing output: ' + str(path))
        if entry['kind'] == 'symlink' and not inside((path.parent / entry['target']).resolve(), permitted_links):
            raise ValueError('Snapshot symlink escapes permitted inputs/outputs')
    # No archive metadata is applied to live destinations. Validate all regular
    # files first in a private staging area; links are created only after files.
    with tempfile.TemporaryDirectory(prefix='orbisdesk-cache-') as temporary:
        stage = Path(temporary)
        seen = set()
        with tarfile.open(bundle / 'payload.tar.gz') as archive:
            for member in archive:
                destination(member.name, destinations)
                entry = entries.get(member.name)
                if not member.isfile() or not entry or entry['kind'] != 'file' or member.name in seen:
                    raise ValueError('Unexpected, linked or duplicate archive member')
                if member.size != entry['size']:
                    raise ValueError('Product snapshot file size differs')
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('wb') as output_file:
                    shutil.copyfileobj(source, output_file)
                if sha(target) != entry['sha256']:
                    raise ValueError('Product snapshot file hash differs')
                seen.add(member.name)
        if seen != {name for name, entry in entries.items() if entry['kind'] == 'file'}:
            raise ValueError('Product snapshot files are missing')
        for name, entry in entries.items():
            path = destination(name, destinations)
            if entry['kind'] == 'directory':
                path.mkdir(parents=True, exist_ok=True)
            elif entry['kind'] == 'file':
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(stage / name), str(path))
                path.chmod(entry['mode'])
                os.utime(path, ns=(entry['mtime_ns'], entry['mtime_ns']))
        for name, entry in entries.items():
            if entry['kind'] == 'symlink':
                path = destination(name, destinations)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(entry['target'])
    return manifest


def make_keys():
    packages = subprocess.check_output(['dpkg-query', '-W', '-f=${binary:Package}=${Version}\n'], text=True).splitlines()
    tools = {}
    names = ('clang', 'clang-19', 'clang-14', 'ld', 'ld.lld-19', 'llvm-ar-19', 'llvm-ranlib-19',
             'gcc', 'g++', 'make', 'ninja', 'pkg-config', 'x86_64-w64-mingw32-gcc',
             'x86_64-w64-mingw32-g++', 'i686-w64-mingw32-gcc', 'i686-w64-mingw32-g++')
    paths = {name: Path(shutil.which(name) or '/missing-cache-tool/' + name) for name in names}
    paths.update(python=Path(sys.executable), cmake=ROOT / '.deps/linux-tools/cmake/data/bin/cmake',
                 pinned_ninja=ROOT / '.deps/linux-tools/bin/ninja')
    for name, path in paths.items():
        tools[name] = {'path': str(path), 'sha256': sha(path),
                       'version': subprocess.check_output([str(path), '--version'], text=True).strip()}
    system = {'architecture': platform.machine(), 'kernel': platform.release(),
              'os_release': Path('/etc/os-release').read_text(),
              'packages': packages, 'tools': tools, 'root': str(ROOT), 'home': str(Path.home()),
              'environment': {k: os.environ.get(k, '') for k in ('PATH', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS',
                  'CPPFLAGS', 'LDFLAGS', 'CPATH', 'LIBRARY_PATH', 'LD_LIBRARY_PATH', 'PKG_CONFIG_PATH',
                  'PKG_CONFIG_LIBDIR', 'PKG_CONFIG_SYSROOT_DIR', 'SOURCE_DATE_EPOCH',
                  'CMAKE_PREFIX_PATH', 'LC_ALL', 'LANG', 'TZ')}}
    deps = json.loads((ROOT / 'dependencies.lock.json').read_text())
    assets = json.loads((ROOT / 'product-assets.lock.json').read_text())['downloads']
    shared = ['tools/ci/product_cache.py', 'tools/ci/build-product.py', 'tools/ci/install-product.sh',
              'tools/ci/install-runner.sh', 'tools/ci/common.py', 'tools/logged_process.py',
              'tools/restore-dependencies.py']
    tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
    records = {}
    for block in BLOCKS:
        if block == 'graphics':
            selected = shared + [p for p in tracked if p.startswith(('tools/vk-h0/', 'native/', 'platform/ps4/', 'patches/shadPS4/'))]
            repositories = {k: deps['repositories'][k] for k in ('DolphinPS4', 'Crema', 'mangohud',
                           'Vulkan-Headers', 'Vulkan-Loader', 'Vulkan-Tools')}
            source = {'repositories': repositories, 'archives': deps['archives'], 'llvm': assets['llvm-source'],
                      'fork': json.loads((ROOT / 'fork.lock.json').read_text()), 'restore': deps['shadps4_fork']}
        else:
            selected = shared + ['tools/build-wine.py', 'tools/build-host-wine-closure.py',
                                 'tools/build-host-wine-unix.py', 'tools/wine_module_names.py']
            source = {'repositories': {k: deps['repositories'][k] for k in ('wine-build-source', 'prospero-win')},
                      'wine': json.loads((ROOT / 'sources.lock.json').read_text())['sources']['wine']}
        inputs = {'schema_version': 1, 'block': block, 'system': system, 'source': source,
                  'sdk': json.loads((ROOT / 'artifacts.lock.json').read_text())['openorbis'],
                  'recipes': {p: sha(ROOT / p) for p in sorted(set(selected))}}
        records[block] = {'key': fingerprint(inputs), 'inputs': inputs}
    records['downloads_key'] = fingerprint(download_specs())
    write_json(INPUTS, records)
    for block in BLOCKS:
        output(block + '_key', records[block]['key'])
    output('downloads_key', records['downloads_key'])
    return records


def validate_outputs(block):
    if block == 'graphics':
        home = mounts(block)['vk']
        required = ('sysroot/lib/libc++.a', 'sysroot/lib/libc++abi.a', 'host-tools/bin/glslangValidator',
                    'llvm-mingw/bin/x86_64-w64-mingw32-clang', 'vk-headers/include/vulkan/vulkan.h',
                    'build/mesa-wine/src/amd/vulkan/libvulkan_radeon.a',
                    'build/mesa-zink/src/gallium/targets/libgl-gdi/opengl32.dll',
                    'build/mesa-zink/src/gallium/targets/wgl/libgallium_wgl.dll',
                    'build/mesa-zink-i386/src/gallium/targets/libgl-gdi/opengl32.dll',
                    'build/mesa-zink-i386/src/gallium/targets/wgl/libgallium_wgl.dll',
                    'build/vk-loader/loader/vulkan-1.dll', 'build/vk-loader-i386/loader/vulkan-1.dll',
                    'build/mangohud/src/libMangoHud.dll', 'build/mangohud-i386/src/libMangoHud.dll',
                    'build/vk-tools/cube/vkcube.exe')
        for name in required:
            if not (home / name).is_file():
                raise ValueError('Incomplete graphics block: ' + name)
    else:
        build = ROOT / '.deps/wine/runtime/build'
        for name in ('loader/wine', 'loader/wine-preloader', 'server/wineserver'):
            path = build / name
            with path.open('rb') as source:
                if source.read(4) != b'\x7fELF' or not os.access(path, os.X_OK):
                    raise ValueError('Invalid cached native Wine executable: ' + name)
        for path in (build / 'loader/wine.inf', ROOT / 'out/wine/wine-runtime-manifest.json',
                     ROOT / 'out/wine-build.json', ROOT / 'reports/increment15/host-build/unix-report.json'):
            if not path.is_file():
                raise ValueError('Incomplete Wine block: ' + str(path))
        report = json.loads((ROOT / 'reports/increment15/host-build/report.json').read_text())
        expected = json.loads((ROOT / 'sources.lock.json').read_text())['sources']['wine']['commit']
        if report['status'] != 'passed' or report['unknown_imports'] or report['wine_commit'] != expected:
            raise ValueError('Wine closure cache is not a passed pinned closure')


def normalize_wine_source():
    # Fresh git checkouts otherwise make cached objects look older than every
    # header. Content/recipe identities, not checkout mtimes, control reuse.
    source = ROOT / '.deps/wine/source'
    expected = json.loads((ROOT / 'sources.lock.json').read_text())['sources']['wine']['commit']
    if (subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != expected or
            subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain']).strip()):
        raise ValueError('Wine source must be the clean pinned checkout before cache reuse')
    for parent, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if name != '.git']
        for name in files:
            path = Path(parent) / name
            if name != '.git' and not path.is_symlink():
                os.utime(path, (1000000000, 1000000000))


class ProductCache:
    def __init__(self, mode):
        self.mode = mode
        self.keys = make_keys()
        self.status = {'cache_mode': mode, 'requested_by_source_sha': revision(), 'blocks': {},
                       'scope': 'Build dependencies only; prefix creation, verification and packaging always run'}
        write_json(STATUS, self.status)

    def use(self, block):
        start = time.monotonic()
        bundle = BASE / block
        reused = self.mode == 'reuse' and bundle.exists()
        producer = None
        if reused:
            with phase('product-cache-restore-' + block):
                producer = restore(bundle, self.keys[block], mounts(block), allowed_links(block))
                validate_outputs(block)
        self.status['blocks'][block] = {'reused': reused, 'key': self.keys[block]['key'],
                                       'producer_sha': producer['producer_sha'] if producer else None,
                                       'producer_run_id': producer['run_id'] if producer else None,
                                       'restore_seconds': round(time.monotonic() - start, 3), 'sealed': False}
        if producer:
            self.status['blocks'][block].update(
                archive_bytes=(bundle / 'payload.tar.gz').stat().st_size,
                file_count=sum(e['kind'] == 'file' for e in producer['entries'].values()),
                uncompressed_bytes=sum(e.get('size', 0) for e in producer['entries'].values()))
        write_json(STATUS, self.status)
        print(json.dumps({'product_cache_block': block, **self.status['blocks'][block]}), flush=True)
        return reused

    def save(self, block):
        with phase('product-cache-seal-' + block):
            validate_outputs(block)
            manifest = seal(BASE / block, self.keys[block], mounts(block), allowed_links(block),
                            excluded_graphics if block == 'graphics' else
                            lambda name: '.git' in PurePosixPath(name).parts)
        self.status['blocks'][block].update(sealed=True, producer_sha=manifest['producer_sha'],
                                           producer_run_id=manifest['run_id'],
                                           file_count=sum(e['kind'] == 'file' for e in manifest['entries'].values()),
                                           uncompressed_bytes=sum(e.get('size', 0) for e in manifest['entries'].values()),
                                           archive_bytes=(BASE / block / 'payload.tar.gz').stat().st_size)
        write_json(STATUS, self.status)


def ready():
    records = json.loads(INPUTS.read_text()) if INPUTS.exists() else {}
    for block in BLOCKS:
        valid = False
        if block in records and (BASE / block / 'manifest.json').is_file():
            manifest = verify_bundle(BASE / block, records[block])
            valid = (manifest['run_id'] == os.environ.get('GITHUB_RUN_ID') and
                     manifest['run_attempt'] == os.environ.get('GITHUB_RUN_ATTEMPT'))
        output(block + '_ready', valid)
    count = 0
    expected = download_specs()
    if DOWNLOADS.exists():
        unlinked_location(DOWNLOADS)
        for path in DOWNLOADS.iterdir():
            if path.is_symlink() or not path.is_file() or path.name not in expected or sha(path) != path.name:
                raise ValueError('Unexpected or altered product download cache file')
            count += 1
    downloads = json.loads(DOWNLOAD_STATUS.read_text()) if DOWNLOAD_STATUS.exists() else {'files': {}}
    output('downloads_ready', count > 0 and any(not entry['reused'] for entry in downloads['files'].values()))
    output('downloads_count', count)
    output('downloads_kind', 'complete' if count == len(expected) else 'partial')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('keys', 'ready'))
    args = parser.parse_args()
    make_keys() if args.action == 'keys' else ready()
