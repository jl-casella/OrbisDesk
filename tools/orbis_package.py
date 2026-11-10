# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small package helper using the existing OpenOrbis SDK and installed .NET."""
import os,pathlib,shutil,subprocess,re

def write_gp4(path,content_id,files,directories,timestamp):
    """The gp4 create-gp4 writes, for any number of files: paths are XML-escaped (spaces, &, quotes) and
    listed in the file, not on a command line. files: [(target path in the package, source path relative
    to the gp4's folder)]; directories: every target folder (empty ones included)."""
    from xml.sax.saxutils import quoteattr
    tree={}
    for name in directories:
        node=tree
        for part in pathlib.PurePosixPath(name).parts:node=node.setdefault(part,{})
    def dirs(node,depth):
        lines=[]
        for name in sorted(node):
            pad='\t'*depth
            if node[name]:lines+=[pad+'<dir targ_name=%s>'%quoteattr(name),*dirs(node[name],depth+1),pad+'</dir>']
            else:lines.append(pad+'<dir targ_name=%s />'%quoteattr(name))
        return lines
    text=['<?xml version="1.0"?>',
        '<psproject xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" fmt="gp4" version="1000">',
        '\t<volume>','\t\t<volume_type>pkg_ps4_app</volume_type>','\t\t<volume_id>PS4VOLUME</volume_id>',
        '\t\t<volume_ts>%s</volume_ts>'%timestamp,
        '\t\t<package content_id=%s passcode="00000000000000000000000000000000"'%quoteattr(content_id),
        '\t\t\tstorage_type="digital50" app_type="full" />',
        '\t\t<chunk_info chunk_count="1" scenario_count="1">','\t\t\t<chunks>',
        '\t\t\t\t<chunk id="0" layer_no="0" label="Chunk #0" />','\t\t\t</chunks>',
        '\t\t\t<scenarios default_id="0">',
        '\t\t\t\t<scenario id="0" type="sp" initial_chunk_count="1" label="Scenario #0">0</scenario>',
        '\t\t\t</scenarios>','\t\t</chunk_info>','\t</volume>','\t<files img_no="0">',
        *('\t\t<file targ_path=%s orig_path=%s />'%(quoteattr(t),quoteattr(o)) for t,o in sorted(files)),
        '\t</files>','\t<rootdir>',*dirs(tree,2),'\t</rootdir>','</psproject>','']
    pathlib.Path(path).write_text('\n'.join(text),encoding='utf-8')

def package_app(root,app,out,title,title_id,content_id,version='01.00',filename=None,extra=None):
    """extra: {target path in the package: source file} for files kept outside app/ (the embedded runtime)."""
    sdk=root/'.deps/sdk/OpenOrbis/PS4Toolchain';env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
    app.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    log=app.parent/'package.log'
    def run(command):
        with log.open('a') as stream:
            subprocess.run(list(map(str,command)),cwd=app,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
    tool=sdk/'bin/linux/PkgTool.Core';sys=app/'sce_sys';sys.mkdir(exist_ok=True);sfo=sys/'param.sfo'
    pkg_command=['dotnet','--roll-forward','Major',sdk/'bin/windows/PkgTool.Core.dll'] if shutil.which('dotnet') else [tool]
    run([*pkg_command,'sfo_new',sfo])
    fields={'APP_TYPE':(1,'Integer',4),'APP_VER':(version,'Utf8',8),'ATTRIBUTE':(0,'Integer',4),
        'CATEGORY':('gd','Utf8',4),'CONTENT_ID':(content_id,'Utf8',48),'DOWNLOAD_DATA_SIZE':(0,'Integer',4),
        'SYSTEM_VER':(0,'Integer',4),'TITLE':(title,'Utf8',128),'TITLE_ID':(title_id,'Utf8',12),'VERSION':(version,'Utf8',8)}
    for name,(value,kind,size) in fields.items():run([*pkg_command,'sfo_setentry',sfo,name,'--type',kind,'--maxsize',size,'--value',value])
    # W170: the app icon of tools/make-app-icon.py (a PS4-shaped window), when it has been made
    icon=root/'out/app-icon/icon0.png'
    shutil.copyfile(icon if icon.exists() else root/'build/hardware-h001b/app/sce_sys/icon0.png',sys/'icon0.png')
    sample=sdk/'samples/hello_world'
    for name in ('sce_module/libc.prx','sce_module/libSceFios2.prx','sce_sys/about/right.sprx'):
        dest=app/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sample/name,dest)
    files=[(p.relative_to(app).as_posix(),)*2 for p in app.rglob('*') if p.is_file() and p.name!='pkg.gp4']
    directories={p.relative_to(app).as_posix() for p in app.rglob('*') if p.is_dir()}
    # the folders create-gp4 always declared
    directories|={'sce_sys/about','sce_module','assets/audio','assets/fonts','assets/images','assets/misc','assets/videos'}
    for target,source in (extra or {}).items():
        target=pathlib.PurePosixPath(target)
        if target.is_absolute() or '..' in target.parts:raise ValueError('package path must be relative: '+str(target))
        files.append((target.as_posix(),pathlib.Path(os.path.relpath(source,app)).as_posix()))
        directories.update(p.as_posix() for p in target.parents if p.as_posix()!='.')
    if len({t.lower() for t,_ in files})!=len(files):raise ValueError('package paths differ only by case')
    import datetime
    write_gp4(app/'pkg.gp4',content_id,files,directories,
              datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
    dotnet=pathlib.Path('/mnt/c/Program Files/dotnet/dotnet.exe')
    def crypto(verb,*args):
        if dotnet.is_file():
            win=lambda p:subprocess.check_output(['wslpath','-w',str(p.resolve())],text=True).strip()
            run([dotnet,'--roll-forward','Major',win(sdk/'bin/windows/PkgTool.Core.dll'),verb,*[win(p) for p in args]])
        elif shutil.which('dotnet'):
            run(['dotnet','--roll-forward','Major',sdk/'bin/windows/PkgTool.Core.dll',verb,*args])
        else:run([tool,verb,*args])
    crypto('pkg_build',app/'pkg.gp4',out)
    package=out/(content_id+'.pkg');crypto('pkg_validate',package)
    if title.startswith('OrbisDesk'):
        stem=re.sub(r'[^A-Za-z0-9._-]+','-',title).strip('-')
        if filename is not None and (pathlib.Path(filename).name!=filename or not filename.endswith('.pkg')):
            raise ValueError('package filename must be a .pkg basename')
        named=out/(filename or (stem+'-'+version+'.pkg'))
        if named!=package:package.replace(named)
        package=named
    return package
