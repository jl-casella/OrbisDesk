# SPDX-License-Identifier: LGPL-2.1-or-later
"""Product identity; old names below exist only for update compatibility."""
import re

NAME = 'OrbisDesk'
SLUG = 'orbisdesk'
STATE_ROOT = '/data/orbisdesk'
LEGACY_STATE_ROOT = '/data/orbis-win'
FIRST_RENAMED_BUILD = 283


def state_root(build):
    return STATE_ROOT if int(build[1:]) >= FIRST_RENAMED_BUILD else LEGACY_STATE_ROOT


def package_build(filename):
    match = re.fullmatch(r'(?:orbisdesk|orbis-win)-W([0-9]{3})-[0-9a-f]{12}\.pkg', filename)
    return int(match[1]) if match else None


def normalize_marker(text):
    """Recognize historical patch markers without altering their source proofs."""
    return text.replace('Orbis-win', NAME)
