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
from urllib.parse import quote
from common import ROOT, RESULTS, revision, sha, write_json


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
    # Only the producer's fresh runtime is archived, never /data from a console.
    archive = output / 'OrbisDesk-runtime.tar.gz'
    with tarfile.open(archive, 'w:gz', dereference=False) as tar:
        tar.add(runtime, arcname='data', recursive=True)
    # GitHub limits individual release assets to 2 GiB. Split without buffering GiBs.
    if archive.stat().st_size > 1900 * 1024 * 1024:
        with archive.open('rb') as stream:
            number = 0
            while True:
                data = stream.read(1024 * 1024)
                if not data:
                    break
                with (output / (archive.name + f'.part{number:03}')).open('wb') as part:
                    part.write(data)
                    remaining = 1899 * 1024 * 1024
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        part.write(chunk)
                        remaining -= len(chunk)
                number += 1
        archive.unlink()
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
    tag = 'orbisdesk-' + version + '-' + source[:12]
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
    body = ('Experimental OrbisDesk build. Source: `' + source + '`.\n\n'
            'Includes PKG, matching fresh /data runtime, licenses and checksums. '
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
