#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build an installable first hardware check, independent of Wine and its prefix."""
import hashlib,json,os,pathlib,shutil,struct,subprocess,zlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sdk=ROOT/'.deps/sdk/OpenOrbis/PS4Toolchain'
work=ROOT/'build/hardware-h001b';app=work/'app';app.mkdir(parents=True,exist_ok=True)
out=ROOT/'out/hardware-h001b';out.mkdir(parents=True,exist_ok=True)
content='IV0000-ORBW00001_00-ORBISWINHW000001'
env=dict(os.environ,OO_PS4_TOOLCHAIN=str(sdk))
def run(command,cwd=ROOT):
    with (work/'build.log').open('a') as log:
        log.write('+ '+' '.join(map(str,command))+'\n');log.flush()
        subprocess.run(list(map(str,command)),cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
flags=['--target=x86_64-pc-freebsd12-elf','-fPIC','-march=btver2','-O2','-g','-Wall','-Wextra','-Werror',
       '-isysroot',sdk,'-isystem',sdk/'include']
sink=work/'sink.c'
sink.write_text((ROOT/'platform/ps4/pw_wine_sink_ps4.c').read_text().replace('"/data/frames','"/data/orbisdesk/hw01/frames'))
objects=[]
for source in (ROOT/'native/hardware_boot.c',sink):
    obj=work/(source.stem+'.o');run(['clang',*flags,'-c',source,'-o',obj]);objects.append(obj)
elf=work/'hardware.elf'
run(['ld.lld','-pie','--no-undefined','--eh-frame-hdr','--script',sdk/'link.x','-o',elf,*objects,
     sdk/'lib/crt1.o','-L',sdk/'lib','-lc','-lkernel','-lSceVideoOut'])
run([sdk/'bin/linux/create-fself','-in='+str(elf),'-out='+str(work/'hardware.oelf'),
     '--eboot',app/'eboot.bin','--paid','0x3800000000000011'])
sys=app/'sce_sys';sys.mkdir(exist_ok=True)
pkg=sdk/'bin/linux/PkgTool.Core';sfo=sys/'param.sfo'
run([pkg,'sfo_new',sfo])
entries={'APP_TYPE':(1,'Integer',4),'APP_VER':('01.01','Utf8',8),'ATTRIBUTE':(0,'Integer',4),
         'CATEGORY':('gd','Utf8',4),'CONTENT_ID':(content,'Utf8',48),'DOWNLOAD_DATA_SIZE':(0,'Integer',4),
         'SYSTEM_VER':(0,'Integer',4),'TITLE':('OrbisDesk Hardware Check H001B','Utf8',128),
         'TITLE_ID':('ORBW00001','Utf8',12),'VERSION':('01.01','Utf8',8)}
for name,(value,kind,size) in entries.items():
    run([pkg,'sfo_setentry',sfo,name,'--type',kind,'--maxsize',str(size),'--value',str(value)])
# Own small OD icon for OrbisDesk; no Sony or third-party artwork.
pixels=bytearray(bytes((16,32,48))*(512*512))
letters=((60,(14,17,17,17,17,17,14)),(280,(30,17,17,17,17,17,30)))
for left,rows in letters:
    for y,bits in enumerate(rows):
        for x in range(5):
            if bits&(1<<(4-x)):
                for yy in range(24):
                    for xx in range(24):
                        at=((160+y*24+yy)*512+left+x*24+xx)*3;pixels[at:at+3]=b'\xff\xff\xff'
def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
raw=b''.join(b'\0'+pixels[y*512*3:(y+1)*512*3] for y in range(512))
(sys/'icon0.png').write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',512,512,8,2,0,0,0))+
    chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))
sample=sdk/'samples/hello_world'
for name in ('sce_module/libc.prx','sce_module/libSceFios2.prx','sce_sys/about/right.sprx'):
    target=app/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sample/name,target)
(app/'hardware-marker.txt').write_text('orbisdesk app0 H001B\n')
files=sorted(str(p.relative_to(app)) for p in app.rglob('*') if p.is_file() and p.name!='pkg.gp4')
run([sdk/'bin/linux/create-gp4','-out','pkg.gp4','--content-id='+content,'--files',' '.join(files)],cwd=app)
dotnet=pathlib.Path('/mnt/c/Program Files/dotnet/dotnet.exe')
def crypto_tool(verb,*args):
    # The SDK's self-contained Linux .NET 3 binary needs obsolete libssl1.1.
    # On WSL use the installed Windows runtime for packaging, without changing it.
    if dotnet.is_file():
        win=lambda p:subprocess.check_output(['wslpath','-w',str(p.resolve())],text=True).strip()
        run([dotnet,'--roll-forward','Major',win(sdk/'bin/windows/PkgTool.Core.dll'),verb,
             *[win(p) for p in args]],cwd=app)
    else:run([pkg,verb,*args],cwd=app)
crypto_tool('pkg_build',app/'pkg.gp4',out)
package=out/(content+'.pkg')
crypto_tool('pkg_validate',package)
named=out/'OrbisDesk-Hardware-Check-H001B-01.01.pkg'
package.replace(named);package=named
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'build':'H001B','app_version':'01.01','title_id':'ORBW00001','content_id':content,'package':str(package.relative_to(ROOT)),
    'package_engine':'Windows PkgTool with installed .NET roll-forward' if dotnet.is_file() else 'Linux PkgTool',
    'package_sha256':sha(package),'package_bytes':package.stat().st_size,'eboot_sha256':sha(app/'eboot.bin'),
    'sources':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'native/hardware_boot.c',ROOT/'tools/build-hardware-boot.py',
        ROOT/'platform/ps4/pw_wine_sink_ps4.c',sink)},
    'files':{name:sha(app/name) for name in files},'hardware_status':'pending',
    'log_directory':'/data/orbisdesk/hw01','no_windows_execution':True}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
