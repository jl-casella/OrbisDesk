#!/usr/bin/env python3
"""Validate committed pins and patch bytes without hydrating dependencies."""
import json
import re
from common import ROOT, sha


def main():
    for path in ROOT.glob('*.lock.json'):
        json.loads(path.read_text())
    fork = json.loads((ROOT / 'fork.lock.json').read_text())
    deps = json.loads((ROOT / 'dependencies.lock.json').read_text())
    for patch in [*fork['patches'], deps['shadps4_fork']['overlay']]:
        path = (ROOT / patch['path']).resolve()
        if not path.is_relative_to(ROOT / 'patches') or sha(path) != patch['sha256']:
            raise SystemExit('Invalid patch path/hash: ' + patch['path'])
    for name, spec in deps['repositories'].items():
        if not re.fullmatch(r'[a-f0-9]{40}', spec['commit']):
            raise SystemExit('Unpinned source: ' + name)
    actions = json.loads((ROOT / 'tools/ci/actions.lock.json').read_text())
    for name, pin in actions.items():
        if not re.fullmatch(r'[a-f0-9]{40}', pin['sha']):
            raise SystemExit('Unpinned action: ' + name)
    for workflow in [*(ROOT / '.github/workflows').glob('*.yml'), *(ROOT / '.github/actions').glob('*/action.yml')]:
        for action, commit in re.findall(r'uses:\s*actions/([\w/-]+)@([^\s]+)', workflow.read_text()):
            base = action.split('/')[0]
            if base not in actions or commit != actions[base]['sha']:
                raise SystemExit('Action differs from lock: ' + action + ' in ' + workflow.name)
    from prebuilt import load_lock
    load_lock()
    print('JSON locks, source revisions and ordered patch hashes verified')


if __name__ == '__main__':
    main()
