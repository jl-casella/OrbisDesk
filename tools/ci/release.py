#!/usr/bin/env python3
"""Assemble verified product assets and publish them through a draft release."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import urllib.request
from urllib.parse import quote, urlparse
from common import ROOT, RESULTS, revision, sha, write_json

# GitHub limits individual release assets to 2 GiB.
ASSET_LIMIT = 1900 * 1024 * 1024


def split_asset(archive):
    """Split a file larger than ASSET_LIMIT into .partNNN files without buffering GiBs; returns the files."""
    if archive.stat().st_size <= ASSET_LIMIT:
        return [archive]
    parts = []
    with archive.open('rb') as stream:
        while True:
            data = stream.read(min(1024 * 1024, ASSET_LIMIT))
            if not data:
                break
            part = archive.with_name(archive.name + f'.part{len(parts):03}')
            with part.open('wb') as out:
                out.write(data)
                remaining = ASSET_LIMIT - len(data)
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            parts.append(part)
    archive.unlink()
    return parts


def fetch(url, digest, path, size=None):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'OrbisDesk-release'})
            with urllib.request.urlopen(request, timeout=120) as response, path.open('wb') as out:
                shutil.copyfileobj(response, out, 1024 * 1024)
            break
        except OSError:
            if attempt == 2:
                raise
    if sha(path) != digest or (size is not None and path.stat().st_size != size):
        raise ValueError('Source download differs from its pin: ' + url)


def git_archive(name, url, commit, path):
    """The pinned commit's tree as a .tar.gz; a server that refuses a fetch by SHA gets a full fetch."""
    work = path.parent / ('.git-' + name)
    subprocess.run(['git', 'init', '-q', '--bare', str(work)], check=True)
    git = ['git', '-C', str(work)]
    try:
        subprocess.run([*git, 'fetch', '-q', '--depth', '1', url, commit], check=True)
    except subprocess.CalledProcessError:
        subprocess.run([*git, 'fetch', '-q', url, '+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*'], check=True)
    found = subprocess.check_output([*git, 'rev-parse', '--verify', commit + '^{commit}'], text=True).strip()
    if found != commit:
        raise ValueError('Repository commit differs: ' + name)
    subprocess.run([*git, 'archive', '--format=tar.gz', '--prefix=' + name + '-' + commit[:12] + '/',
                    '-o', str(path), commit], check=True)
    shutil.rmtree(work)


def third_party_sources(candidate, tag, work):
    """<tag>-third-party-sources.tar (docs/RELEASE_LICENSES.md section 5): the pinned third-party sources the
    package is built from or ships, each checked against its lock, with SOURCES.txt listing their SHA-256.
    Returns the release files it wrote into candidate (one, or its .partNNN pieces)."""
    lock = json.loads((ROOT / 'third-party-sources.lock.json').read_text())
    assets = json.loads((ROOT / 'product-assets.lock.json').read_text())['downloads']
    dependencies = json.loads((ROOT / 'dependencies.lock.json').read_text())
    name = tag + '-third-party-sources'
    folder = work / name
    folder.mkdir(parents=True)
    downloads = [(key, entry['url'], entry['sha256'], entry.get('bytes')) for key, entry in lock['downloads'].items()]
    downloads += [(key, assets[key]['url'], assets[key]['sha256'], None) for key in lock['product_assets']]
    downloads += [(key, dependencies['archives'][key]['url'], dependencies['archives'][key]['sha256'], None)
                  for key in lock['dependency_archives']]
    rows = []
    for key, url, digest, size in downloads:
        filename = PurePosixPath(urlparse(url).path).name
        if not filename or filename in ('.', '..'):
            raise ValueError('Source URL has no file name: ' + url)
        target = folder / key / filename
        target.parent.mkdir()
        fetch(url, digest, target, size)
        rows.append((digest, target.relative_to(folder).as_posix(), url))
    (folder / 'repositories').mkdir()
    for key in lock['repositories']:
        entry = dependencies['repositories'][key]
        target = folder / 'repositories' / (key + '-' + entry['commit'][:12] + '.tar.gz')
        git_archive(key, entry['url'], entry['commit'], target)
        rows.append((sha(target), target.relative_to(folder).as_posix(), entry['url'] + ' ' + entry['commit']))
    (folder / 'SOURCES.txt').write_text(
        'OrbisDesk ' + tag + ': third-party sources, SHA-256, path in this archive, origin.\n'
        'OrbisDesk\'s own source is the repository at the tag ' + tag + '.\n\n' +
        ''.join(f'{digest}  {path}  {origin}\n' for digest, path, origin in rows))
    archive = candidate / (name + '.tar')
    with tarfile.open(archive, 'w') as tar:
        tar.add(folder, arcname=name)
    shutil.rmtree(folder)
    return split_asset(archive)


