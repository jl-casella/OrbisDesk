#!/usr/bin/env python3
"""Prebuilt dependency blocks published as GitHub Release assets and pinned by prebuilt-blocks.lock.json.

The lock is the trust anchor: it is committed through a reviewed PR and names, per block, the input key,
the release tag and the SHA-256/size of the sealed manifest and of every payload part. A product build
places an asset in .deps/product-cache/<block> only when the lock's key equals the key it computed and
every hash matches; product_cache.restore then verifies the bundle exactly as for an actions/cache hit.
Anything else (no entry, other key, download error, hash mismatch) leaves the block to be built.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote
from common import ROOT, RESULTS, revision, sha, write_json
import product_cache

LOCK = ROOT / 'prebuilt-blocks.lock.json'
ASSETS = RESULTS / 'prebuilt'
PART_BYTES = 1900 * 1024 * 1024   # GitHub limits each release asset to 2 GiB
HEX64 = re.compile(r'[0-9a-f]{64}')
ASSET_NAME = re.compile(r'(graphics|wine)-[0-9a-f]{16}\.(manifest\.json|payload\.tar\.gz\.part[0-9]{3})')


def empty_lock():
    return {'schema_version': 1, 'blocks': {}}


def validate_entry(block, entry):
    if block not in product_cache.BLOCKS:
        raise ValueError('Unknown prebuilt block: ' + block)
    key = entry.get('key', '')
    if not HEX64.fullmatch(key):
        raise ValueError('Invalid prebuilt key: ' + block)
    if not re.fullmatch(r'prebuilt-' + block + '-' + key[:16] + r'-[0-9]+', entry.get('tag', '')):
        raise ValueError('Prebuilt tag does not name its block and key: ' + block)
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', entry.get('repository', '')):
        raise ValueError('Invalid prebuilt repository: ' + block)
    files = [entry['manifest'], *entry['payload']['parts']]
    if not entry['payload']['parts'] or not HEX64.fullmatch(entry['payload'].get('sha256', '')):
        raise ValueError('Invalid prebuilt payload: ' + block)
    for item in files:
        if (not ASSET_NAME.fullmatch(item.get('name', '')) or not item['name'].startswith(block + '-' + key[:16]) or
                not HEX64.fullmatch(item.get('sha256', '')) or not isinstance(item.get('size'), int) or item['size'] <= 0):
            raise ValueError('Invalid prebuilt asset record: ' + block)
    names = [part['name'] for part in entry['payload']['parts']]
    if names != [f'{block}-{key[:16]}.payload.tar.gz.part{n:03}' for n in range(len(names))]:
        raise ValueError('Prebuilt payload parts are not consecutive: ' + block)
    if sum(part['size'] for part in entry['payload']['parts']) != entry['payload'].get('size'):
        raise ValueError('Prebuilt payload size differs from its parts: ' + block)
    return entry


def load_lock(path=None):
    path = path or LOCK
    if not path.is_file():
        return empty_lock()
    lock = json.loads(path.read_text())
    if lock.get('schema_version') != 1 or not isinstance(lock.get('blocks'), dict):
        raise ValueError('Unsupported prebuilt lock')
    for block, entry in lock['blocks'].items():
        validate_entry(block, entry)
    return lock


def download_asset(repository, tag, name, directory):
    """One release asset through the GitHub CLI (public and private repositories alike)."""
    subprocess.run(['gh', 'release', 'download', tag, '--repo', repository, '--pattern', name,
                    '--dir', str(directory)], check=True, timeout=3600)
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise ValueError('Prebuilt asset was not downloaded: ' + name)
    return path


def checked(path, record):
    if path.stat().st_size != record['size'] or sha(path) != record['sha256']:
        raise ValueError('Prebuilt asset hash or size differs from the lock: ' + record['name'])
    return path


def fetch(block, key_record, bundle, lock_path=None):
    """Place the locked asset of `block` as a sealed bundle when, and only when, it matches `key_record`."""
    status = {'fetched': False, 'computed_key': key_record['key']}
    try:
        entry = load_lock(lock_path)['blocks'].get(block)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status, reason='invalid lock: ' + str(exc))
    if not entry:
        return dict(status, reason='no lock entry')
    status.update(lock_key=entry['key'], tag=entry['tag'])
    if entry['key'] != key_record['key']:
        # The block's inputs changed since it was published: never use a stale asset.
        return dict(status, reason='key mismatch')
    product_cache.unlinked_location(bundle)
    if bundle.exists() or bundle.is_symlink():
        return dict(status, reason='bundle destination already exists')
    bundle.parent.mkdir(parents=True, exist_ok=True)
    try:
        product_cache.require_disk_space(bundle.parent, entry['payload']['size'] + PART_BYTES, 'fetch prebuilt block')
        with tempfile.TemporaryDirectory(prefix='.prebuilt-' + block + '-', dir=bundle.parent) as temporary:
            stage = Path(temporary)
            downloads = stage / 'downloads'
            downloads.mkdir()
            sealed = stage / 'bundle'
            sealed.mkdir()
            manifest = checked(download_asset(entry['repository'], entry['tag'], entry['manifest']['name'], downloads),
                               entry['manifest'])
            shutil.move(str(manifest), str(sealed / 'manifest.json'))
            # Join part by part so the peak is one payload plus one part.
            with (sealed / 'payload.tar.gz').open('wb') as payload:
                for record in entry['payload']['parts']:
                    part = checked(download_asset(entry['repository'], entry['tag'], record['name'], downloads), record)
                    with part.open('rb') as source:
                        shutil.copyfileobj(source, payload, 1024 * 1024)
                    part.unlink()
            if sha(sealed / 'payload.tar.gz') != entry['payload']['sha256']:
                raise ValueError('Joined prebuilt payload differs from the lock')
            downloads.rmdir()
            sealed_manifest = product_cache.verify_bundle(sealed, key_record)
            if sealed_manifest['payload_sha256'] != entry['payload']['sha256']:
                raise ValueError('Prebuilt manifest names another payload')
            sealed.rename(bundle)
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as exc:
        if bundle.exists() and not bundle.is_symlink():
            shutil.rmtree(bundle)
        print('Prebuilt ' + block + ' rejected; building it instead: ' + str(exc), flush=True)
        return dict(status, reason='rejected: ' + str(exc))
    return dict(status, fetched=True, reason='lock key and hashes match',
                producer_sha=sealed_manifest['producer_sha'], producer_run_id=sealed_manifest['run_id'])


def split_payload(payload, directory, stem):
    parts = []
    with payload.open('rb') as stream:
        number = 0
        while True:
            data = stream.read(min(PART_BYTES, 1024 * 1024))
            if not data:
                break
            path = directory / f'{stem}.payload.tar.gz.part{number:03}'
            with path.open('wb') as part:
                part.write(data)
                remaining = PART_BYTES - len(data)
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    part.write(chunk)
                    remaining -= len(chunk)
            parts.append({'name': path.name, 'sha256': sha(path), 'size': path.stat().st_size})
            number += 1
    return parts


def api(endpoint, method='GET', payload=None):
    command = ['gh', 'api', '--method', method, endpoint]
    data = None
    if payload is not None:
        command += ['--input', '-']
        data = json.dumps(payload)
    return json.loads(subprocess.check_output(command, input=data, text=True))


def publish(block):
    """Upload a block sealed in this run to a new prerelease and write its lock fragment."""
    repository = os.environ['GITHUB_REPOSITORY']
    run_id = os.environ['GITHUB_RUN_ID']
    source = os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repository) or not run_id.isdigit() or revision() != source:
        raise ValueError('Publish only from the checked-out workflow revision')
    key_record = json.loads(product_cache.INPUTS.read_text())[block]
    bundle = product_cache.BASE / block
    manifest = product_cache.verify_bundle(bundle, key_record)
    if manifest['run_id'] != run_id or manifest['run_attempt'] != os.environ.get('GITHUB_RUN_ATTEMPT'):
        raise ValueError('Only a block sealed by this run is published')
    product_cache.validate_outputs(block)
    stem = block + '-' + key_record['key'][:16]
    tag = 'prebuilt-' + stem + '-' + run_id
    directory = ASSETS / block
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    shutil.copyfile(bundle / 'manifest.json', directory / (stem + '.manifest.json'))
    parts = split_payload(bundle / 'payload.tar.gz', directory, stem)
    entry = validate_entry(block, {
        'key': key_record['key'], 'repository': repository, 'tag': tag,
        'producer_sha': manifest['producer_sha'], 'run_id': run_id,
        'manifest': {'name': stem + '.manifest.json', 'sha256': sha(directory / (stem + '.manifest.json')),
                     'size': (directory / (stem + '.manifest.json')).stat().st_size},
        'payload': {'sha256': manifest['payload_sha256'], 'size': sum(p['size'] for p in parts), 'parts': parts}})
    files = {entry['manifest']['name']: entry['manifest']['sha256'], **{p['name']: p['sha256'] for p in parts}}
    # A new tag for every run: existing tags and published releases are never moved or overwritten.
    api(f'repos/{repository}/git/refs', 'POST', {'ref': 'refs/tags/' + tag, 'sha': source})
    release = api(f'repos/{repository}/releases', 'POST', {
        'tag_name': tag, 'target_commitish': source, 'name': f'Prebuilt {block} block {key_record["key"][:16]}',
        'body': (f'Sealed `{block}` dependency block for OrbisDesk product builds (input key `{key_record["key"]}`, '
                 f'source `{source}`, run {run_id}). Not a product release: consumed only through '
                 '`prebuilt-blocks.lock.json`, which pins every asset by SHA-256.'),
        'draft': True, 'prerelease': True, 'make_latest': 'false'})
    subprocess.run(['gh', 'release', 'upload', tag, *map(str, sorted(directory.iterdir())), '--repo', repository],
                   check=True)
    remote = api(f'repos/{repository}/releases/{release["id"]}')
    if {a['name'] for a in remote['assets']} != set(files):
        raise ValueError('Remote prebuilt asset inventory differs')
    for asset in remote['assets']:
        if asset.get('digest') != 'sha256:' + files[asset['name']]:
            raise ValueError('Remote prebuilt digest differs: ' + asset['name'])
    release = api(f'repos/{repository}/releases/{release["id"]}', 'PATCH', {'draft': False, 'make_latest': 'false'})
    for part in entry['payload']['parts'] + [entry['manifest']]:
        part['url'] = f'https://github.com/{repository}/releases/download/{quote(tag)}/{quote(part["name"])}'
    write_json(ASSETS / (block + '.lock-fragment.json'), {block: entry})
    shutil.rmtree(directory)
    print(release['html_url'], flush=True)


def merge(fragments, lock_path=None):
    lock_path = lock_path or LOCK
    lock = load_lock(lock_path)
    for path in fragments:
        for block, entry in json.loads(Path(path).read_text()).items():
            lock['blocks'][block] = validate_entry(block, entry)
    lock['blocks'] = dict(sorted(lock['blocks'].items()))
    write_json(lock_path, lock)
    return lock


def plan(block, force=False):
    keys = product_cache.make_keys()
    entry = load_lock()['blocks'].get(block)
    needed = force or not entry or entry['key'] != keys[block]['key']
    product_cache.output('needed', needed)
    print(json.dumps({'block': block, 'computed_key': keys[block]['key'],
                      'lock_key': entry['key'] if entry else None, 'needed': needed}), flush=True)
    return needed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='action', required=True)
    planned = commands.add_parser('plan')
    planned.add_argument('--block', choices=product_cache.BLOCKS, required=True)
    planned.add_argument('--force', action='store_true')
    published = commands.add_parser('publish')
    published.add_argument('--block', choices=product_cache.BLOCKS, required=True)
    merged = commands.add_parser('merge')
    merged.add_argument('fragments', nargs='+')
    args = parser.parse_args()
    if args.action == 'plan':
        plan(args.block, args.force)
    elif args.action == 'publish':
        publish(args.block)
    else:
        merge(args.fragments)
