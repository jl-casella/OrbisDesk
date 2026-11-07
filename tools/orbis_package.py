# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small package helper using the existing OpenOrbis SDK and installed .NET."""
import os,pathlib,shutil,subprocess,re

def package_app(root,app,out,title,title_id,content_id,version='01.00',filename=None):
    sdk=root/'.deps/sdk/OpenOrbis/PS4Toolchain';env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
    app.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    log=app.parent/'package.log'
    def run(command):
        with log.open('a') as stream:
            subprocess.run(list(map(str,command)),cwd=app,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
    tool=sdk/'bin/linux/PkgTool.Core';sys=app/'sce_sys';sys.mkdir(exist_ok=True);sfo=sys/'param.sfo'
    run([tool,'sfo_new',sfo])
    fields={'APP_TYPE':(1,'Integer',4),'APP_VER':(version,'Utf8',8),'ATTRIBUTE':(0,'Integer',4),
        'CATEGORY':('gd','Utf8',4),'CONTENT_ID':(content_id,'Utf8',48),'DOWNLOAD_DATA_SIZE':(0,'Integer',4),
        'SYSTEM_VER':(0,'Integer',4),'TITLE':(title,'Utf8',128),'TITLE_ID':(title_id,'Utf8',12),'VERSION':(version,'Utf8',8)}
    for name,(value,kind,size) in fields.items():run([tool,'sfo_setentry',sfo,name,'--type',kind,'--maxsize',size,'--value',value])
    # W170: the app icon of tools/make-app-icon.py (a PS4-shaped window), when it has been made
    icon=root/'out/app-icon/icon0.png'
    shutil.copyfile(icon if icon.exists() else root/'build/hardware-h001b/app/sce_sys/icon0.png',sys/'icon0.png')
    sample=sdk/'samples/hello_world'
    for name in ('sce_module/libc.prx','sce_module/libSceFios2.prx','sce_sys/about/right.sprx'):
        dest=app/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sample/name,dest)
    files=sorted(str(p.relative_to(app)) for p in app.rglob('*') if p.is_file() and p.name!='pkg.gp4')
    run([sdk/'bin/linux/create-gp4','-out','pkg.gp4','--content-id='+content_id,'--files',' '.join(files)])
    dotnet=pathlib.Path('/mnt/c/Program Files/dotnet/dotnet.exe')
    def crypto(verb,*args):
        if dotnet.is_file():
            win=lambda p:subprocess.check_output(['wslpath','-w',str(p.resolve())],text=True).strip()
            run([dotnet,'--roll-forward','Major',win(sdk/'bin/windows/PkgTool.Core.dll'),verb,*[win(p) for p in args]])
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
