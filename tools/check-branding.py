#!/usr/bin/env python3
"""Reject stale product branding in active code, with explicit compatibility exceptions."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
old = re.compile(r'orbis[-_ ]?(?:wine|win)', re.I)
compat = {
    'platform/ps4/pw_brand.h', 'tools/project_brand.py',
    'tools/vk-h0/patch-crema-telemetry.py', 'native/doshost_win32.c',
    'tests/test_project_brand.py',
    'tools/check-branding.py',
}
unexpected, retained = [], []
for folder in ('native', 'platform', 'tools', 'fixtures', 'tests'):
    for path in (ROOT / folder).rglob('*'):
        if path.suffix.lower() not in {'.c', '.h', '.cpp', '.hpp', '.py', '.js', '.sh', '.ps1', '.ini', '.rc', '.patch'}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not old.search(line):
                continue
            category = None
            if rel in compat:
                category = 'migration, historical collection, or cached source compatibility'
            elif re.search(r'IV0000-[A-Z0-9_-]*ORBISWIN[A-Z0-9_-]*', line):
                category = 'stable PS4 update identity'
            elif re.search(r'https?://\S*orbis[-_ ]?(?:wine|win)', line, re.I):
                category = 'external source URL'
            item = {'path': rel, 'line': number}
            if category:
                retained.append({**item, 'reason': category})
            else:
                unexpected.append(item)
print(json.dumps({'product': 'OrbisDesk', 'unexpected': unexpected,
                  'retained_compatibility': retained}, indent=2))
raise SystemExit(bool(unexpected))
