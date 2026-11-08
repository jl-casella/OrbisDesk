# SPDX-License-Identifier: LGPL-2.1-or-later
"""Resolve Wine source import-library aliases to configured PE filenames."""
import re


def import_library_alias(definition):
    text = definition.replace('\\\n', ' ')
    match = re.search(r'^IMPORTLIB[ \t]*=[ \t]*([^\r\n#]*)', text, re.M)
    if not match:
        return None
    name = match[1].strip().lower()
    if not name:
        return None
    if len(name.split()) != 1 or '$' in name or '/' in name or '\\' in name:
        raise ValueError('Unsupported Wine IMPORTLIB: ' + name)
    return name


def register_alias(aliases, arch, alias, module):
    if alias is None:
        return
    key = (arch, alias.lower())
    module = module.lower()
    if key in aliases and aliases[key] != module:
        raise ValueError('Ambiguous Wine import library: ' + repr(key))
    aliases[key] = module


def resolve_import_library(name, arch, aliases):
    name = name.lower()
    if '$' in name:
        raise ValueError('Unexpanded Wine import library: ' + name)
    if (arch, name) in aliases:
        return aliases[(arch, name)]
    return name if '.' in name else name + '.dll'
