#!/usr/bin/env python3
"""Check project-owned English/Spanish Markdown pairs without extra packages."""
from pathlib import Path
import argparse
import json
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^)\n]+)\)')


def own_docs(root):
    paths = [root / name for name in (
        'README.md', 'README-es.md', 'THIRD_PARTY.md', 'THIRD_PARTY-es.md',
        'AGENTS.md', 'AGENTS-es.md')]
    paths += list((root / 'docs').rglob('*.md'))
    paths += list((root / 'notes').rglob('*.md'))
    return sorted(p for p in paths if p.is_file())


def prose(text):
    """Exclude fenced examples when checking navigational links."""
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if fence is None and not line.startswith(('    ', '\t')):
            yield re.sub(r'(`+).*?\1', '', line)


def check(root):
    errors, warnings = [], []
    paths = own_docs(root)
    known = set(paths)
    primary = [p for p in paths if not p.stem.endswith('-es')]
    for path in paths:
        spanish = path.stem.endswith('-es')
        base = path.with_name(path.stem[:-3] + '.md') if spanish else path
        counterpart = base if spanish else base.with_name(base.stem + '-es.md')
        name = path.relative_to(root).as_posix()
        if counterpart not in known:
            errors.append(f'{name}: missing counterpart {counterpart.name}')
        text = path.read_text(encoding='utf-8')
        navigation = f'[English]({base.name}) | [Español]({base.stem}-es.md)'
        if navigation not in text[:1800]:
            errors.append(f'{name}: missing language navigation near the beginning')
        if re.search(r'ZXQ\d{4}ZXQ', text):
            errors.append(f'{name}: unresolved translation placeholder')
        for line in prose(text):
            for match in LINK.finditer(line):
                dest = match[1].strip('<>')
                parsed = urlsplit(dest)
                if parsed.scheme or dest.startswith('//') or not parsed.path:
                    continue
                target = (path.parent / unquote(parsed.path)).resolve()
                if target in known and target != counterpart:
                    if target.stem.endswith('-es') != spanish:
                        errors.append(f'{name}: cross-language content link: {dest}')
                elif not target.exists():
                    warnings.append(f'{name}: unresolved local link: {dest}')
    return {'pairs': len(primary), 'documents': len(paths),
            'errors': sorted(set(errors)), 'warnings': sorted(set(warnings))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = check(args.root.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{report['pairs']} pairs; {len(report['errors'])} errors; "
          f"{len(report['warnings'])} unresolved local links")
    for error in report['errors']:
        print(error)
    sys.exit(bool(report['errors']))


if __name__ == '__main__':
    main()