def contained(root, relative):
    name = PurePosixPath(relative)
    if name.is_absolute() or '..' in name.parts or '\\' in relative or not name.parts:
        raise ValueError('Unsafe product path: ' + relative)
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError('Product path escapes or is a symlink: ' + relative)
    return path


def verify_product(root, product):
    package = contained(root, product['package'])
    if package.name != 'OrbisDesk.pkg' or package.read_bytes()[:4] != b'\x7fCNT':
        raise ValueError('Not an OrbisDesk PS4 PKG')
    if sha(package) != product['package_sha256']:
        raise ValueError('Package hash differs')
    runtime = contained(root, product['runtime_root'])
    expected = product['runtime_files']
    actual = {p.relative_to(runtime).as_posix() for p in runtime.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(expected):
        raise ValueError('Runtime file inventory differs')
    for name, record in expected.items():
        path = contained(runtime, name)
        if sha(path) != record['sha256'] or path.stat().st_size != record['bytes']:
            raise ValueError('Runtime file differs: ' + name)
    for name, digest in product['source_hashes'].items():
        if sha(contained(root, name)) != digest:
            raise ValueError('Product source changed: ' + name)
    if product.get('title_id') != 'ORBW00002' or product.get('product', {}).get('name') != 'OrbisDesk':
        raise ValueError('Product identity differs')
    return package, runtime


def assemble():
    proof = json.loads((RESULTS / 'product-build.json').read_text())
    if proof.get('status') != 'built' or proof['source_sha'] != revision():
        raise ValueError('No successful product build for this revision')
    manifest_path = contained(ROOT, proof['manifest'])
    if sha(manifest_path) != proof['manifest_sha256']:
        raise ValueError('Product manifest changed')
    product = json.loads(manifest_path.read_text())
    package, runtime = verify_product(ROOT, product)
    output = ROOT / 'out/release'
    output.mkdir(exist_ok=False)
    shutil.copyfile(package, output / 'OrbisDesk.pkg')
    shutil.copyfile(manifest_path, output / 'product-manifest.json')
    shutil.copyfile(RESULTS / 'product-build.json', output / 'build-provenance.json')
    shutil.copyfile(ROOT / 'THIRD_PARTY.md', output / 'THIRD_PARTY.md')
    shutil.copytree(ROOT / 'LICENSES', output / 'LICENSES')
    # alpha-1: a package that carries the runtime installs it on its first start (native/hw_install.h);
    # the release is then the package alone. Older recipes ship the runtime as an archive.
    if product.get('runtime_embedded', {}).get('embedded'):
        (output / 'INSTALL.txt').write_text(
            'Install OrbisDesk.pkg with your existing homebrew package installer and start it.\n'
            'The first start of each version installs the runtime into /data (about 1.1 GB; it shows its progress).\n'
            'Documents, saves, Steam games and your settings stay; files earlier versions shipped are replaced.\n'
            'If it reports INSTALL FAILED, free the space it names (or report the screen), then start again.\n'
            'Experimental build: package/import checks only; desktop smoke and physical acceptance are pending.\n')
    else:
        # Only the producer's fresh runtime is archived, never /data from a console.
        archive = output / 'OrbisDesk-runtime.tar.gz'
        with tarfile.open(archive, 'w:gz', dereference=False) as tar:
            tar.add(runtime, arcname='data', recursive=True)
        split_asset(archive)
        (output / 'INSTALL.txt').write_text(
            'Install OrbisDesk.pkg with your existing homebrew package installer.\n'
            'Extract OrbisDesk-runtime.tar.gz to a new staging directory, then transfer the data/ contents to /data.\n'
            'For split archives first concatenate OrbisDesk-runtime.tar.gz.part* in lexical order.\n'
            'Back up existing registries, documents, settings and saves before replacing runtime files.\n'
            'This archive is a fresh runtime, not a merge-aware updater. No FTP deployment is automatic.\n'
            'Experimental build: package/import checks only; desktop smoke and physical acceptance are pending.\n')
    # Licenses are a single upload asset; never accidentally publish arbitrary tree files.
    with tarfile.open(output / 'LICENSES.tar.gz', 'w:gz') as tar:
        tar.add(output / 'LICENSES', arcname='LICENSES')
    shutil.rmtree(output / 'LICENSES')
    # Recompute transport checksums after replacing the license directory with its archive.
    hashes = {p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name not in ('SHA256SUMS', 'release-manifest.json')}
    write_json(output / 'release-manifest.json', {'source_sha': revision(), 'app_version': product['app_version'],
               'files': hashes, 'Wine_booted': False, 'hardware_status': 'pending'})
    (output / 'SHA256SUMS').write_text(''.join(value + '  ' + name + '\n' for name, value in sorted(hashes.items())) +
                                    sha(output / 'release-manifest.json') + '  release-manifest.json\n')


def api(endpoint, method='GET', payload=None):
    command = ['gh', 'api', '--method', method, endpoint]
    if payload is None:
        data = None
    else:
        command += ['--input', '-']
        data = json.dumps(payload)
    return json.loads(subprocess.check_output(command, input=data, text=True))


def publish():
    if os.environ['GITHUB_REF'] != 'refs/heads/main':
        raise ValueError('Releases must target main')
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid repository')
    event = os.environ['GITHUB_EVENT_NAME']
    if event == 'workflow_dispatch' and any(os.environ.get(key, '').casefold() != repo.split('/')[0].casefold()
                                           for key in ('GITHUB_ACTOR', 'GITHUB_TRIGGERING_ACTOR')):
        raise ValueError('Only the repository owner can dispatch or rerun a manual release')
    source = os.environ['GITHUB_SHA']
    candidate = ROOT / 'out/release'
    manifest = json.loads((candidate / 'release-manifest.json').read_text())
    if manifest['source_sha'] != source or revision() != source:
        raise ValueError('Release source revision differs')
    for name, digest in manifest['files'].items():
        if sha(contained(candidate, name)) != digest:
            raise ValueError('Release asset differs: ' + name)
    expected = set(manifest['files']) | {'release-manifest.json', 'SHA256SUMS'}
    if {p.name for p in candidate.iterdir()} != expected:
        raise ValueError('Unexpected release assets')
    checksums = ''.join(value + '  ' + name + '\n' for name, value in sorted(manifest['files'].items()))
    checksums += sha(candidate / 'release-manifest.json') + '  release-manifest.json\n'
    if (candidate / 'SHA256SUMS').read_text() != checksums:
        raise ValueError('Transport checksum list differs')
    version = manifest['app_version']
    # the tag and source asset names the package's C:\orbis\licenses\SOURCE.txt gives (tools/build-wine-hardware.py)
    tag = 'orbisdesk-' + version + '-' + source[:12]
    # The corresponding third-party sources, fetched here against their pins before anything is tagged
    for path in third_party_sources(candidate, tag, ROOT / 'out/release-sources'):
        manifest['files'][path.name] = sha(path)
    write_json(candidate / 'release-manifest.json', manifest)
    checksums = ''.join(value + '  ' + name + '\n' for name, value in sorted(manifest['files'].items()))
    (candidate / 'SHA256SUMS').write_text(checksums + sha(candidate / 'release-manifest.json') + '  release-manifest.json\n')
    expected = set(manifest['files']) | {'release-manifest.json', 'SHA256SUMS'}
    # Never advance an existing tag. Retries may finish only the same draft/tag/SHA.
    try:
        reference = api(f'repos/{repo}/git/ref/tags/{quote(tag, safe="")}')
    except subprocess.CalledProcessError as exc:
        # A 404 must be distinguished from a permission/network/API error.
        listing = api(f'repos/{repo}/git/matching-refs/tags/{quote(tag, safe="")}')
        if listing:
            raise exc
        reference = api(f'repos/{repo}/git/refs', 'POST', {'ref': 'refs/tags/' + tag, 'sha': source})
    if reference['object']['sha'] != source or reference['object']['type'] != 'commit':
        raise ValueError('Existing release tag targets another object')
    releases = json.loads(subprocess.check_output(['gh', 'api', '--paginate', '--slurp',
                         f'repos/{repo}/releases?per_page=100'], text=True))
    releases = [entry for page in releases for entry in page]
    current = next((r for r in releases if r['tag_name'] == tag), None)
    if current and not current['draft']:
        raise ValueError('Release already published; refusing to replace assets')
    # Choose the closest prior published OrbisDesk release on the target's ancestry.
    previous = []
    for release in releases:
        name = release['tag_name']
        if release['draft'] or name == tag or not name.startswith('orbisdesk-'):
            continue
        exists = subprocess.run(['git', 'rev-parse', '--verify', 'refs/tags/' + name], capture_output=True)
        if exists.returncode:
            continue
        ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', 'refs/tags/' + name, source])
        if ancestor.returncode == 0:
            count = int(subprocess.check_output(['git', 'rev-list', '--count', name + '..' + source]))
            if count:
                previous.append((count, name))
    base = min(previous)[1] if previous else None
    args = {'tag_name': tag, 'target_commitish': source}
    if base:
        args['previous_tag_name'] = base
    generated = api(f'repos/{repo}/releases/generate-notes', 'POST', args)
    commits = subprocess.check_output(['git', 'log', '--format=- %h %s', (base + '..' + source) if base else source], text=True)
    runtime = ('matching fresh /data runtime' if any(n.startswith('OrbisDesk-runtime') for n in manifest['files'])
               else 'which installs its runtime on first start')
    body = ('Experimental OrbisDesk build. Source: `' + source + '`.\n\n'
            'Includes the PKG, ' + runtime + ', licenses, checksums and `' + tag + '-third-party-sources.tar` '
            '(the corresponding third-party sources; concatenate any `.part*` files in order first). '
            'Build/package/import checks passed; desktop smoke and physical PS4 acceptance remain pending.\n\n' +
            generated['body'] + '\n\n## Included commits\n\n' + commits)
    payload = {'tag_name': tag, 'target_commitish': source, 'name': 'OrbisDesk ' + version,
               'body': body, 'draft': True, 'prerelease': True}
    if current:
        release = api(f'repos/{repo}/releases/{current["id"]}', 'PATCH', payload)
    else:
        release = api(f'repos/{repo}/releases', 'POST', payload)
    # Uploads complete before the draft becomes visible. Failures preserve the draft.
    subprocess.run(['gh', 'release', 'upload', tag, *map(str, sorted(candidate.iterdir())),
                    '--repo', repo, '--clobber'], check=True)
    remote = api(f'repos/{repo}/releases/{release["id"]}')
    if {a['name'] for a in remote['assets']} != expected:
        raise ValueError('Remote release asset inventory differs')
    for asset in remote['assets']:
        if asset.get('digest') != 'sha256:' + sha(candidate / asset['name']):
            raise ValueError('Remote release digest differs: ' + asset['name'])
    release = api(f'repos/{repo}/releases/{release["id"]}', 'PATCH', {'draft': False})
    print(release['html_url'])
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('Published ' + release['html_url'] + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('assemble', 'publish'))
    args = parser.parse_args()
    assemble() if args.action == 'assemble' else publish()
