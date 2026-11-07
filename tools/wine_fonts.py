# SPDX-License-Identifier: LGPL-2.1-or-later
"""Verified font staging into an already validated, private Wine prefix."""
import hashlib,pathlib,re,shutil

def stage_fonts(root, bundle, manifest, prefix):
    # Validate all inputs before changing the prefix. No host font discovery.
    for name,entry in manifest.items():
        if pathlib.PurePosixPath(name).name!=name or '\\' in name:raise ValueError('Unsafe font asset name')
        if pathlib.PurePosixPath(entry['path']).is_absolute() or '..' in pathlib.PurePosixPath(entry['path']).parts:
            raise ValueError('Unsafe font asset path')
        source=bundle/entry['path']
        if hashlib.sha256(source.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Font asset hash mismatch: '+entry['path'])
    destination=prefix/'drive_c/windows/Fonts'
    if destination.is_symlink():raise ValueError('Fonts directory cannot be a symlink')
    destination.mkdir(parents=True,exist_ok=True)
    for name,entry in manifest.items():
        target=destination/name if name.endswith('.ttf') else destination/'licenses'/name
        target.parent.mkdir(exist_ok=True)
        if target.is_symlink():raise ValueError('Font asset destination cannot be a symlink')
        shutil.copyfile(bundle/entry['path'],target)
    registry=prefix/'system.reg'
    text=registry.read_text()
    sections={r'Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts':{
        'Tahoma (TrueType)':r'C:\\windows\\Fonts\\tahoma.ttf',
        'Tahoma Bold (TrueType)':r'C:\\windows\\Fonts\\tahomabd.ttf',
        'Marlett (TrueType)':r'C:\\windows\\Fonts\\marlett.ttf'},
        r'Software\\Microsoft\\Windows NT\\CurrentVersion\\FontSubstitutes':{
        'MS Shell Dlg':'Tahoma','MS Shell Dlg 2':'Tahoma','MS Sans Serif':'Tahoma','Arial':'Tahoma'}}
    for section,values in sections.items():
        pattern=r'(?m)^\['+re.escape(section)+r'\][^\n]*\n([^\[]*)'
        found=re.search(pattern,text)
        body=found.group(1) if found else ''
        for key,value in values.items():
            body=re.sub(r'(?m)^"'+re.escape(key)+r'"=.*\n?','',body)
            body+='"'+key+'"="'+value+'"\n'
        block='['+section+']\n'+body.rstrip()+'\n\n'
        text=text[:found.start()]+block+text[found.end():] if found else text+'\n'+block
    registry.write_text(text)
    return {name:entry['sha256'] for name,entry in manifest.items()}
