#!/usr/bin/env python3
"""Generate English/Spanish indexes of public Markdown documentation only."""
import argparse
from pathlib import Path
import posixpath
import re

ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
    ('Entry points and policy', 'Entrada y políticas'),
    ('Architecture and guest execution', 'Arquitectura y ejecución de invitados'),
    ('Emulator and desktop validation', 'Emulador y validación del escritorio'),
    ('Native Steam client, games and attribution', 'Cliente Steam nativo, juegos y atribuciones'),
    ('Platform and Wine increments (historical)', 'Incrementos de plataforma y Wine (históricos)'),
    ('Hardware builds and subsystem evidence', 'Builds físicas y evidencia por subsistema'),
    ('Drafts and plans (not acceptance evidence)', 'Borradores y planes (no son evidencia de aceptación)'),
    ('Other public notes', 'Otras notas públicas'),
]


def group(path):
    name = path.name
    if any(word in name.lower() for word in ('borrador', 'plan', 'wxxx')):
        return 6
    if path.parent == ROOT or name in {
        'CURRENT_STATE.md', 'STATUS.md', 'DOCUMENTATION_POLICY.md',
        'REPOSITORY_LAYOUT.md', 'REBRANDING_ORBISDESK.md',
    }:
        return 0
    if name.startswith('investigacion-'):
        return 1
    if name in {'SHAD_W284_DESKTOP.md', 'TASKBAR_CENTER_FIX.md'}:
        return 2
    if name.startswith('STEAM_') or name in {'GAMES.md', 'THIRD_PARTY_FONTS.md'}:
        return 3
    if name.startswith('INCREMENT_'):
        return 4
    if name.startswith('HARDWARE_'):
        return 5
    return 7


def render(paths, spanish):
    title = '# Índice de documentación' if spanish else '# Documentation index'
    intro = (
        'Índice de toda la documentación pública. Empezar por la guía para IA y el estado actual. '
        'Los documentos históricos y borradores conservan su contexto; un enlace no implica validación actual. '
        'Las notas privadas, dependencias descargadas y evidencia ignorada no se indexan.'
        if spanish else
        'Index of all public documentation. Start with the AI/developer guide and current state. '
        'Historical documents and drafts retain their original scope; a link does not imply current validation. '
        'Private notes, downloaded dependencies and ignored evidence are not indexed.'
    )
    result = [title, '', '[English](INDEX.md) | [Español](INDEX-es.md)', '', intro, '',
              ('Regenerar ambos idiomas: `python3 tools/build-doc-index.py`.' if spanish else
               'Regenerate both languages: `python3 tools/build-doc-index.py`.'), '']
    for i, labels in enumerate(GROUPS):
        selected = [p for p in paths if group(p) == i]
        if not selected:
            continue
        result += ['## ' + labels[int(spanish)], '']
        for path in selected:
            target = path.with_name(path.stem + '-es.md') if spanish else path
            if not target.is_file():
                raise SystemExit('Missing language counterpart: ' + str(target.relative_to(ROOT)))
            text = target.read_text(encoding='utf-8')
            heading = re.search(r'^#\s+(.+)$', text, re.M)
            description = re.sub(r'<[^>]*>|[*`]', '', heading[1]).strip() if heading else target.stem
            href = posixpath.relpath(target.relative_to(ROOT).as_posix(), 'docs')
            result.append(f'- [{target.name}]({href}) — {description}')
        result.append('')
    return '\n'.join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the generated indexes are stale')
    args = parser.parse_args()
    paths = [ROOT / name for name in ('AGENTS.md', 'README.md', 'THIRD_PARTY.md')]
    for folder in ('docs', 'notes'):
        paths += [p for p in (ROOT / folder).rglob('*.md')
                  if not p.stem.endswith('-es') and p.name != 'INDEX.md']
    paths = sorted(set(paths), key=lambda p: p.relative_to(ROOT).as_posix())
    stale = []
    for spanish in (False, True):
        path = ROOT / 'docs' / ('INDEX-es.md' if spanish else 'INDEX.md')
        expected = render(paths, spanish)
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != expected:
                stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.write_text(expected, encoding='utf-8')
    if stale:
        raise SystemExit('Stale documentation index: ' + ', '.join(stale))
    print(f'{len(paths)} public documents indexed in both languages')


if __name__ == '__main__':
    main()
