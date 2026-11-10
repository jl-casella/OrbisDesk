# SPDX-License-Identifier: LGPL-2.1-or-later
"""Read staging declarations without importing scripts that execute builds on import."""
import ast


def declaration(path, name):
    assignments = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value

    def literal(node):
        if isinstance(node, ast.Name):
            return literal(assignments[node.id])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return literal(node.left) + literal(node.right)
        if isinstance(node, ast.Dict):
            return {literal(k): literal(v) for k, v in zip(node.keys, node.values)}
        return ast.literal_eval(node)

    return literal(assignments[name])


def product_seeds(root):
    tools = root / 'tools'
    modules = set()
    def add(arch, names):
        modules.update((arch, name.lower()) for name in names)
    i386 = tools / 'stage-wine-i386.py'
    add('i386', (name + '.dll' for name in declaration(i386, 'TARGETS')))
    add('x86_64', (name + '.dll' for name in declaration(i386, 'X64_TARGETS')))
    for arch, field in (('i386', 'W261_I386'), ('x86_64', 'W261_X64')):
        add(arch, declaration(i386, field))
    add('x86_64', (name + '.exe' for name in declaration(tools / 'stage-wine-programs.py', 'PROGRAMS')))
    add('x86_64', ('joy.cpl',))
    for arch in ('i386', 'x86_64'):
        add(arch, (name for _, name in declaration(tools / 'stage-wine-extras.py', 'MODULES')))
    for arch, names in declaration(tools / 'stage-mshtml-hw.py', 'TARGETS').items():
        add(arch.removesuffix('-windows'), (name for name in names if not name.endswith('.tlb')))
    add('i386', declaration(tools / 'stage-dshow-i386.py', 'TARGETS'))
    # These are resource/static-library make targets, not PE images to traverse.
    resources = ['dlls/aero.msstyles/x86_64-windows/aero.msstyles']
    resources += [f'dlls/mshtml.tlb/{arch}-windows/mshtml.tlb' for arch in ('i386', 'x86_64')]
    resources += [f'libs/{name}/i386-windows/lib{name}.a'
                  for name in ('strmbase', 'strmiids', 'uuid', 'dxguid', 'winecrt0', 'compiler-rt')]
    return modules, resources
